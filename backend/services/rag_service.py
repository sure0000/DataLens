import json
from typing import Any
from collections.abc import Awaitable, Callable

import asyncio
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    BusinessDomain,
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
from services.sql_ast_guard import (
    extract_table_refs_from_sql,
    format_sql_for_display,
    source_type_to_sqlglot_dialect,
    validate_readonly_sql_ast,
)


def _insert_reasoning_4_after_reasoning_3(traces: list[dict[str, Any]], detail: str) -> None:
    """在 reasoning_3 之后插入第 4 步，保证 trace 顺序为 …→3→4→5…（SQL 在修复/执行后再写入）。"""
    d = (detail or "").strip()
    if len(d) > 2800:
        d = d[:2800] + "…"
    row: dict[str, Any] = {"id": "reasoning_4", "label": "4. 查询逻辑以及 SQL", "detail": d}
    for i, t in enumerate(traces):
        if t.get("id") == "reasoning_3":
            traces.insert(i + 1, row)
            return
    traces.append(row)


def _resolve_table_meta_for_trace(
    db: Session,
    *,
    datasource_id: int,
    default_database: str | None,
    db_part: str | None,
    table_name: str,
) -> TableMeta | None:
    """将 SQL 中的 db.table 解析为当前数据源下的 TableMeta（用于 trace 链接与一致性说明）。"""
    schema = ((db_part or "").strip() or (default_database or "").strip()) or ""
    tbl = (table_name or "").strip()
    if not datasource_id or not schema or not tbl:
        return None
    row = db.execute(
        select(TableMeta)
        .where(
            TableMeta.datasource_id == datasource_id,
            TableMeta.database_name == schema,
            TableMeta.table_name == tbl,
        )
        .limit(1)
    ).scalars().first()
    if row:
        return row
    return db.execute(
        select(TableMeta)
        .where(
            TableMeta.datasource_id == datasource_id,
            func.lower(TableMeta.database_name) == schema.lower(),
            func.lower(TableMeta.table_name) == tbl.lower(),
        )
        .limit(1)
    ).scalars().first()


