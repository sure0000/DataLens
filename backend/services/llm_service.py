import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from config import get_settings

settings = get_settings()
TABLE_DESC_SECTIONS = ["业务描述", "数据定位", "核心口径", "使用建议", "风险边界"]


def _has_llm_key() -> bool:
    return bool(settings.deepseek_api_key or settings.openai_api_key)


_llm_client: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    api_key = settings.deepseek_api_key or settings.openai_api_key
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY or OPENAI_API_KEY is required")
    if settings.deepseek_api_key:
        _llm_client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    else:
        _llm_client = AsyncOpenAI(api_key=api_key)
    return _llm_client


async def _retry_json(call: Callable[[], Awaitable[str]], max_attempts: int = 3, delay: int = 1) -> dict[str, Any]:
    import logging
    _logger = logging.getLogger(__name__)
    last_error: Exception | None = None
    last_raw: str = ""
    for attempt in range(max_attempts):
        try:
            last_raw = await call()
            return json.loads(last_raw)
        except Exception as e:  # noqa: BLE001
            last_error = e
            _logger.warning(
                "LLM JSON parse failed (attempt %d/%d): %s | raw response: %.500s",
                attempt + 1,
                max_attempts,
                e,
                last_raw,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"LLM JSON parse failed after {max_attempts} attempts: {last_error}")


