import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from services.httpx_env import async_client as httpx_async_client
from services.llm_connections import get_connection, is_connection_ref, parse_connection_id
from services.llm_models import has_any_llm_key, parse_model_ref, resolve_effective_model
from services.runtime_llm_config import (
    get_effective_deepseek_api_key,
    get_effective_deepseek_base_url,
    get_effective_openai_api_key,
    get_effective_openai_base_url,
)
from prompts import load_prompt as _load_prompt

TABLE_DESC_SECTIONS = ["业务描述", "数据定位", "核心口径", "使用建议", "风险边界"]

SQL_GENERATION_SYSTEM = _load_prompt("sql_generation_system")
SQL_REPAIR_SYSTEM = _load_prompt("sql_repair_system")


@dataclass(frozen=True)
class SqlCopilotContext:
    """分层 Prompt 的业务侧块（对齐语义上下文引擎：Business + Few-shot）。"""

    knowledge: str
    datasource_priority: str
    schema: str
    few_shot_json: str

    def business_sections(self) -> str:
        parts: list[str] = []
        if self.knowledge.strip():
            parts.append(f"## BUSINESS CONTEXT — 知识库与业务口径\n{self.knowledge.strip()}")
        parts.append(
            f"## BUSINESS CONTEXT — 数据源与表分析（优先采信）\n{self.datasource_priority.strip()}"
        )
        parts.append(f"## BUSINESS CONTEXT — 结构化字段\n{self.schema.strip()}")
        return "\n\n".join(parts)

    def few_shot_section(self) -> str:
        return f"## FEW-SHOT — 历史相似问答（仅上下文不足时参考）\n{self.few_shot_json.strip()}"


def _sql_generation_user_message(question: str, summary: str, ctx: SqlCopilotContext) -> str:
    return (
        f"{ctx.business_sections()}\n\n"
        f"{ctx.few_shot_section()}\n\n"
        f"## TABLE SUMMARY（表级摘要聚合）\n{summary.strip()}\n\n"
        f"## USER QUESTION\n{question.strip()}"
    )

_async_clients: dict[str, AsyncOpenAI] = {}
_async_conn_clients: dict[str, AsyncOpenAI] = {}


def _llm_http_client() -> httpx.AsyncClient:
    return httpx_async_client(timeout=120.0)


def _has_llm_key(db: Session) -> bool:
    return has_any_llm_key(db)


def _client_cache_key(provider: str, api_key: str, base_url: str | None) -> str:
    raw = f"{provider}\0{api_key}\0{base_url or ''}"
    return sha256(raw.encode()).hexdigest()


def _async_client_for(provider: str, db: Session) -> AsyncOpenAI:
    if provider == "deepseek":
        api_key = get_effective_deepseek_api_key(db)
        base_url = get_effective_deepseek_base_url(db)
        if not api_key:
            raise RuntimeError("DeepSeek API key 未配置")
    elif provider == "openai":
        api_key = get_effective_openai_api_key(db)
        base_url = get_effective_openai_base_url(db)
        if not api_key:
            raise RuntimeError("OpenAI API key 未配置")
    else:
        raise RuntimeError(f"未知 provider: {provider}")

    cache_key = _client_cache_key(provider, api_key, base_url)
    if cache_key not in _async_clients:
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "http_client": _llm_http_client(),
        }
        if base_url:
            kwargs["base_url"] = base_url
        _async_clients[cache_key] = AsyncOpenAI(**kwargs)
    return _async_clients[cache_key]


