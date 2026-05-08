import json
from typing import Any
from collections.abc import Awaitable, Callable

import asyncio
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    BusinessDomainKnowledgeBase,
    ColumnMeta,
    DataSource,
    KnowledgeBase,
    KnowledgeEntry,
    QueryExample,
    TableKnowledgeBase,
    TableKnowledgeEntry,
    TableMeta,
    TableSummary,
)
from services.embedding_service import embed_and_store_async, search_knowledge_semantic, search_similar_async
from services.llm_service import (
    SqlCopilotContext,
    _heuristic_intent,
    answer_general_question,
    classify_question_intent,
    generate_sql,
    guardrail_for_question,
    repair_failed_sql,
    sanitize_sql_text,
)
from services.schema_extractor import _is_postgres_family, execute_readonly_sql
from services.sql_ast_guard import source_type_to_sqlglot_dialect, validate_readonly_sql_ast


def _latest_table_summaries(db: Session) -> dict[int, TableSummary]:
    subq = (
        select(
            TableSummary.table_id.label("tid"),
            func.max(TableSummary.generated_at).label("max_at"),
        )
        .group_by(TableSummary.table_id)
        .subquery()
    )
    stmt = (
        select(TableSummary)
        .join(subq, TableSummary.table_id == subq.c.tid)
        .where(TableSummary.generated_at == subq.c.max_at)
    )
    rows = db.execute(stmt).scalars().all()
    return {row.table_id: row for row in rows}


def _build_priority_context(db: Session, table_id: int | None) -> tuple[str, str, str, int | None]:
    latest_summaries = _latest_table_summaries(db)
    preferred_table = db.get(TableMeta, table_id) if table_id else None
    preferred_datasource_id = preferred_table.datasource_id if preferred_table else None

    table_rows = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().all()
    if preferred_datasource_id is not None:
        table_rows = [t for t in table_rows if t.datasource_id == preferred_datasource_id] + [
            t for t in table_rows if t.datasource_id != preferred_datasource_id
        ]

    seen_tables: set[tuple[int | None, str, str]] = set()
    selected_tables: list[TableMeta] = []
    for t in table_rows:
        key = (t.datasource_id, t.database_name, t.table_name)
        if key in seen_tables:
            continue
        seen_tables.add(key)
        selected_tables.append(t)
        if len(selected_tables) >= 10:
            break

    datasource_ids = [t.datasource_id for t in selected_tables if t.datasource_id is not None]
    datasource_ids_unique = list(dict.fromkeys(datasource_ids))
    datasources = (
        db.execute(select(DataSource).where(DataSource.id.in_(datasource_ids_unique))).scalars().all()
        if datasource_ids_unique
        else []
    )
    ds_map = {d.id: d for d in datasources}

    context_lines = ["[优先上下文-数据源采集信息]"]
    if preferred_table:
        context_lines.append(
            f"当前指定表: {preferred_table.database_name}.{preferred_table.table_name} (table_id={preferred_table.id})"
        )
    for d in datasources:
        context_lines.append(
            f"- 数据源[{d.id}] {d.name} ({d.source_type}) 数据库={d.database} | 备注: {d.description or '无'}"
        )

    analysis_lines = ["[优先上下文-AI分析信息]"]
    merged_summary_parts: list[str] = []
    for t in selected_tables:
        summary = latest_summaries.get(t.id)
        use_cases = summary.use_cases if summary and summary.use_cases else ""
        key_cols = summary.key_columns if summary and summary.key_columns else ""
        table_line = f"- {t.database_name}.{t.table_name} 状态={t.status}"
        if summary and summary.summary:
            table_line += f" | 摘要={summary.summary}"
            merged_summary_parts.append(summary.summary)
        if use_cases:
            table_line += f" | 场景={use_cases}"
        if key_cols:
            table_line += f" | 关键字段={key_cols}"
        analysis_lines.append(table_line)

    selected_table_ids = [t.id for t in selected_tables]
    if table_id:
        selected_table_ids = [table_id]
    cols = (
        db.execute(select(ColumnMeta).where(ColumnMeta.table_id.in_(selected_table_ids))).scalars().all()
        if selected_table_ids
        else []
    )
    schema_lines = []
    for c in cols:
        schema_lines.append(
            f"{c.table_id}.{c.column_name} | {c.data_type or ''} | semantic={c.semantic_type or ''} | desc={c.semantic_desc or ''}"
        )

    context_text = "\n".join(context_lines)
    analysis_text = "\n".join(analysis_lines)
    schema_text = "\n".join(schema_lines)
    summary_text = "；".join(merged_summary_parts[:6])

    resolved_table_id = table_id
    if resolved_table_id is None and preferred_table:
        resolved_table_id = preferred_table.id
    if resolved_table_id is None and selected_tables:
        resolved_table_id = selected_tables[0].id
    return context_text + "\n" + analysis_text, schema_text, summary_text, resolved_table_id