def _reasoning3_basis_chain(
    db: Session,
    *,
    business_domain_id: int | None,
    tm: TableMeta | None,
    table_narrative: str,
    datasource_fallback: DataSource | None = None,
    database_name_fallback: str | None = None,
) -> str:
    """
    业务域 → 数据库 → 数据表分层依据；层与层之间使用 ‖，由前端换行展示。
    """
    parts: list[str] = []
    if business_domain_id:
        dom = db.get(BusinessDomain, business_domain_id)
        if dom:
            parts.append(f"业务域：会话绑定「{dom.name}」（id={dom.id}），用于关联知识库与域内表策略上下文。")
        else:
            parts.append(f"业务域：请求携带 domain_id={business_domain_id}，元数据中未找到对应业务域。")
    else:
        parts.append("业务域：未选择业务域，本链路未经过域级知识库路由。")

    if tm and tm.datasource_id:
        ds = db.get(DataSource, tm.datasource_id)
        if ds:
            dname = (ds.name or "").strip() or f"id={ds.id}"
            parts.append(f"数据库：数据源「{dname}」（类型 {ds.source_type}），逻辑库/命名空间为「{tm.database_name}」。")
        else:
            parts.append(f"数据库：表记录关联 datasource_id={tm.datasource_id}，但未检索到数据源实体。")
    elif datasource_fallback:
        dname = (datasource_fallback.name or "").strip() or f"id={datasource_fallback.id}"
        ns = (database_name_fallback or "").strip() or (datasource_fallback.database or "") or "默认"
        parts.append(
            f"数据库：当前解析锚定数据源「{dname}」（类型 {datasource_fallback.source_type}），命名空间「{ns}」。"
        )
    elif tm:
        parts.append("数据库：表元数据缺少 datasource_id，无法下钻到连接配置。")
    else:
        parts.append("数据库：无表元数据锚点，无法解析到具体数据源与库名。")

    if tm:
        fq = f"{tm.database_name}.{tm.table_name}"
        parts.append(f"数据表：元数据登记「{fq}」（table_id={tm.id}）。{table_narrative}")
    else:
        parts.append(f"数据表：{table_narrative}")

    return "‖".join(parts)


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

    async def trace_row(step_id: str, label: str, detail: str = "", links: list[dict[str, Any]] | None = None) -> None:
        d = (detail or "").strip()
        if len(d) > 2800:
            d = d[:2800] + "…"
        row: dict[str, Any] = {"id": step_id, "label": label, "detail": d}
        if links:
            row["links"] = links
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

    reasoning_2_lines: list[str] = []
    reasoning_2_links: list[dict[str, Any]] = []
    if business_domain_id:
        dom = db.get(BusinessDomain, business_domain_id)
        if dom:
            reasoning_2_lines.append(f"业务域：「{dom.name}」（id={dom.id}）。")
            reasoning_2_links.append(
                {
                    "kind": "business_domain",
                    "id": dom.id,
                    "matches": [f"「{dom.name}」", f"业务域：「{dom.name}」"],
                }
            )
            stmt_kb = (
                select(KnowledgeBase)
                .join(
                    BusinessDomainKnowledgeBase,
                    KnowledgeBase.id == BusinessDomainKnowledgeBase.knowledge_base_id,
                )
                .where(BusinessDomainKnowledgeBase.domain_id == business_domain_id)
            )
            kbs = list(db.execute(stmt_kb).scalars().all())
            if kbs:
                head = kbs[:3]
                suffix = " 等" if len(kbs) > 3 else ""
                reasoning_2_lines.append("关联知识库：" + "、".join(f"「{k.name}」" for k in head) + suffix + "。")
                seen_kb: set[int] = set()
                for k in kbs:
                    if k.id in seen_kb:
                        continue
                    seen_kb.add(k.id)
                    reasoning_2_links.append({"kind": "knowledge_base", "id": k.id, "matches": [f"「{k.name}」", k.name]})
    reasoning_2_lines.extend(
        [
            f"业务/知识库约 {len(knowledge_text)} 字",
            f"相似历史问法 {ref_n} 条",
            f"表与数据源说明约 {len(priority_context)} 字",
            f"列语义 Schema 约 {len(schema)} 字。",
        ]
    )
    reasoning_2_detail = "\n".join(reasoning_2_lines)

    if intent != "sql_query":
        await trace_row(
            "reasoning_1",
            "1. 明确用户输入，给出理解",
            "\n".join(
                [
                    f"用户问题摘要：{q_preview or '（空）'}",
                    "判定为「通用问答」。",
                    f"意图说明：{reason_txt or '（无）'}",
                ]
            ),
        )
        await trace_row("reasoning_2", "2. 确认拿到的上下文信息", reasoning_2_detail, links=reasoning_2_links)
        await trace_row(
            "reasoning_gq",
            "3. 执行方式",
            "不进行单表 SQL 查询。\n结合上述上下文由模型生成自然语言回答。",
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
        "\n".join(
            [
                f"用户问题摘要：{q_preview or '（空）'}",
                "判定为「SQL 数据分析」。",
                f"意图说明：{reason_txt or '（无）'}",
            ]
        ),
    )
    await trace_row("reasoning_2", "2. 确认拿到的上下文信息", reasoning_2_detail, links=reasoning_2_links)

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
    used_latest_table_fallback = False
    if resolved_table_id is None:
        latest_table = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().first()
        if latest_table:
            resolved_table_id = latest_table.id
            used_latest_table_fallback = True

    sql_text = sanitize_sql_text(str(result.get("sql") or ""))
    result["sql"] = sql_text

    r3_links_map: dict[tuple[str, int], dict[str, Any]] = {}

    def _add_table_trace_link(tm: TableMeta | None) -> None:
        if tm is None:
            return
        key = ("table", tm.id)
        if key in r3_links_map:
            return
        fq = f"{tm.database_name}.{tm.table_name}"
        r3_links_map[key] = {
            "kind": "table",
            "id": tm.id,
            "matches": [f"「{fq}」", fq, f"table_id={tm.id}", f"id={tm.id}。"],
        }

    primary_ctx_id = table_id or preferred_table_id or resolved_table_id
    primary_tm = db.get(TableMeta, primary_ctx_id) if primary_ctx_id else None
    anchor_tm: TableMeta | None = db.get(TableMeta, table_id) if table_id else None
    if anchor_tm is None and preferred_table_id:
        anchor_tm = db.get(TableMeta, preferred_table_id)
    if anchor_tm is None and resolved_table_id:
        anchor_tm = db.get(TableMeta, resolved_table_id)

    ds_anchor: DataSource | None = None
    dialect_anchor = "mysql"
    default_db: str | None = None
    if anchor_tm and anchor_tm.datasource_id:
        ds_anchor = db.get(DataSource, anchor_tm.datasource_id)
        default_db = (anchor_tm.database_name or "").strip() or None
    elif resolved_table_id:
        rt_anchor = db.get(TableMeta, resolved_table_id)
        if rt_anchor and rt_anchor.datasource_id:
            ds_anchor = db.get(DataSource, rt_anchor.datasource_id)
            default_db = (rt_anchor.database_name or "").strip() or None
    if ds_anchor is None:
        ds_anchor = db.execute(select(DataSource).order_by(DataSource.created_at.desc())).scalars().first()
        if ds_anchor and not default_db:
            default_db = (str(ds_anchor.database or "").strip()) or None
    if ds_anchor:
        dialect_anchor = source_type_to_sqlglot_dialect(ds_anchor.source_type) or "mysql"

    sql_resolved: list[TableMeta] = []
    seen_sql_tid: set[int] = set()
    refs_raw: list[tuple[str | None, str | None, str]] = []
    if sql_text.strip() and ds_anchor:
        refs_raw = extract_table_refs_from_sql(sql_text, dialect=dialect_anchor)
        ds_id = int(ds_anchor.id)
        for _cat, dbp, name in refs_raw:
            tm_hit = _resolve_table_meta_for_trace(
                db, datasource_id=ds_id, default_database=default_db, db_part=dbp, table_name=name
            )
            if tm_hit and tm_hit.id not in seen_sql_tid:
                seen_sql_tid.add(tm_hit.id)
                sql_resolved.append(tm_hit)
        for tm_sql in sql_resolved:
            _add_table_trace_link(tm_sql)

    scope_lines: list[str] = []

    def _r3_row(
        fq_bracketed: str,
        trust_code: str,
        role: str,
        *,
        tm: TableMeta | None,
        table_narrative: str,
        datasource_fallback: DataSource | None = None,
        database_name_fallback: str | None = None,
    ) -> None:
        basis = _reasoning3_basis_chain(
            db,
            business_domain_id=business_domain_id,
            tm=tm,
            table_narrative=table_narrative,
            datasource_fallback=datasource_fallback,
            database_name_fallback=database_name_fallback,
        )
        scope_lines.append(f"{fq_bracketed}　[[trust:{trust_code}]]　角色：{role}　判断依据：{basis}")

    if sql_resolved:
        for tm in sql_resolved:
            fq = f"{tm.database_name}.{tm.table_name}"
            fq_b = f"「{fq}」"
            locked_here = bool(table_id and tm.id == table_id)
            if locked_here:
                role = "主分析表（与用户锁定一致）"
                narr = f"请求锁定 table_id={table_id}。方言「{dialect_anchor}」解析生成 SQL 已引用该物理名。"
                _r3_row(fq_b, "high", role, tm=tm, table_narrative=narr)
            elif table_id and primary_tm and primary_tm.id == table_id and tm.id != table_id:
                role = "查询涉及表（FROM/JOIN）"
                narr = (
                    f"用户锁定主表为「{primary_tm.database_name}.{primary_tm.table_name}」，"
                    f"本表仍出现在方言「{dialect_anchor}」解析的 JOIN/FROM 中，请确认是否必要。"
                )
                _r3_row(fq_b, "review", role, tm=tm, table_narrative=narr)
            elif len(sql_resolved) == 1:
                role = "主分析表"
                narr = f"未请求锁定单表。方言「{dialect_anchor}」解析生成 SQL 单表引用该登记名。"
                if primary_tm and tm.id == primary_tm.id:
                    narr += "与上下文默认对齐表一致。"
                _r3_row(fq_b, "medium-high", role, tm=tm, table_narrative=narr)
            else:
                role = "查询涉及表（FROM/JOIN）"
                narr = f"方言「{dialect_anchor}」解析生成 SQL 多表 JOIN 之一。"
                if primary_tm and tm.id == primary_tm.id:
                    narr += "与上下文默认对齐表一致。"
                _r3_row(fq_b, "medium", role, tm=tm, table_narrative=narr)

    if primary_tm and primary_tm.id not in seen_sql_tid:
        pfq = f"{primary_tm.database_name}.{primary_tm.table_name}"
        fq_b = f"「{pfq}」"
        if table_id:
            narr = (
                f"请求锁定 table_id={table_id}，但方言「{dialect_anchor}」在生成 SQL 中未解析出「{pfq}」全名，"
                "请对照是否别名、子查询或未带库前缀。"
            )
            _r3_row(fq_b, "review", "用户锁定主表（SQL 未解析到该物理名）", tm=primary_tm, table_narrative=narr)
        else:
            narr = (
                "写入绑定曾回退到「最近创建表」，仅作 Schema 与示例锚点，不等价于查询范围。"
                if used_latest_table_fallback
                else "上下文默认对齐表，用于列语义注入。生成 SQL 未解析到该全名时以 SQL 中出现的表理解实际范围。"
            )
            tc = "low" if used_latest_table_fallback else "medium"
            _r3_row(fq_b, tc, "上下文参考表（未出现在 SQL 解析结果）", tm=primary_tm, table_narrative=narr)

    if not scope_lines:
        if not sql_text.strip():
            _r3_row(
                "（无表名）",
                "low",
                "—",
                tm=None,
                table_narrative="无生成 SQL 文本，无法从语句解析物理表。",
                datasource_fallback=ds_anchor,
                database_name_fallback=default_db,
            )
        elif not ds_anchor:
            _r3_row("（无表名）", "low", "—", tm=None, table_narrative="缺少数据源锚点，未对生成 SQL 做表名抽取。")
        elif refs_raw and not sql_resolved:
            fq_bits: list[str] = []
            for _c, d2, n2 in refs_raw[:4]:
                sc = ((d2 or "").strip() or (default_db or "?")) or "?"
                fq_bits.append(f"{sc}.{n2}")
            tail = " 等" if len(refs_raw) > 4 else ""
            narr = (
                "语句可见 "
                + "、".join(fq_bits)
                + tail
                + "，但在已登记元数据中未匹配到同数据源下的表。"
            )
            _r3_row(
                "（解析片段）",
                "low",
                "—",
                tm=None,
                table_narrative=narr,
                datasource_fallback=ds_anchor,
                database_name_fallback=default_db,
            )
        elif not refs_raw and "select" in sql_text.lower():
            _r3_row(
                "（无表名）",
                "low",
                "—",
                tm=None,
                table_narrative="方言解析未得到独立物理表名（可能为常量查询或嵌套过深）。",
                datasource_fallback=ds_anchor,
                database_name_fallback=default_db,
            )
        else:
            _r3_row(
                "（无表名）",
                "medium",
                "—",
                tm=None,
                table_narrative="无可用语句级表名，请依赖其它步骤或重新生成 SQL。",
                datasource_fallback=ds_anchor,
                database_name_fallback=default_db,
            )

    if business_domain_id:
        dom_r3 = db.get(BusinessDomain, business_domain_id)
        if dom_r3:
            r3_links_map[("business_domain", dom_r3.id)] = {
                "kind": "business_domain",
                "id": dom_r3.id,
                "matches": [f"「{dom_r3.name}」", f"会话绑定「{dom_r3.name}」"],
            }
    if ds_anchor:
        r3_links_map[("datasource", int(ds_anchor.id))] = {
            "kind": "datasource",
            "id": int(ds_anchor.id),
            "matches": [
                f"数据源「{(ds_anchor.name or '').strip() or f'id={ds_anchor.id}'}」",
                (ds_anchor.name or "").strip() or f"id={ds_anchor.id}",
            ],
        }

    if table_id:
        _add_table_trace_link(db.get(TableMeta, table_id))
    elif preferred_table_id:
        _add_table_trace_link(db.get(TableMeta, preferred_table_id))
    if resolved_table_id and not table_id:
        rt = db.get(TableMeta, resolved_table_id)
        if rt and (preferred_table_id is None or resolved_table_id != preferred_table_id):
            _add_table_trace_link(rt)
    r3_links = list(r3_links_map.values())
    await trace_row("reasoning_3", "3. 推断将使用的表", "\n".join(scope_lines), links=r3_links)

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
    exp_raw = str(result.get("explanation") or "").strip()
    exp_show = (exp_raw[:1600] + ("…" if len(exp_raw) > 1600 else "")) if exp_raw else "（模型未给出说明）"

    execution: dict[str, Any] = {"ok": False, "columns": [], "rows": [], "error": "未生成 SQL"}
    if sql_text:
        await emit("sql_executing")
        datasource: DataSource | None = None
        database_name: str | None = None
        target_table: TableMeta | None = None
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
            r5_detail = (
                f"数据源：{datasource.name or datasource.id}\n"
                f"连接类型：{datasource.source_type}\n"
                f"解析出的 SQL 方言（用于语法树校验）：{dialect_label}\n"
                f"库/命名空间：{database_name or datasource.database or '（默认）'}"
            )
            link_r5: list[dict[str, Any]] = []
            ds_label = str(datasource.name or datasource.id)
            link_r5.append({"kind": "datasource", "id": datasource.id, "matches": [f"数据源：{ds_label}", ds_label]})
            ns_display = (database_name or datasource.database or "").strip()
            if ns_display and ns_display != "（默认）":
                link_r5.append(
                    {
                        "kind": "database",
                        "datasource_id": datasource.id,
                        "database_name": ns_display,
                        "matches": [f"库/命名空间：{ns_display}"],
                    }
                )
            if target_table:
                fq = f"{target_table.database_name}.{target_table.table_name}"
                link_r5.append({"kind": "table", "id": target_table.id, "matches": [f"「{fq}」", fq]})
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
                    try:
                        execution = await asyncio.to_thread(execute_readonly_sql, conn_info, attempted_sql)
                    except Exception as exc:  # noqa: BLE001
                        execution = {"ok": False, "columns": [], "rows": [], "error": str(exc)}

                if execution.get("ok"):
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

            # 与真实下发/最后一次尝试一致（含自动修复后的 SQL）
            result["sql"] = sanitize_sql_text(str(attempted_sql or ""))

            if not execution.get("ok") and repair_attempts:
                final_err = str(execution.get("error") or "未知错误").strip()
                if len(final_err) > 1200:
                    final_err = final_err[:1200] + "…"
                execution["error"] = final_err

            # 合并原步骤 5、6：数据源/方言绑定 + AST 与下发结论（不再单独占一步）
            if execution.get("ok"):
                ast_tail = f"方言 {dialect_label}：只读与安全 AST 已通过，已向数据源执行查询。"
            elif last_ast_error.strip():
                le = last_ast_error.strip()
                ast_tail = f"方言 {dialect_label}：只读 AST 未通过 — {le[:900]}{'…' if len(le) > 900 else ''}"
            else:
                emsg = str(execution.get("error") or "执行失败").strip()
                if len(emsg) > 900:
                    emsg = emsg[:900] + "…"
                ast_tail = f"方言 {dialect_label}：AST 校验通过后，执行阶段失败 — {emsg}"
            r56_detail = f"{r5_detail}\n\n{ast_tail}"
            await trace_row("reasoning_5", "5. 执行环境与 AST 校验", r56_detail, links=link_r5)

            if execution.get("ok"):
                rows_n = len(execution.get("rows") or [])
                cols_n = len(execution.get("columns") or [])
                r7_detail = (
                    "执行状态：成功。\n"
                    f"结果集：{rows_n} 行 × {cols_n} 列。\n"
                    "界面下方表格展示预览（最多 20 行）。"
                )
            else:
                err = str(execution.get("error") or "未知错误").strip()
                if len(err) > 1000:
                    err = err[:1000] + "…"
                r7_detail = "执行状态：失败。\n" f"原因摘要：{err}\n" "完整报错见对话中的「执行结果」区域。"
            await trace_row("reasoning_7", "7. 执行结果", r7_detail)
        else:
            execution = {"ok": False, "columns": [], "rows": [], "error": "未配置可用数据源"}
            await trace_row(
                "reasoning_5",
                "5. 执行环境与 AST 校验",
                "未找到可用数据源，无法绑定执行环境与方言。\n\nAST 与实际下发：跳过（无可用数据源）。",
            )
            await trace_row("reasoning_7", "7. 执行结果", "执行状态：未执行（未配置可用数据源）。")
    else:
        await trace_row(
            "reasoning_5",
            "5. 执行环境与 AST 校验",
            "无有效 SQL 文本，跳过数据源与方言绑定。\n\nAST 与实际下发：无可执行语句。",
        )
        await trace_row("reasoning_7", "7. 执行结果", "执行状态：未执行（无 SQL 文本）。")

    # 第 4 步在修复与执行之后写入，SQL 与 result["sql"] 及实际尝试执行的语句一致；并做可读性格式化
    _sql_disp = str(result.get("sql") or "").strip()
    _fmt_dialect = source_type_to_sqlglot_dialect(ds_anchor.source_type) if ds_anchor else dialect_anchor
    if _sql_disp:
        try:
            _pretty = format_sql_for_display(_sql_disp, dialect=str(_fmt_dialect or "mysql"))
            if _pretty.strip():
                _sql_disp = _pretty.strip()
        except Exception:  # noqa: BLE001
            pass
        result["sql"] = _sql_disp
    sql_show_final = (_sql_disp[:3200] + ("…" if len(_sql_disp) > 3200 else "")) if _sql_disp else "（清洗后暂无可执行 SQL）"
    _insert_reasoning_4_after_reasoning_3(
        pipeline_traces,
        f"【判定与取数逻辑】\n{exp_show}\n\n【SQL（清洗后用于执行）】\n{sql_show_final}",
    )
    if trace_callback:
        for _r4 in pipeline_traces:
            if _r4.get("id") == "reasoning_4":
                await trace_callback(_r4)
                break

    result["query_result"] = execution
    result["intent"] = "sql_query"
    result["answer"] = "已根据你的问题生成并执行 SQL，结果如下。"
    result["pipeline_trace"] = pipeline_traces
    return result