def _async_client_for_connection_id(db: Session, conn_id: str) -> tuple[AsyncOpenAI, str]:
    """自定义接入：OpenAI SDK + 行内 base_url / api_key / model_id。"""
    row = get_connection(db, conn_id)
    if not row or not (row.api_key or "").strip():
        raise RuntimeError("大模型接入不存在或未配置密钥")
    api_key = row.api_key.strip()
    base = (row.base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("大模型接入未配置 Endpoint")
    model_name = (row.model_id or "").strip()
    if not model_name:
        raise RuntimeError("大模型接入未配置模型")
    cache_key = _client_cache_key("conn", api_key, base)
    if cache_key not in _async_conn_clients:
        _async_conn_clients[cache_key] = AsyncOpenAI(
            api_key=api_key,
            base_url=base,
            http_client=_llm_http_client(),
        )
    return _async_conn_clients[cache_key], model_name


def _client_and_model_for_ref(model_ref: str, db: Session) -> tuple[AsyncOpenAI, str]:
    if is_connection_ref(model_ref):
        return _async_client_for_connection_id(db, parse_connection_id(model_ref))
    provider, model_name = parse_model_ref(model_ref)
    return _async_client_for(provider, db), model_name


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


async def _chat_json(
    prompt: str,
    model_ref: str,
    db: Session,
    *,
    temperature: float = 0.1,
) -> dict[str, Any]:
    return await _chat_json_messages(
        [{"role": "user", "content": prompt}],
        model_ref,
        db,
        temperature=temperature,
    )


async def _chat_json_messages(
    messages: list[dict[str, str]],
    model_ref: str,
    db: Session,
    *,
    temperature: float = 0.1,
) -> dict[str, Any]:
    client, model_name = _client_and_model_for_ref(model_ref, db)

    async def do_call() -> str:
        resp = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"

    return await _retry_json(do_call)


async def _chat_text(prompt: str, model_ref: str, db: Session, temperature: float = 0.3) -> str:
    client, model_name = _client_and_model_for_ref(model_ref, db)
    resp = await client.chat.completions.create(
        model=model_name,
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


async def classify_question_intent(question: str, db: Session, chat_model: str | None = None) -> dict[str, str]:
    if not _has_llm_key(db):
        intent = _heuristic_intent(question)
        return {
            "intent": intent,
            "reason": "未配置LLM Key，使用规则进行意图识别",
        }
    model_ref = resolve_effective_model(chat_model, db)
    if not model_ref:
        intent = _heuristic_intent(question)
        return {"intent": intent, "reason": "无可用模型，使用规则进行意图识别"}
    prompt = _load_prompt("intent_classification").format(question=question)
    data = await _chat_json(prompt, model_ref, db)
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


async def answer_general_question(
    question: str,
    db: Session,
    context_hint: str = "",
    chat_model: str | None = None,
) -> str:
    if not _has_llm_key(db):
        return (
            "结论\n"
            "- 这是一个非 SQL 查询问题，建议直接用自然语言解答。\n\n"
            "说明\n"
            "- 当前未配置 LLM Key，暂时无法给出更智能的上下文化回答。\n\n"
            "下一步\n"
            "- 你可以继续补充背景、目标和限制条件，我会给出更具体的建议。"
        )
    model_ref = resolve_effective_model(chat_model, db)
    if not model_ref:
        return (
            "结论\n"
            "- 这是一个非 SQL 查询问题。\n\n"
            "说明\n"
            "- 当前无可用对话模型配置。\n\n"
            "下一步\n"
            "- 请在偏好设置中填写 API URL 与 Key，或配置环境变量。"
        )
    prompt = _load_prompt("general_qa").format(context_hint=context_hint, question=question)
    text = await _chat_text(prompt, model_ref, db, temperature=0.4)
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


async def analyze_column(
    table_name: str,
    column_info: dict[str, Any],
    profiling_result: dict[str, Any],
    db: Session,
    *,
    semantic_model_ref: str,
    business_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _has_llm_key(db):
        col = column_info.get("column_name", "")
        ctype = (column_info.get("data_type") or "").lower()
        semantic_type = "dimension"
        if "id" in col.lower():
            semantic_type = "id"
        elif any(x in ctype for x in ["int", "decimal", "float", "double"]):
            semantic_type = "metric"
        elif ctype not in ("enum", "set") and ("time" in col.lower() or "date" in col.lower()):
            semantic_type = "time"
        return {
            "desc": f"{col} 字段（本地兜底语义）",
            "type": semantic_type,
            "is_usable": True,
            "reason": "未配置LLM Key，使用本地规则兜底生成",
        }

    domain_contexts = (business_context or {}).get("domain_contexts") or []
    domain_knowledge_entries = (business_context or {}).get("domain_knowledge_entries") or []
    domain_hint = ""
    if domain_contexts:
        domain_names = [d.get("domain_name", "") for d in domain_contexts if d.get("domain_name")]
        domain_descs = [d.get("domain_description", "") for d in domain_contexts if d.get("domain_description")]
        domain_hint = f"\n所属业务域: {'、'.join(domain_names)}"
        if domain_descs:
            domain_hint += f"\n业务域描述: {'；'.join(domain_descs[:2])}"
    if domain_knowledge_entries:
        knowledge_parts = []
        for e in domain_knowledge_entries[:5]:
            part = f"- {e.get('title','')}"
            if e.get("summary"):
                part += f": {e.get('summary','')[:200]}"
            knowledge_parts.append(part)
        if knowledge_parts:
            domain_hint += f"\n关联业务知识条目:\n" + "\n".join(knowledge_parts)

    prompt = _load_prompt("analyze_column").format(
        table_name=table_name,
        column_info_json=json.dumps(column_info, ensure_ascii=False),
        profiling_json=json.dumps(profiling_result, ensure_ascii=False),
        domain_hint=domain_hint,
    )
    return await _chat_json(prompt, semantic_model_ref, db)


async def _normalize_summary_async(
    raw_summary: str,
    table_name: str,
    columns_with_semantic: list[dict[str, Any]],
    context: dict[str, Any],
    db: Session,
    semantic_model_ref: str,
    *,
    fallback_text: str = "",
) -> str:
    """Parse sections from LLM output, fill missing sections with targeted LLM call or rule fallback."""

    def _parse_sections(raw_text: str) -> dict[str, list[str]]:
        parsed: dict[str, list[str]] = {s: [] for s in TABLE_DESC_SECTIONS}
        current_section = ""
        for line in raw_text.split("\n"):
            trimmed = line.strip()
            if not trimmed:
                continue
            if trimmed in parsed:
                current_section = trimmed
                continue
            if current_section:
                if trimmed.startswith(("*", "•")):
                    trimmed = f"- {trimmed[1:].strip()}"
                if not trimmed.startswith("- "):
                    trimmed = f"- {trimmed}"
                parsed[current_section].append(trimmed)
        return parsed

    def _render_sections(parsed: dict[str, list[str]]) -> str:
        blocks = [f"{section}\n" + "\n".join(parsed[section][:5]) for section in TABLE_DESC_SECTIONS]
        return "\n\n".join(blocks)

    raw = (raw_summary or "").replace("\r", "").strip()
    if not raw:
        return fallback_text or _render_sections(_parse_sections(""))

    parsed = _parse_sections(raw)
    missing_sections = [s for s in TABLE_DESC_SECTIONS if not parsed[s]]
    if not missing_sections:
        return _render_sections(parsed)

    # Try LLM fill for missing sections
    if _has_llm_key(db) and semantic_model_ref:
        col_summary = json.dumps(
            [{"column_name": c.get("column_name"), "semantic_desc": c.get("semantic_desc"), "semantic_type": c.get("semantic_type")}
             for c in columns_with_semantic[:30]],
            ensure_ascii=False,
        )
        domain_hint = ""
        for d in (context.get("domain_contexts") or [])[:2]:
            domain_hint += f"业务域「{d.get('domain_name','')}」：{d.get('domain_description','')}；"
        fill_prompt = _load_prompt("normalize_summary").format(
            table_name=table_name,
            col_summary=col_summary,
            domain_hint=domain_hint,
            raw=raw[:800],
            missing_sections="、".join(missing_sections),
            section_format=chr(10).join(f"{s}\n- …" for s in missing_sections),
            section_keys=",".join(missing_sections),
        )
        try:
            fill_result = await _chat_json(fill_prompt, semantic_model_ref, db)
            for section in missing_sections:
                fill_val = fill_result.get(section)
                if isinstance(fill_val, str) and fill_val.strip():
                    lines = fill_val.strip().split("\n")
                    parsed[section] = [l if l.startswith("- ") else f"- {l}" for l in lines[:4] if l.strip()]
        except Exception:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("LLM section fill failed for %s, using rule fallback", missing_sections, exc_info=True)

    # Rule fallback for any sections still missing after LLM attempt
    fallback_parsed = _parse_sections(fallback_text or "")
    for section in TABLE_DESC_SECTIONS:
        if not parsed[section]:
            parsed[section] = fallback_parsed.get(section, [])

    return _render_sections(parsed)


async def analyze_table(
    table_name: str,
    columns_with_semantic: list[dict[str, Any]],
    row_count: int,
    db: Session,
    business_context: dict[str, Any] | None = None,
    *,
    semantic_model_ref: str,
) -> dict[str, Any]:
    def fallback_summary_text() -> str:
        domain_names = [d.get("domain_name", "") for d in domain_contexts if d.get("domain_name")]
        domain_descs = [d.get("domain_description", "") for d in domain_contexts if d.get("domain_description")]
        database_desc = str(context.get("database_description") or "").strip() or "暂无数据库描述"
        table_desc = str(context.get("table_business_description") or "").strip() or "暂无表级业务描述"
        prev_desc = str(context.get("previous_table_description") or "").strip()
        return (
            "业务描述\n"
            f"- 每行代表一条{table_name}记录（行粒度供参考，请结合实际业务确认）。\n"
            "- 该表的业务角色为数据明细/维度表，用于支撑相关业务域的数据查询与分析。\n"
            f"- 共包含 {len(columns_with_semantic)} 个字段、{row_count} 行数据，覆盖当前数据源可访问的数据范围。\n"
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

    context = business_context or {}
    domain_contexts = context.get("domain_contexts") or []

    # Column priority filtering for wide tables: keep top 50 by semantic importance
    _TYPE_PRIORITY = {"metric": 0, "time": 1, "id": 2, "enum": 3, "dimension": 4}
    if len(columns_with_semantic) > 50:
        sorted_cols = sorted(
            columns_with_semantic,
            key=lambda c: (
                _TYPE_PRIORITY.get(str(c.get("semantic_type", "")).lower(), 5),
                c.get("null_ratio", 0),
            ),
        )
        prompt_cols = sorted_cols[:50]
    else:
        prompt_cols = columns_with_semantic

    if not _has_llm_key(db):
        return {
            "summary": fallback_summary_text(),
            "use_cases": ["基础统计分析", "趋势分析", "明细核对"],
            "key_columns": [c["column_name"] for c in columns_with_semantic[:3]],
            "warnings": "未配置LLM Key，当前为规则生成结果，仅用于本地联调",
        }
    prompt = _load_prompt("analyze_table").format(
        table_name=table_name,
        prompt_cols_json=json.dumps(prompt_cols, ensure_ascii=False),
        row_count=row_count,
        context_json=json.dumps(context, ensure_ascii=False),
    )
    result = await _chat_json(prompt, semantic_model_ref, db)

    # Validate key_columns against real column names
    all_col_names = {c["column_name"] for c in columns_with_semantic if c.get("column_name")}
    raw_key_columns = result.get("key_columns")
    if isinstance(raw_key_columns, list):
        valid_cols = [k for k in raw_key_columns if k in all_col_names]
        hallucinated = [k for k in raw_key_columns if k not in all_col_names]
        if hallucinated:
            warnings_extra = f"以下key_columns未在表中找到对应字段，已自动移除：{'、'.join(hallucinated)}。"
            result["warnings"] = (
                str(result.get("warnings") or "").strip()
                + " " + warnings_extra
            ).strip()
        result["key_columns"] = valid_cols if valid_cols else [c["column_name"] for c in columns_with_semantic[:3]]
    else:
        result["key_columns"] = [c["column_name"] for c in columns_with_semantic[:3]]

    use_cases = result.get("use_cases")
    result["use_cases"] = use_cases if isinstance(use_cases, list) else ["基础统计分析", "趋势分析", "明细核对"]
    result["warnings"] = str(result.get("warnings") or "").strip() or "暂无明确风险说明，建议结合业务背景复核。"

    # Normalize summary with LLM fill for missing sections
    result["summary"] = await _normalize_summary_async(
        str(result.get("summary") or ""),
        table_name,
        columns_with_semantic,
        context,
        db,
        semantic_model_ref,
        fallback_text=fallback_summary_text(),
    )
    return result


async def generate_sql(
    question: str,
    table_summary: str,
    db: Session,
    chat_model: str | None = None,
    *,
    copilot_context: SqlCopilotContext,
) -> dict[str, Any]:
    if not _has_llm_key(db):
        return {
            "sql": "SELECT DATE(created_at) AS date, SUM(order_amt) AS gmv FROM orders WHERE created_at >= NOW() - INTERVAL 7 DAY GROUP BY DATE(created_at) ORDER BY date;",
            "explanation": "未配置LLM Key，返回本地兜底SQL模板用于联调",
            "referenced_columns": ["created_at", "order_amt"],
        }
    model_ref = resolve_effective_model(chat_model, db)
    if not model_ref:
        return {
            "sql": "",
            "explanation": "无可用对话模型",
            "referenced_columns": [],
        }
    user_content = _sql_generation_user_message(question, table_summary, copilot_context)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SQL_GENERATION_SYSTEM},
        {
            "role": "user",
            "content": user_content + "\n\n请根据 USER QUESTION 生成 SQL，并输出 JSON 键：sql,explanation,referenced_columns",
        },
    ]
    return await _chat_json_messages(messages, model_ref, db)


def _format_sql(sql: str) -> str:
    """Basic SQL formatter: uppercase keywords, one clause per line."""
    keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "LEFT JOIN",
        "RIGHT JOIN",
        "INNER JOIN",
        "JOIN",
        "ON",
        "GROUP BY",
        "ORDER BY",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "UNION ALL",
        "UNION",
        "WITH",
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
    table_summary: str,
    db: Session,
    chat_model: str | None = None,
    *,
    copilot_context: SqlCopilotContext,
) -> dict[str, str]:
    sanitized_failed_sql = sanitize_sql_text(failed_sql)
    if not _has_llm_key(db):
        return {
            "sql": sanitized_failed_sql,
            "reason": "未配置LLM Key，仅执行基础SQL清洗（去除代码块/分号）。",
        }
    model_ref = resolve_effective_model(chat_model, db)
    if not model_ref:
        return {
            "sql": sanitized_failed_sql,
            "reason": "无可用对话模型，仅执行基础SQL清洗。",
        }

    ctx_block = _sql_generation_user_message(question, table_summary, copilot_context)
    user_content = (
        f"{ctx_block}\n\n"
        f"## FAILED SQL\n{sanitized_failed_sql}\n\n"
        f"## DATABASE ERROR\n{error_message.strip()}\n\n"
        "请修复 FAILED SQL，输出 JSON 键：sql,reason"
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SQL_REPAIR_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    fixed = await _chat_json_messages(messages, model_ref, db)
    candidate = sanitize_sql_text(str(fixed.get("sql") or ""))
    reason = str(fixed.get("reason") or "").strip() or "根据数据库报错自动修复 SQL。"
    return {"sql": candidate, "reason": reason}


async def batch_analyze_columns(
    table_name: str,
    column_inputs: list[tuple[dict[str, Any], dict[str, Any]]],
    db: Session,
    concurrency: int = 5,
    *,
    semantic_model_ref: str,
    business_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)

    async def worker(col: dict[str, Any], prof: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            try:
                return await analyze_column(
                    table_name, col, prof, db,
                    semantic_model_ref=semantic_model_ref,
                    business_context=business_context,
                )
            except Exception:
                import logging
                _logger = logging.getLogger(__name__)
                cn = col.get("column_name", "?")
                _logger.warning("Column analysis failed for %s.%s, using fallback", table_name, cn, exc_info=True)
                ctype = (col.get("data_type") or "").lower()
                stype = "dimension"
                if "id" in cn.lower():
                    stype = "id"
                elif any(x in ctype for x in ["int", "decimal", "float", "double"]):
                    stype = "metric"
                elif "date" in ctype or "time" in ctype:
                    stype = "time"
                return {"desc": f"{cn}（LLM分析失败，提供兜底语义）", "type": stype, "is_usable": False, "reason": "LLM analysis failed for this column"}

    return await asyncio.gather(*(worker(c, p) for c, p in column_inputs))
