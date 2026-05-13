"""MCP 导入引擎：连接 MCP Server → 调用 tool → 转 markdown → 写入知识条目。

支持 stdio（本地进程）和 http（远程 URL）两种 MCP 传输方式。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from datetime import datetime
from typing import Any

from sqlalchemy import cast, delete, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from models import KnowledgeEntry, KnowledgeMcpSource

_logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 120000  # 单条目最大字符数（超出则按段落拆分）
_MAX_PROMPT_CHARS = 2000  # 自定义提示词最大字符数

# 提示词安全过滤正则
_REMOVE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # 控制字符（保留 \n \r \t）
_STRIP_TAGS_RE = re.compile(r"<[^>]*>")  # HTML 标签
_UNICODE_BIDI_RE = re.compile(r"[‪-‮⁦-⁩‎‏]")  # 双向覆盖字符


def _sanitize_mcp_prompt(raw: str | None) -> str:
    """过滤用户输入的 MCP 导入提示词，防止注入攻击。"""
    if not raw or not raw.strip():
        return ""
    s = raw.strip()
    s = _REMOVE_RE.sub("", s)
    s = _STRIP_TAGS_RE.sub("", s)
    s = _UNICODE_BIDI_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:_MAX_PROMPT_CHARS]


def _format_sync_exception(exc: BaseException) -> str:
    """格式化异常为用户可读的信息。展开 ExceptionGroup 的子异常。"""
    # Python 3.11+ ExceptionGroup / TaskGroup 会把真实异常包在 sub-exceptions 里
    if isinstance(exc, BaseExceptionGroup):
        parts = [_format_sync_exception(e) for e in exc.exceptions]
        return " | ".join(parts)[:2000]
    msg = str(exc) or type(exc).__name__
    return msg[:2000]


def _plain_excerpt(body: str, max_len: int = 420) -> str:
    s = (body or "").strip()
    if not s:
        return ""
    s = re.sub(r"[\n\r\t]+", " ", s)
    s = re.sub(r" +", " ", s).strip()
    if len(s) <= max_len:
        return s
    return f"{s[: max_len - 1].rstrip()}…"


# ── 内容格式化 ──────────────────────────────────────────────────────────────

def _json_to_markdown(data: Any, level: int = 0) -> str:
    """将 JSON 数据递归转为可读的 markdown 文本。"""
    if isinstance(data, dict):
        parts: list[str] = []
        for k, v in data.items():
            key_str = str(k)
            prefix = "#" * min(level + 2, 4) + " " if level <= 2 else "**" + key_str + "**: "
            if isinstance(v, (dict, list)):
                parts.append(prefix)
                parts.append(_json_to_markdown(v, level + 1))
            else:
                parts.append(f"{prefix}{_format_value(v)}")
        return "\n".join(parts) + "\n"
    elif isinstance(data, list):
        items = []
        for item in data:
            if isinstance(item, dict):
                items.append(_json_to_markdown(item, level))
            else:
                items.append(f"- {_format_value(item)}")
        return "\n".join(items) + "\n"
    else:
        return _format_value(data)


def _format_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    return str(v)


def _to_markdown(content: str, mode: str) -> str:
    """按指定模式将原始内容转为 markdown。"""
    raw = (content or "").strip()
    if not raw:
        return ""
    if mode == "json_to_md":
        try:
            parsed = json.loads(raw)
            return _json_to_markdown(parsed)
        except json.JSONDecodeError:
            return raw
    return raw


def _split_into_entries(markdown: str, source_name: str, max_chars: int = _MAX_BODY_CHARS) -> list[dict[str, str]]:
    """将长 markdown 按段落拆分为多个条目。"""
    md = markdown.strip()
    if not md:
        return []
    if len(md) <= max_chars:
        title = _extract_title(md) or f"{source_name} 导入"
        excerpt = _plain_excerpt(md)
        return [{"title": title[:500], "summary": excerpt, "body": md}]

    entries: list[dict[str, str]] = []
    sections = re.split(r"\n(?=#{1,4}\s)", md)
    buffer = ""
    part_num = 0

    for sec in sections:
        if len(buffer) + len(sec) > max_chars and buffer.strip():
            part_num += 1
            title = _extract_title(buffer) or f"{source_name} 导入 ({part_num})"
            entries.append({"title": title[:500], "summary": _plain_excerpt(buffer), "body": buffer.strip()})
            buffer = sec
        else:
            buffer = buffer + "\n\n" + sec if buffer else sec

    if buffer.strip():
        part_num += 1
        title = _extract_title(buffer) or f"{source_name} 导入 ({part_num})"
        entries.append({"title": title[:500], "summary": _plain_excerpt(buffer), "body": buffer.strip()})

    return entries


def _extract_title(md: str) -> str:
    """从 markdown 中提取第一个标题作为条目标题。"""
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#{2,4}\s+(.+)$", md, re.MULTILINE)
    if m:
        return m.group(1).strip()
    first_line = md.strip().split("\n")[0].strip()
    if len(first_line) <= 120:
        return first_line
    return ""


# ── MCP 客户端封装 ──────────────────────────────────────────────────────────

async def _list_mcp_tools_stdio(
    command: str,
    env: dict[str, str] | None,
    *,
    args: list[str] | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """仅连接 MCP Server 并列出可用 tools，不调用任何 tool。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    if args:
        parsed_args = args
        parsed_command = command
    else:
        parsed = _parse_command_args(command)
        parsed_command = parsed[0]
        parsed_args = parsed[1:]

    server_params = StdioServerParameters(command=parsed_command, args=parsed_args, env=env or None)
    async with asyncio.timeout(timeout):
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [{"name": t.name, "description": t.description or ""} for t in tools.tools]