def _collect_knowledge_context_text(
    db: Session, question: str, business_domain_id: int | None, table_id: int | None
) -> str:
    """聚合：会话业务域关联的知识库 + 当前表关联的知识库与固定条目 + 各库语义检索片段。"""
    kb_ids: list[int] = []
    seen_kb: set[int] = set()

    def add_kb(kid: int) -> None:
        if kid in seen_kb:
            return
        seen_kb.add(kid)
        kb_ids.append(kid)

    if business_domain_id:
        for kid in db.execute(
            select(BusinessDomainKnowledgeBase.knowledge_base_id).where(
                BusinessDomainKnowledgeBase.domain_id == business_domain_id
            )
        ).scalars().all():
            add_kb(int(kid))

    pinned_ids: list[int] = []
    seen_ent: set[int] = set()
    if table_id:
        for kid in db.execute(
            select(TableKnowledgeBase.knowledge_base_id).where(TableKnowledgeBase.table_id == table_id)
        ).scalars().all():
            add_kb(int(kid))
        for eid in db.execute(
            select(TableKnowledgeEntry.knowledge_entry_id).where(TableKnowledgeEntry.table_id == table_id)
        ).scalars().all():
            eid = int(eid)
            if eid in seen_ent:
                continue
            seen_ent.add(eid)
            pinned_ids.append(eid)

    sections: list[str] = []
    max_total = 16000
    pinned_set = set(pinned_ids)

    if pinned_ids:
        entries = list(db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(pinned_ids))).scalars().all())
        entry_by_id = {e.id: e for e in entries}
        pin_lines = ["[表关联知识条目 — 固定全文]"]
        for eid in pinned_ids:
            e = entry_by_id.get(eid)
            if not e:
                continue
            kb = db.get(KnowledgeBase, e.knowledge_base_id)
            kb_name = kb.name if kb else "?"
            body = (e.body or "").strip()
            if len(body) > 6000:
                body = body[:6000] + "\n…（正文已截断）"
            pin_lines.append(f"## {e.title}（知识库：{kb_name}，entry_id={e.id}）\n{body}")
        sections.append("\n".join(pin_lines))

    if kb_ids and question.strip():
        sem_lines = ["[知识库语义检索 — 与问题相关的片段]"]
        merged_hits: dict[int, dict[str, Any]] = {}
        for kb_id in kb_ids:
            for hit in search_knowledge_semantic(db, kb_id, question.strip(), top_k=6):
                eid = int(hit["entry_id"])
                if eid in pinned_set:
                    continue
                merged_hits.setdefault(eid, hit)
        for hit in list(merged_hits.values())[:20]:
            title = str(hit.get("title") or "")
            snippet = str(hit.get("snippet") or "").strip().replace("\r\n", "\n")
            if len(snippet) > 800:
                snippet = snippet[:800] + "…"
            sem_lines.append(f"- {title} (entry_id={hit['entry_id']})\n  {snippet}")
        if len(sem_lines) > 1:
            sections.append("\n".join(sem_lines))

    text = "\n\n".join(sections).strip()
    if len(text) > max_total:
        return f"{text[:max_total]}\n…（知识上下文已截断）"
    return text