async def _chat_json(prompt: str) -> dict[str, Any]:
    client = _client()

    async def do_call() -> str:
        resp = await client.chat.completions.create(
            model="deepseek-chat" if settings.deepseek_api_key else "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"

    return await _retry_json(do_call)


async def _chat_text(prompt: str, temperature: float = 0.3) -> str:
    client = _client()
    resp = await client.chat.completions.create(
        model="deepseek-chat" if settings.deepseek_api_key else "gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def _heuristic_intent(question: str) -> str:
    q = question.lower()
    sql_signals = [
        "sql",
        "查询",
        "统计",
        "按天",
        "趋势",
        "gmv",
        "订单",
        "销量",
        "top",
        "group by",
        "where",
        "sum(",
        "count(",
    ]
    if any(s in q for s in sql_signals):
        return "sql_query"
    return "general_qa"


async def classify_question_intent(question: str) -> dict[str, str]:
    if not _has_llm_key():
        intent = _heuristic_intent(question)
        return {
            "intent": intent,
            "reason": "未配置LLM Key，使用规则进行意图识别",
        }
    prompt = f"""你是 ChatBI 助手的意图分类器。
请判断用户问题是否需要"生成并执行SQL"。

分类规则：
1) 若用户明确要查数、统计、趋势、明细、排行、对比、筛选，返回 sql_query
2) 若用户是解释概念、系统使用帮助、闲聊、写作润色、策略建议且不依赖即时查数，返回 general_qa
3) 不确定时，优先返回 general_qa（避免误触发SQL）

用户问题: {question}

仅输出JSON，键为: intent,reason
intent 只能是 sql_query 或 general_qa
"""
    data = await _chat_json(prompt)
    intent = str(data.get("intent") or "").strip()
    if intent not in {"sql_query", "general_qa"}:
        intent = "general_qa"
    return {"intent": intent, "reason": str(data.get("reason") or "")}


def guardrail_for_question(question: str) -> dict[str, str] | None:
    q = question.lower()
    privilege_keywords = [
        "密码",
        "token",
        "api key",
        "access key",
        "secret",
        "越权",
        "绕过",
        "提权",
        "注入",
        "爆破",
        "删库",
        "破解",
    ]
    unrelated_keywords = [
        "讲笑话",
        "星座",
        "写诗",
        "塔罗",
        "彩票开奖",
        "追星",
        "菜谱",
    ]

    has_privilege_risk = any(k in q for k in privilege_keywords)
    is_unrelated = any(k in q for k in unrelated_keywords)

    if has_privilege_risk:
        return {
            "reason": "触发安全护栏：问题涉及潜在越权、凭据或攻击性操作",
            "answer": (
                "结论\n"
                "- 这个问题涉及越权或敏感信息操作，我不能提供这类协助。\n\n"
                "说明\n"
                "- 为保护数据与系统安全，助手不会提供绕过权限、获取密钥或破坏性操作建议。\n"
                "- 你可以基于已有权限提出合规的数据分析目标，我会继续协助。\n\n"
                "下一步\n"
                "- 你可以改问：`在我有权限的订单表中，近7天 GMV 趋势如何？`\n"
                "- 你可以改问：`如何设计最小权限的数据分析角色？`"
            ),
        }
    if is_unrelated:
        return {
            "reason": "触发范围护栏：问题与 DataLens 数据分析场景无关",
            "answer": (
                "结论\n"
                "- 这个问题超出当前数据分析助手的服务范围。\n\n"
                "说明\n"
                "- 我主要用于业务数据查询、指标解释、SQL 分析和结果解读。\n"
                "- 与业务分析无关的话题可能无法得到准确或稳定的结果。\n\n"
                "下一步\n"
                "- 你可以改问：`帮我拆解本周留存下降的排查思路`。\n"
                "- 你可以改问：`按渠道看最近30天订单转化率趋势`。"
            ),
        }
    return None


async def answer_general_question(question: str, context_hint: str = "") -> str:
    if not _has_llm_key():
        return (
            "结论\n"
            "- 这是一个非 SQL 查询问题，建议直接用自然语言解答。\n\n"
            "说明\n"
            "- 当前未配置 LLM Key，暂时无法给出更智能的上下文化回答。\n\n"
            "下一步\n"
            "- 你可以继续补充背景、目标和限制条件，我会给出更具体的建议。"
        )
    prompt = f"""你是 DataLens 的 ChatBI 助手。
请直接回答用户问题，不要生成 SQL。
回答要求：
- 使用固定中文结构，严格按以下模板输出，不要添加其他标题：
结论
- <1-2 条要点>

说明
- <2-4 条要点，必要时给示例>

下一步
- <1-2 条可执行建议>
- 每条以 "- " 开头
- 不要使用 Markdown 代码块
- 不要输出 SQL

上下文提示（可为空）:
{context_hint}

用户问题:
{question}
"""
    text = await _chat_text(prompt, temperature=0.4)
    if not text:
        return (
            "结论\n"
            "- 这个问题不需要执行 SQL。\n\n"
            "说明\n"
            "- 更适合先明确业务目标与口径，再给出分析方案。\n\n"
            "下一步\n"
            "- 你可以补充想看的指标、时间范围和维度，我会给出可执行建议。"
        )

    lines = [line.rstrip() for line in text.splitlines()]
    normalized: list[str] = []
    blank_count = 0
    for line in lines:
        stripped = re.sub(r"\s+", " ", line).strip()
        if not stripped:
            blank_count += 1
            if blank_count <= 1:
                normalized.append("")
            continue
        blank_count = 0
        if stripped.startswith(("*", "•")):
            stripped = f"- {stripped[1:].strip()}"
        normalized.append(stripped)

    return "\n".join(normalized).strip()


async def analyze_column(table_name: str, column_info: dict[str, Any], profiling_result: dict[str, Any]) -> dict[str, Any]:
    if not _has_llm_key():
        col = column_info.get("column_name", "")
        ctype = (column_info.get("data_type") or "").lower()
        semantic_type = "dimension"
        if "id" in col.lower():
            semantic_type = "id"
        elif any(x in ctype for x in ["int", "decimal", "float", "double"]):
            semantic_type = "metric"
        elif "time" in col.lower() or "date" in col.lower():
            semantic_type = "time"
        return {
            "desc": f"{col} 字段（本地兜底语义）",
            "type": semantic_type,
            "is_usable": True,
            "reason": "未配置LLM Key，使用本地规则兜底生成",
        }
    prompt = f"""你是一个数据分析专家，请根据字段信息理解其业务含义。
表名: {table_name}
字段信息: {json.dumps(column_info, ensure_ascii=False)}
统计信息: {json.dumps(profiling_result, ensure_ascii=False)}
输出JSON键: desc,type,is_usable,reason"""
    return await _chat_json(prompt)


async def analyze_table(
    table_name: str,
    columns_with_semantic: list[dict[str, Any]],
    row_count: int,
    business_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def fallback_summary_text() -> str:
        domain_names = [d.get("domain_name", "") for d in domain_contexts if d.get("domain_name")]
        domain_descs = [d.get("domain_description", "") for d in domain_contexts if d.get("domain_description")]
        datasource_desc = str(context.get("datasource_description") or "").strip() or "暂无数据源描述"
        database_desc = str(context.get("database_description") or "").strip() or "暂无数据库描述"
        table_desc = str(context.get("table_business_description") or "").strip() or "暂无表级业务描述"
        prev_desc = str(context.get("previous_table_description") or "").strip()
        return (
            "业务描述\n"
            f"- {table_name} 用于承载该业务域相关的核心数据。\n"
            f"- 关联数据域：{('、'.join(domain_names) if domain_names else '未归属明确数据域')}。\n\n"
            "数据定位\n"
            f"- 关联业务域：{('、'.join(domain_names) if domain_names else '未归属明确业务域')}。\n"
            f"- 数据库描述：{database_desc}。\n"
            f"- 表级描述：{table_desc}。\n\n"
            "核心口径\n"
            f"- 建议优先关注关键字段：{', '.join([c.get('column_name', '') for c in columns_with_semantic[:5] if c.get('column_name')]) or '待补充'}。\n"
            f"- 历史说明参考：{prev_desc or '暂无历史说明'}。\n"
            f"- 数据域补充说明：{('；'.join(domain_descs) if domain_descs else '暂无补充')}。\n\n"
            "使用建议\n"
            "- 适合用于趋势、结构占比、明细核对等分析。\n"
            "- 建议联动时间维度和核心业务维度进行分组统计。\n\n"
            "风险边界\n"
            "- 当前说明为自动生成，使用前需结合业务口径做复核。\n"
            "- 如存在字段缺失或命名歧义，可能导致指标解释偏差。"
        )

    def normalize_summary_template(raw_summary: str) -> str:
        def parse_sections(raw_text: str) -> dict[str, list[str]]:
            parsed_sections: dict[str, list[str]] = {s: [] for s in TABLE_DESC_SECTIONS}
            current_section = ""
            for line in raw_text.split("\n"):
                trimmed = line.strip()
                if not trimmed:
                    continue
                if trimmed in parsed_sections:
                    current_section = trimmed
                    continue
                if current_section:
                    if trimmed.startswith(("*", "•")):
                        trimmed = f"- {trimmed[1:].strip()}"
                    if not trimmed.startswith("- "):
                        trimmed = f"- {trimmed}"
                    parsed_sections[current_section].append(trimmed)
            return parsed_sections

        raw = (raw_summary or "").replace("\r", "").strip()
        if not raw:
            return fallback_summary_text()
        parsed = parse_sections(raw)
        fallback_parsed = parse_sections(fallback_summary_text())
        for section in TABLE_DESC_SECTIONS:
            if not parsed[section]:
                parsed[section] = fallback_parsed[section]

        blocks = [f"{section}\n" + "\n".join(parsed[section][:4]) for section in TABLE_DESC_SECTIONS]
        return "\n\n".join(blocks)

    context = business_context or {}
    domain_contexts = context.get("domain_contexts") or []
    if not _has_llm_key():
        return {
            "summary": fallback_summary_text(),
            "use_cases": ["基础统计分析", "趋势分析", "明细核对"],
            "key_columns": [c["column_name"] for c in columns_with_semantic[:3]],
            "warnings": "未配置LLM Key，当前为规则生成结果，仅用于本地联调",
        }
    prompt = f"""你是资深数据分析师，请总结数据表用途。
表名: {table_name}
字段: {json.dumps(columns_with_semantic, ensure_ascii=False)}
总行数: {row_count}
业务上下文（必须充分考虑）: {json.dumps(context, ensure_ascii=False)}

输出要求：
1) summary 必须严格使用下面固定模板输出，不要新增/删减标题：
业务描述
- <1-3条>

数据定位
- <2-4条，覆盖业务域/数据库/表自身描述>

核心口径
- <2-4条，给出关键口径、关键维度、关键指标>

使用建议
- <2-4条，给出适合的分析用法>

风险边界
- <2-4条，给出限制、风险与不适用场景>

2) 每一条都必须以 "- " 开头
2) use_cases 给出 3-5 个高价值分析场景
3) key_columns 只列最关键字段（3-8个）
4) warnings 明确风险/歧义/缺失信息

输出JSON键: summary,use_cases,key_columns,warnings"""
    result = await _chat_json(prompt)
    use_cases = result.get("use_cases")
    key_columns = result.get("key_columns")
    result["summary"] = normalize_summary_template(str(result.get("summary") or ""))
    result["use_cases"] = use_cases if isinstance(use_cases, list) else ["基础统计分析", "趋势分析", "明细核对"]
    result["key_columns"] = key_columns if isinstance(key_columns, list) else [c["column_name"] for c in columns_with_semantic[:3]]
    result["warnings"] = str(result.get("warnings") or "").strip() or "暂无明确风险说明，建议结合业务背景复核。"
    return result


async def generate_sql(question: str, table_schema: str, table_summary: str) -> dict[str, Any]:
    if not _has_llm_key():
        return {
            "sql": "SELECT DATE(created_at) AS date, SUM(order_amt) AS gmv FROM orders WHERE created_at >= NOW() - INTERVAL 7 DAY GROUP BY DATE(created_at) ORDER BY date;",
            "explanation": "未配置LLM Key，返回本地兜底SQL模板用于联调",
            "referenced_columns": ["created_at", "order_amt"],
        }
    prompt = f"""你是数据分析专家，请根据信息生成MySQL SQL。
必须遵循：
1) 优先使用"优先上下文-数据源采集信息"和"优先上下文-AI分析信息"中的信息确定数据来源、业务口径和可用表。
2) 仅在上下文不足时，才参考"历史相似问答"。
3) SQL 必须可执行、只读、无写操作。
4) SQL 必须格式化输出：关键字大写，每个子句（SELECT/FROM/WHERE/JOIN/GROUP BY/ORDER BY/HAVING/LIMIT）单独一行，嵌套子查询缩进2个空格。
5) explanation 需说明你如何利用数据源采集信息与AI分析信息。
6) 禁止输出 markdown 代码块。

context: {table_schema}
summary: {table_summary}
question: {question}
输出JSON键: sql,explanation,referenced_columns"""
    return await _chat_json(prompt)


def _format_sql(sql: str) -> str:
    """Basic SQL formatter: uppercase keywords, one clause per line."""
    keywords = [
        "SELECT", "FROM", "WHERE", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN",
        "JOIN", "ON", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "OFFSET",
        "UNION ALL", "UNION", "WITH",
    ]
    result = sql.strip()
    for kw in keywords:
        result = re.sub(rf"(?i)\b{re.escape(kw)}\b", kw, result)
    clause_re = re.compile(
        r"\b(SELECT|FROM|WHERE|(?:LEFT|RIGHT|INNER|OUTER)?\s*JOIN|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|UNION(?: ALL)?|WITH)\b",
        re.IGNORECASE,
    )
    result = clause_re.sub(lambda m: "\n" + m.group(0).upper(), result)
    lines = [line.strip() for line in result.splitlines() if line.strip()]
    return "\n".join(lines)


def sanitize_sql_text(sql: str) -> str:
    cleaned = (sql or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip().rstrip(";").strip()
    cleaned = _format_sql(cleaned)
    return cleaned


async def repair_failed_sql(
    question: str,
    failed_sql: str,
    error_message: str,
    table_schema: str,
    table_summary: str,
) -> dict[str, str]:
    sanitized_failed_sql = sanitize_sql_text(failed_sql)
    # 本地兜底：即便没配 LLM，也先做一次最基础的 SQL 清洗修复。
    if not _has_llm_key():
        return {
            "sql": sanitized_failed_sql,
            "reason": "未配置LLM Key，仅执行基础SQL清洗（去除代码块/分号）。",
        }

    prompt = f"""你是资深 SQL 修复助手。请根据执行错误修复 SQL。
要求：
1) 只允许输出 JSON，键为 sql,reason。
2) sql 必须是可执行只读语句（SELECT/SHOW/WITH/DESC/EXPLAIN）。
3) 必须优先依据 error_message 修复，不要凭空新增不存在的字段。
4) SQL 必须格式化输出：关键字大写，每个子句单独一行，嵌套子查询缩进2个空格。
5) 禁止输出 markdown 代码块。

question: {question}
failed_sql: {sanitized_failed_sql}
error_message: {error_message}
context: {table_schema}
summary: {table_summary}
"""
    fixed = await _chat_json(prompt)
    candidate = sanitize_sql_text(str(fixed.get("sql") or ""))
    reason = str(fixed.get("reason") or "").strip() or "根据数据库报错自动修复 SQL。"
    return {"sql": candidate, "reason": reason}


async def batch_analyze_columns(
    table_name: str, column_inputs: list[tuple[dict[str, Any], dict[str, Any]]], concurrency: int = 5
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)

    async def worker(col: dict[str, Any], prof: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await analyze_column(table_name, col, prof)

    return await asyncio.gather(*(worker(c, p) for c, p in column_inputs))