async def _list_mcp_tools_http(
    url: str,
    *,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """仅连接 HTTP MCP Server 并列出可用 tools，不调用任何 tool。"""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async with asyncio.timeout(timeout):
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [{"name": t.name, "description": t.description or ""} for t in tools.tools]


async def _call_mcp_tool_stdio(
    command: str,
    env: dict[str, str] | None,
    tool_name: str | None,
    tool_args: dict[str, Any] | None,
    *,
    args: list[str] | None = None,
    user_prompt: str = "",
    timeout: float = 300.0,
    db: Session | None = None,
    source_name: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """通过 stdio 启动 MCP Server，使用 LLM agent 循环调用 tools 收集内容。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    if args:
        parsed_args = args
        parsed_command = command
    else:
        parsed = _parse_command_args(command)
        parsed_command = parsed[0]
        parsed_args = parsed[1:]

    server_params = StdioServerParameters(
        command=parsed_command,
        args=parsed_args,
        env=env or None,
    )

    async with asyncio.timeout(timeout):
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_list = [
                    {"name": t.name, "description": t.description or ""}
                    for t in tools.tools
                ]

                if not tools.tools:
                    raise RuntimeError("MCP Server 未提供任何 tool")

                # 优先使用 LLM agent 模式
                if db is not None:
                    result = await _run_mcp_agent(session, tools, user_prompt, db, source_name)
                    if result.strip():
                        return result, tool_list

                # fallback：直接调用指定 tool（无 LLM 时）
                from mcp.types import TextContent
                resolved_tool = tool_name or tools.tools[0].name
                input_schema: dict[str, Any] | None = None
                for t in tools.tools:
                    if t.name == resolved_tool and t.inputSchema:
                        input_schema = t.inputSchema
                        break
                final_args = _merge_user_prompt_into_args(tool_args or {}, user_prompt, input_schema) if user_prompt.strip() else (tool_args or {})
                result_raw = await session.call_tool(resolved_tool, arguments=final_args)
                parts: list[str] = []
                for item in result_raw.content:
                    if isinstance(item, TextContent):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
                return "\n\n".join(parts), tool_list


async def _call_mcp_tool_http(
    url: str,
    tool_name: str | None,
    tool_args: dict[str, Any] | None,
    *,
    user_prompt: str = "",
    timeout: float = 300.0,
    db: Session | None = None,
    source_name: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """通过 HTTP/SSE 连接 MCP Server，使用 LLM agent 循环调用 tools 收集内容。"""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async with asyncio.timeout(timeout):
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_list = [
                    {"name": t.name, "description": t.description or ""}
                    for t in tools.tools
                ]

                if not tools.tools:
                    raise RuntimeError("MCP Server 未提供任何 tool")

                # 优先使用 LLM agent 模式
                if db is not None:
                    result = await _run_mcp_agent(session, tools, user_prompt, db, source_name)
                    if result.strip():
                        return result, tool_list

                # fallback：直接调用指定 tool（无 LLM 时）
                from mcp.types import TextContent
                resolved_tool = tool_name or tools.tools[0].name
                input_schema: dict[str, Any] | None = None
                for t in tools.tools:
                    if t.name == resolved_tool and t.inputSchema:
                        input_schema = t.inputSchema
                        break
                final_args = _merge_user_prompt_into_args(tool_args or {}, user_prompt, input_schema) if user_prompt.strip() else (tool_args or {})
                result_raw = await session.call_tool(resolved_tool, arguments=final_args)
                parts: list[str] = []
                for item in result_raw.content:
                    if isinstance(item, TextContent):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
                return "\n\n".join(parts), tool_list


def _parse_command_args(command: str) -> list[str]:
    """将命令字符串拆分为参数列表（处理引号包裹的参数）。"""
    import shlex
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _merge_user_prompt_into_args(
    tool_args: dict[str, Any],
    user_prompt: str,
    input_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    """将用户自定义提示词智能合并到 tool 参数中。

    根据 tool 的 input_schema 选择正确的参数名：
    - 若 schema 定义了 query 参数，使用 query
    - 若 schema 定义了 prompt 参数，使用 prompt
    - 否则取 schema 中第一个 string 类型参数
    - 无匹配时存为 _prompt 避免校验报错（不会被实际发送）
    """
    if not user_prompt.strip():
        return tool_args

    args = dict(tool_args)
    schema_props: dict[str, Any] = {}
    if input_schema and isinstance(input_schema, dict):
        schema_props = input_schema.get("properties", {}) or {}

    # 优先匹配常见参数名
    candidate_keys = ["query", "prompt", "search", "jql", "q", "question", "text", "content"]
    for key in candidate_keys:
        if key in schema_props:
            args[key] = user_prompt
            return args

    # 取 schema 中第一个 string 类型参数
    for param_name, param_info in schema_props.items():
        if isinstance(param_info, dict) and param_info.get("type") == "string":
            args[param_name] = user_prompt
            return args

    # 无匹配：不传额外参数，避免 Pydantic 校验报错
    _logger.info("MCP tool has no recognizable string parameter; user prompt stored in meta only")
    return args


_AGENT_SYSTEM = """你是一个知识库内容采集助手。你可以调用 MCP Server 提供的工具来获取用户需要的内容。

工作流程：
1. 根据用户的需求，选择合适的工具并调用
2. 分析工具返回的结果，判断是否需要继续调用其他工具（例如先搜索获取 ID，再用 ID 获取详细内容）
3. 重复调用直到收集到足够的内容
4. 当内容收集完毕后，将所有收集到的内容整理为结构清晰的 Markdown 文档输出

注意：
- 优先获取实际内容，而不仅仅是列表或索引
- 如果返回的是 ID 列表，应继续调用工具获取每个 ID 对应的详细内容
- 最终输出应该是完整的 Markdown 文档，包含实际内容而非仅仅是标题列表
- 输出纯 Markdown，不要包含任何前言或后记
"""

_MAX_AGENT_ROUNDS = 10  # 最多循环轮数，防止无限循环
_MAX_TOOL_RESULT_CHARS = 20000  # 单次 tool 结果最大字符数


async def _run_mcp_agent(
    session: Any,
    tools_raw: Any,
    user_prompt: str,
    db: Session,
    source_name: str,
) -> str:
    """LLM 驱动的 MCP agent 循环：自动决策调用哪些 tool、组合结果输出 markdown。"""
    from mcp.types import TextContent
    from services.llm_models import has_any_llm_key, resolve_effective_model
    from services.llm_service import _client_and_model_for_ref

    # 检查 LLM 是否可用
    if not has_any_llm_key(db):
        _logger.warning("MCP agent: no LLM key, falling back to single tool call")
        return ""

    model_ref = resolve_effective_model(None, db)
    if not model_ref:
        _logger.warning("MCP agent: no model resolved, falling back to single tool call")
        return ""

    client, model_name = _client_and_model_for_ref(model_ref, db)

    # 构建 OpenAI function calling 格式的 tools 列表
    openai_tools = []
    for t in tools_raw.tools:
        schema = t.inputSchema if t.inputSchema else {"type": "object", "properties": {}}
        # 移除 $defs 等复杂引用，简化 schema 避免部分模型不支持
        simple_schema = {
            "type": "object",
            "properties": schema.get("properties", {}),
        }
        if schema.get("required"):
            simple_schema["required"] = schema["required"]
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": (t.description or "")[:500],
                "parameters": simple_schema,
            },
        })

    goal = user_prompt.strip() if user_prompt.strip() else "获取该 MCP Server 中所有可用的内容，整理为知识库文档"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _AGENT_SYSTEM},
        {"role": "user", "content": f"目标：{goal}\n\n请开始收集内容。"},
    ]

    collected_parts: list[str] = []

    for round_num in range(_MAX_AGENT_ROUNDS):
        _logger.info("MCP agent round %d/%d for %s", round_num + 1, _MAX_AGENT_ROUNDS, source_name)

        resp = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=openai_tools if openai_tools else None,
            tool_choice="auto" if openai_tools else None,
            temperature=0.1,
        )

        msg = resp.choices[0].message
        finish_reason = resp.choices[0].finish_reason

        # LLM 决定停止调用 tool，输出最终内容
        if finish_reason == "stop" or not msg.tool_calls:
            final_text = (msg.content or "").strip()
            if final_text:
                collected_parts.append(final_text)
            break

        # 追加 assistant 消息（含 tool_calls），保留 reasoning_content（思考模式模型需要）
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        }
        # DeepSeek R1 等思考模式模型会在响应中附带 reasoning_content，必须原样传回
        # model_extra 包含 SDK 不认识的非标准字段
        reasoning = None
        if hasattr(msg, "model_extra") and isinstance(msg.model_extra, dict):
            reasoning = msg.model_extra.get("reasoning_content")
        if not reasoning and hasattr(msg, "reasoning_content"):
            reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        messages.append(assistant_msg)

        # 执行每个 tool call
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                tool_args = {}

            _logger.info("MCP agent calling tool: %s args: %s", tool_name, str(tool_args)[:200])

            try:
                result = await session.call_tool(tool_name, arguments=tool_args)
                parts: list[str] = []
                for item in result.content:
                    if isinstance(item, TextContent):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
                tool_result = "\n".join(parts)
                # 截断过长结果
                if len(tool_result) > _MAX_TOOL_RESULT_CHARS:
                    tool_result = tool_result[:_MAX_TOOL_RESULT_CHARS] + "\n\n[结果已截断...]"
            except Exception as e:
                tool_result = f"[工具调用失败: {e}]"
                _logger.warning("MCP agent tool %s failed: %s", tool_name, e)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

    return "\n\n".join(collected_parts)


async def _analyze_content_with_llm(db: Session, raw_content: str, source_name: str) -> str:
    """使用 LLM 分析原始导入内容，输出结构化的 Markdown。"""
    from services.llm_models import has_any_llm_key, resolve_effective_model
    from services.llm_service import _chat_text

    if not has_any_llm_key(db):
        _logger.info("MCP import: no LLM key configured, using raw content as-is for %s", source_name)
        return raw_content

    model_ref = resolve_effective_model(None, db)
    if not model_ref:
        _logger.info("MCP import: no effective model resolved, using raw content as-is for %s", source_name)
        return raw_content

    # 限制输入长度避免超出 LLM 上下文
    max_input = 80000
    truncated = raw_content if len(raw_content) <= max_input else raw_content[:max_input] + "\n\n[内容已截断...]"

    prompt = f"{_ANALYSIS_PROMPT}\n来源：{source_name}\n\n{truncated}"

    try:
        result = await _chat_text(prompt, model_ref, db, temperature=0.3)
        if not result.strip():
            _logger.warning("MCP import: LLM returned empty result for %s, falling back to raw content", source_name)
            return raw_content
        return result
    except Exception as exc:
        _logger.warning("MCP import: LLM analysis failed for %s: %s, falling back to raw content", source_name, exc)
        return raw_content


def _set_import_status(db: Session, source_id: int, kb_id: int, status: str, *, error: str | None = None, entries: int | None = None) -> None:
    """更新 MCP 源的导入状态字段。"""
    values: dict[str, Any] = {
        "last_import_status": status,
        "last_import_at": datetime.utcnow(),
        "last_import_kb_id": kb_id,
    }
    if error is not None:
        values["last_import_error"] = error[:2000]
    else:
        values["last_import_error"] = None
    if entries is not None:
        values["last_import_entries"] = entries
    else:
        values["last_import_entries"] = None
    db.execute(
        update(KnowledgeMcpSource)
        .where(KnowledgeMcpSource.id == source_id)
        .values(**values)
    )
    db.commit()


# ── 主同步函数 ──────────────────────────────────────────────────────────────

async def _run_mcp_import_async(db: Session, source_id: int, target_kb_id: int, prompt: str | None = None) -> dict[str, Any]:
    """异步执行 MCP 导入：连接 server → 调用 tool → LLM 分析 → 写入条目。"""
    src = db.get(KnowledgeMcpSource, source_id)
    if not src:
        return {"ok": False, "error": "MCP 源不存在"}

    kb_id = target_kb_id

    # 设置导入中状态
    _set_import_status(db, source_id, kb_id, "importing")

    now = datetime.utcnow()
    env = dict(src.mcp_env or {})
    tool_args = dict(src.mcp_tool_args or {})

    # 安全过滤用户自定义提示词（参数名由 tool schema 决定，不再硬编码为 prompt）
    sanitized_prompt = _sanitize_mcp_prompt(prompt)

    try:
        if src.mcp_transport == "stdio":
            if not (src.mcp_command or "").strip():
                error_msg = "stdio 模式下 mcp_command 不能为空"
                _set_import_status(db, source_id, kb_id, "failed", error=error_msg)
                return {"ok": False, "error": error_msg}
            raw_result, tool_list = await _call_mcp_tool_stdio(
                command=src.mcp_command or "",
                env=env,
                tool_name=src.mcp_tool_name,
                tool_args=tool_args,
                args=src.mcp_args,
                user_prompt=sanitized_prompt,
                db=db,
                source_name=src.name,
            )
        elif src.mcp_transport == "http":
            if not (src.mcp_url or "").strip():
                error_msg = "http 模式下 mcp_url 不能为空"
                _set_import_status(db, source_id, kb_id, "failed", error=error_msg)
                return {"ok": False, "error": error_msg}
            raw_result, tool_list = await _call_mcp_tool_http(
                url=src.mcp_url or "",
                tool_name=src.mcp_tool_name,
                tool_args=tool_args,
                user_prompt=sanitized_prompt,
                db=db,
                source_name=src.name,
            )
        else:
            error_msg = f"不支持的传输方式: {src.mcp_transport}"
            _set_import_status(db, source_id, kb_id, "failed", error=error_msg)
            return {"ok": False, "error": error_msg}
    except Exception as exc:
        import traceback
        _logger.warning("MCP import failed for source_id=%s kb_id=%s: %s\n%s", source_id, kb_id, exc, traceback.format_exc())
        detail = _format_sync_exception(exc)
        _set_import_status(db, source_id, kb_id, "failed", error=detail)
        return {"ok": False, "error": detail}

    if not raw_result.strip():
        error_msg = "MCP tool 返回了空结果"
        _logger.warning("MCP import empty result for source_id=%s kb_id=%s", source_id, kb_id)
        _set_import_status(db, source_id, kb_id, "failed", error=error_msg)
        return {"ok": False, "error": error_msg}

    # 格式化为 markdown
    raw_md = _to_markdown(raw_result, mode=src.content_mode or "markdown")

    # LLM 分析：将原始 markdown 整理为结构化知识库内容
    md_content = await _analyze_content_with_llm(db, raw_md, src.name)

    # 删除该源之前导入的条目
    old_ids = list(
        db.scalars(
            select(KnowledgeEntry.id).where(
                KnowledgeEntry.knowledge_base_id == kb_id,
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "mcp_import",
                cast(KnowledgeEntry.source_meta, JSONB)["mcp_source_id"].astext == str(source_id),
            )
        ).all()
    )
    from services.embedding_service import delete_embeddings_for_knowledge_entries
    delete_embeddings_for_knowledge_entries(db, old_ids)
    if old_ids:
        db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(old_ids)))
        db.flush()

    # 获取排序序号
    max_order = db.execute(
        select(KnowledgeEntry.sort_order)
        .where(KnowledgeEntry.knowledge_base_id == kb_id)
        .order_by(KnowledgeEntry.sort_order.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1

    # 拆分为条目并写入
    entries = _split_into_entries(md_content, src.name, max_chars=src.max_entry_chars or _MAX_BODY_CHARS)
    created = 0
    try:
        for entry_data in entries:
            meta = {
                "kind": "mcp_import",
                "mcp_source_id": str(source_id),
                "mcp_server": src.name,
                "mcp_transport": src.mcp_transport,
                "imported_at": now.isoformat(),
            }
            if sanitized_prompt:
                meta["mcp_prompt"] = sanitized_prompt
            entry = KnowledgeEntry(
                knowledge_base_id=kb_id,
                title=entry_data["title"][:500],
                summary=entry_data["summary"],
                body=entry_data["body"],
                sort_order=next_order,
                source_meta=meta,
                updated_at=now,
            )
            db.add(entry)
            db.flush()
            from services.embedding_service import replace_knowledge_entry_embedding
            replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
            next_order += 1
            created += 1

        db.commit()
        _set_import_status(db, source_id, kb_id, "success", entries=created)
        return {
            "ok": True,
            "entries": created,
            "message": f"已导入 {created} 个知识条目（共 {len(raw_result)} 字原始内容）",
        }
    except Exception as exc:
        db.rollback()
        detail = _format_sync_exception(exc)
        _logger.warning("MCP import write failed for source_id=%s kb_id=%s: %s", source_id, kb_id, detail)
        _set_import_status(db, source_id, kb_id, "failed", error=detail)
        return {"ok": False, "error": detail}


def run_mcp_import(db: Session, source_id: int, target_kb_id: int, prompt: str | None = None) -> dict[str, Any]:
    """同步封装：MCP 导入入口。"""
    return asyncio.run(_run_mcp_import_async(db, source_id, target_kb_id, prompt=prompt))


async def test_mcp_connection_async(source: KnowledgeMcpSource) -> dict[str, Any]:
    """测试 MCP Server 连接并列出可用 tools（不调用任何 tool）。"""
    env = dict(source.mcp_env or {}) if source.mcp_env else None

    try:
        if source.mcp_transport == "stdio":
            if not (source.mcp_command or "").strip():
                return {"ok": False, "error": "stdio 模式下 mcp_command 不能为空"}
            tool_list = await _list_mcp_tools_stdio(
                command=source.mcp_command or "",
                env=env,
                args=source.mcp_args,
                timeout=30.0,
            )
        elif source.mcp_transport == "http":
            if not (source.mcp_url or "").strip():
                return {"ok": False, "error": "http 模式下 mcp_url 不能为空"}
            tool_list = await _list_mcp_tools_http(
                url=source.mcp_url or "",
                timeout=30.0,
            )
        else:
            return {"ok": False, "error": f"不支持的传输方式: {source.mcp_transport}"}

        return {"ok": True, "tools": tool_list, "preview": ""}
    except Exception as exc:
        detail = _format_sync_exception(exc)
        return {"ok": False, "error": detail, "tools": []}


# ── 调度辅助 ────────────────────────────────────────────────────────────────

def _trigger_background_import(source_id: int, target_kb_id: int, prompt: str | None = None) -> None:
    """在后台线程中执行 MCP 导入（用于 API 端点非阻塞响应）。"""
    from database import SessionLocal

    def _run():
        db2 = SessionLocal()
        try:
            run_mcp_import(db2, source_id, target_kb_id, prompt=prompt)
        except Exception:
            _logger.exception("Background MCP import failed for source_id=%s kb_id=%s", source_id, target_kb_id)
        finally:
            db2.close()

    t = threading.Thread(target=_run, daemon=True, name=f"mcp-import-{source_id}")
    t.start()