async def answer(
    db: Session,
    question: str,
    table_id: int | None = None,
    business_domain_id: int | None = None,
    stage_callback: Callable[[str], Awaitable[None]] | None = None,
    trace_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    chat_model: str | None = None,
) -> dict[str, Any]:
    pipeline_traces: list[dict[str, Any]] = []

    async def emit(stage: str) -> None:
        if stage_callback:
            await stage_callback(stage)

    async def trace_row(step_id: str, label: str, detail: str = "") -> None:
        d = (detail or "").strip()
        if len(d) > 2800:
            d = d[:2800] + "…"
        row: dict[str, Any] = {"id": step_id, "label": label, "detail": d}
        pipeline_traces.append(row)
        if trace_callback:
            await trace_callback(row)

    async def trace_live(step_id: str, label: str, detail: str = "") -> None:
        """仅用于 SSE 流式进度，不写入 pipeline_traces，避免阻塞时前端长时间无反馈。"""
        if trace_callback:
            d = (detail or "").strip()
            await trace_callback({"id": step_id, "label": label, "detail": d})

    await emit("intent_recognizing")
    await asyncio.sleep(0)
    q_preview = (question or "").strip()
    if len(q_preview) > 900:
        q_preview = q_preview[:900] + "…"
    refs = await search_similar_async(db, question, top_k=5, table_id=table_id, ref_type="query")
    await trace_live("live_prep", "准备上下文", "已完成相似问法检索，正在加载表结构与业务知识…")
    await asyncio.sleep(0)
    priority_context, schema, summary_text, preferred_table_id = _build_priority_context(db, table_id)
    await asyncio.sleep(0)
    knowledge_text = _collect_knowledge_context_text(db, question, business_domain_id, table_id)
    await asyncio.sleep(0)
    ref_n = len(refs) if isinstance(refs, list) else 0
    await trace_live("live_intent", "意图识别", "正在调用大模型判断是否需要生成 SQL…")
    await asyncio.sleep(0)
    _intent_timeout_s = 72.0
    try:
        intent_info = await asyncio.wait_for(
            classify_question_intent(question, db, chat_model),
            timeout=_intent_timeout_s,
        )
    except asyncio.TimeoutError:
        intent_info = {
            "intent": _heuristic_intent(question),
            "reason": f"意图识别请求超过 {_intent_timeout_s:.0f}s 未返回，已使用规则分流",
        }
    intent = intent_info.get("intent", "general_qa")
    reason_txt = str(intent_info.get("reason") or "").strip()
    if len(reason_txt) > 1200:
        reason_txt = reason_txt[:1200] + "…"

    if intent != "sql_query":
        await trace_row(
            "reasoning_1",
            "1. 明确用户输入，给出理解",
            f"用户问题摘要：{q_preview or '（空）'}\n判定为「通用问答」。说明：{reason_txt or '（无）'}",
        )
        await trace_row(
            "reasoning_2",
            "2. 确认拿到的上下文信息",
            f"已加载：业务/知识库约 {len(knowledge_text)} 字；相似历史问法 {ref_n} 条；表与数据源说明约 {len(priority_context)} 字；Schema 约 {len(schema)} 字。",
        )
        await trace_row(
            "reasoning_gq",
            "3. 执行方式",
            "不进行单表 SQL 查询；结合上述上下文由模型生成自然语言回答。",
        )
        guardrail = guardrail_for_question(question)
        await emit("answer_generating")
        if guardrail:
            natural_answer = guardrail["answer"]
            explanation = guardrail["reason"]
        else:
            hint_parts = [p for p in (knowledge_text.strip(), priority_context.strip()) if p]
            natural_answer = await answer_general_question(
                question, db, context_hint="\n\n".join(hint_parts), chat_model=chat_model
            )
            explanation = intent_info.get("reason", "该问题更适合自然语言回答，无需执行 SQL")
        await embed_and_store_async(db, "query", table_id or 0, f"{question} -> {natural_answer}")
        return {
            "intent": "general_qa",
            "answer": natural_answer,
            "sql": "",
            "explanation": explanation,
            "query_result": {"ok": False, "columns": [], "rows": [], "error": "该问题无需SQL执行"},
            "pipeline_trace": pipeline_traces,
        }

    await trace_row(
        "reasoning_1",
        "1. 明确用户输入，给出理解",
        f"用户问题摘要：{q_preview or '（空）'}\n判定为「SQL 数据分析」。说明：{reason_txt or '（无）'}",
    )
    await trace_row(
        "reasoning_2",
        "2. 确认拿到的上下文信息",
        f"已加载：业务/知识库约 {len(knowledge_text)} 字；相似历史问法 {ref_n} 条；表与数据源说明约 {len(priority_context)} 字；列语义 Schema 约 {len(schema)} 字。",
    )

    await emit("answer_generating")
    few_shot = json.dumps(refs, ensure_ascii=False)
    copilot_context = SqlCopilotContext(
        knowledge=knowledge_text.strip(),
        datasource_priority=priority_context.strip(),
        schema=schema.strip(),
        few_shot_json=few_shot,
    )
    result = await generate_sql(
        question,
        summary_text,
        db,
        chat_model,
        copilot_context=copilot_context,
    )

    # query_examples.table_id has FK constraint, so we must persist a real table id.
    resolved_table_id = table_id
    if resolved_table_id is None and preferred_table_id:
        resolved_table_id = preferred_table_id
    if resolved_table_id is None:
        latest_table = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().first()
        if latest_table:
            resolved_table_id = latest_table.id

    scope_lines: list[str] = []
    if table_id:
        tm = db.get(TableMeta, table_id)
        if tm:
            scope_lines.append(
                f"选表：请求携带 table_id={table_id}，已锁定「{tm.database_name}.{tm.table_name}」；列语义、表摘要与知识库片段优先从该表注入，模型应围绕该表生成 SQL。"
            )
        else:
            scope_lines.append(f"请求携带 table_id={table_id}，但库中未找到对应表元数据。")
    elif preferred_table_id:
        tm = db.get(TableMeta, preferred_table_id)
        if tm:
            scope_lines.append(
                f"选表：未在请求中指定 table_id；已按数据源与元数据顺序将主上下文对齐到「{tm.database_name}.{tm.table_name}」（id={preferred_table_id}），Schema 片段主要来自该表及同批候选表。"
            )
    else:
        scope_lines.append(
            "选表：当前未稳定对齐到单一主表；模型仍可根据 Schema 与知识库在候选表之间推断，执行阶段会绑定到已配置的数据源。"
        )
    if resolved_table_id and not table_id:
        rt = db.get(TableMeta, resolved_table_id)
        if rt and (preferred_table_id is None or resolved_table_id != preferred_table_id):
            scope_lines.append(
                f"示例与向量写入绑定到 table_id={resolved_table_id}（{rt.database_name}.{rt.table_name}），"
                "与上文自动选表不一致时多为「无指定表」下的最近表回退。"
            )
    await trace_row("reasoning_3", "3. 明确使用的表", "\n".join(scope_lines))

    if resolved_table_id is not None:
        db.add(
            QueryExample(
                table_id=resolved_table_id,
                question=question,
                sql_text=result.get("sql", ""),
                explanation=result.get("explanation", ""),
            )
        )
        db.commit()
    await embed_and_store_async(db, "query", resolved_table_id or 0, f"{question} -> {result.get('sql', '')}")

    # Execute generated SQL and return data preview.
    sql_text = sanitize_sql_text(str(result.get("sql") or ""))
    result["sql"] = sql_text
    exp_raw = str(result.get("explanation") or "").strip()
    exp_show = (exp_raw[:1600] + ("…" if len(exp_raw) > 1600 else "")) if exp_raw else "（模型未给出说明）"
    sql_show = (sql_text[:3200] + ("…" if len(sql_text) > 3200 else "")) if sql_text else "（清洗后暂无可执行 SQL）"
    await trace_row(
        "reasoning_4",
        "4. 查询逻辑以及 SQL",
        f"【判定与取数逻辑】\n{exp_show}\n\n【SQL（清洗后用于执行）】\n{sql_show}",
    )

    execution: dict[str, Any] = {"ok": False, "columns": [], "rows": [], "error": "未生成 SQL"}
    if sql_text:
        await emit("sql_executing")
        datasource: DataSource | None = None
        database_name: str | None = None
        if resolved_table_id is not None:
            target_table = db.get(TableMeta, resolved_table_id)
            if target_table and target_table.datasource_id:
                datasource = db.get(DataSource, target_table.datasource_id)
                database_name = target_table.database_name
        if datasource is None:
            datasource = db.execute(select(DataSource).order_by(DataSource.created_at.desc())).scalars().first()

        if datasource:
            dialect = source_type_to_sqlglot_dialect(datasource.source_type)
            dialect_label = str(dialect) if dialect else str(datasource.source_type)
            await trace_row(
                "reasoning_5",
                "5. 核实执行 SQL 的策略",
                f"数据源：{datasource.name or datasource.id}\n"
                f"连接类型：{datasource.source_type}\n"
                f"解析出的 SQL 方言（用于语法树校验）：{dialect_label}\n"
                f"库/命名空间：{database_name or datasource.database or '（默认）'}",
            )
            if _is_postgres_family(datasource.source_type):
                conn_info = {
                    "source_type": datasource.source_type,
                    "host": datasource.host,
                    "port": datasource.port,
                    "database": datasource.database,
                    "namespace": database_name or "public",
                    "username": datasource.username,
                    "password": datasource.password,
                }
            elif datasource.source_type == "trino":
                conn_info = {
                    "source_type": "trino",
                    "host": datasource.host,
                    "port": datasource.port,
                    "database": datasource.database,
                    "namespace": database_name or datasource.database,
                    "username": datasource.username,
                    "password": datasource.password,
                }
            else:
                conn_info = {
                    "source_type": datasource.source_type,
                    "host": datasource.host,
                    "port": datasource.port,
                    "database": database_name or datasource.database,
                    "username": datasource.username,
                    "password": datasource.password,
                }
            attempted_sql = sql_text
            repair_attempts: list[dict[str, str]] = []
            emitted_reasoning_6 = False
            last_ast_error = ""

            for attempt_idx in range(3):
                ast_ok_loop, ast_err_loop = validate_readonly_sql_ast(attempted_sql, dialect=dialect)
                if not ast_ok_loop:
                    last_ast_error = str(ast_err_loop or "")
                    execution = {
                        "ok": False,
                        "columns": [],
                        "rows": [],
                        "error": f"SQL 安全校验未通过：{ast_err_loop}",
                    }
                else:
                    last_ast_error = ""
                    if not emitted_reasoning_6:
                        await trace_row(
                            "reasoning_6",
                            "6. 最终 SQL 执行校验",
                            f"方言 {dialect_label}：只读与安全 AST 已通过，准备向数据源下发（第 {attempt_idx + 1} 轮）。",
                        )
                        emitted_reasoning_6 = True
                    try:
                        execution = await asyncio.to_thread(execute_readonly_sql, conn_info, attempted_sql)
                    except Exception as exc:  # noqa: BLE001
                        execution = {"ok": False, "columns": [], "rows": [], "error": str(exc)}

                if execution.get("ok"):
                    rows_n = len(execution.get("rows") or [])
                    cols_n = len(execution.get("columns") or [])
                    await trace_row(
                        "reasoning_7",
                        "7. 执行 SQL",
                        f"成功：返回 {rows_n} 行、{cols_n} 列（预览最多 20 行由前端展示）。",
                    )
                    if attempt_idx > 0:
                        result["sql"] = attempted_sql
                        attempt_desc = "；".join(
                            [
                                f"第{idx + 1}次修复：{item.get('reason', '自动修复')}"
                                for idx, item in enumerate(repair_attempts)
                            ]
                        )
                        base_exp = str(result.get("explanation") or "").strip()
                        result["explanation"] = (
                            f"{base_exp}\n\n自动修复说明\n- 原SQL执行失败，系统已自动修复并重试成功。\n- {attempt_desc or '已完成自动修复重试。'}"
                        ).strip()
                    break

                if attempt_idx == 2:
                    break

                current_error = str(execution.get("error") or "SQL执行失败")
                fix = await repair_failed_sql(
                    question=question,
                    failed_sql=attempted_sql,
                    error_message=current_error,
                    table_summary=summary_text,
                    db=db,
                    chat_model=chat_model,
                    copilot_context=copilot_context,
                )
                next_sql = sanitize_sql_text(fix.get("sql", ""))
                reason = fix.get("reason", "自动修复")
                repair_attempts.append({"reason": reason, "error": current_error, "sql": next_sql})

                if not next_sql or next_sql == attempted_sql:
                    break
                attempted_sql = next_sql

            if not execution.get("ok") and repair_attempts:
                final_err = str(execution.get("error") or "未知错误").strip()
                if len(final_err) > 1200:
                    final_err = final_err[:1200] + "…"
                execution["error"] = final_err
            if not execution.get("ok") and last_ast_error:
                if not emitted_reasoning_6:
                    await trace_row(
                        "reasoning_6",
                        "6. 最终 SQL 执行校验",
                        f"方言 {dialect_label}：只读 AST 未通过 — {last_ast_error[:900]}{'…' if len(last_ast_error) > 900 else ''}",
                    )
                elif emitted_reasoning_6:
                    # 首轮曾通过 AST，修复后 SQL 在后续轮次未再通过 AST
                    await trace_row(
                        "reasoning_6_last",
                        "6. 最终 SQL 执行校验（后续轮次）",
                        f"方言 {dialect_label}：AST 未通过 — {last_ast_error[:900]}{'…' if len(last_ast_error) > 900 else ''}",
                    )
        else:
            execution = {"ok": False, "columns": [], "rows": [], "error": "未配置可用数据源"}
            await trace_row(
                "reasoning_5",
                "5. 核实执行 SQL 的策略",
                "未找到可用数据源，无法绑定执行环境与方言。",
            )
            await trace_row("reasoning_6", "6. 最终 SQL 执行校验", "未配置数据源，跳过 AST 与下发校验。")
    else:
        await trace_row("reasoning_5", "5. 核实执行 SQL 的策略", "无有效 SQL 文本，跳过数据源与方言绑定。")
        await trace_row("reasoning_6", "6. 最终 SQL 执行校验", "无可执行语句，未进行 AST 校验。")

    result["query_result"] = execution
    result["intent"] = "sql_query"
    result["answer"] = "已根据你的问题生成并执行 SQL，结果如下。"
    result["pipeline_trace"] = pipeline_traces
    return result
