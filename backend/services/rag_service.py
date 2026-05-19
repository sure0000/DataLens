"""Copilot RAG 回答流水线：意图识别 → 上下文组装 → SQL 生成 → 安全校验 → 执行 → 修复。"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    BusinessDomain,
    BusinessDomainDescription,
    BusinessDomainKnowledgeBase,
    ColumnMeta,
    DataSource,
    KnowledgeBase,
    QueryExample,
    TableMeta,
    TableSummary,
)
from services.context_builder import (
    build_priority_context,
    collect_knowledge_context_text,
    reasoning3_basis_chain,
    resolve_table_meta_for_trace,
)
from services.embedding_service import embed_and_store_async, search_similar_async
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
from services.trace_helpers import insert_reasoning_4_after_reasoning_3


async def answer(
    db: Session,
    question: str,
    table_id: int | None = None,
    business_domain_id: int | None = None,
    stage_callback: Callable[[str], Awaitable[None]] | None = None,
    trace_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    chat_model: str | None = None,
) -> dict[str, Any]:
    """端到端 Copilot 回答：意图分类 → 上下文 → SQL 生成 → 安全校验 → 执行/修复 → Trace。"""

    pipeline_traces: list[dict[str, Any]] = []

    # -------- 内联 trace / emit 闭包 --------
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
        if trace_callback:
            d = (detail or "").strip()
            await trace_callback({"id": step_id, "label": label, "detail": d})

    # -------- 阶段 1：意图识别 --------
    await emit("intent_recognizing")
    await asyncio.sleep(0)

    q_preview = (question or "").strip()
    if len(q_preview) > 900:
        q_preview = q_preview[:900] + "…"

    refs = await search_similar_async(db, question, top_k=5, table_id=table_id, ref_type="query")
    await trace_live("live_prep", "准备上下文", "已完成相似问法检索；若已选业务域，将先按域内知识库语义检索筛候选表再加载表元数据…")
    await asyncio.sleep(0)

    # -------- 阶段 2：上下文组装 --------
    priority_context, schema, summary_text, preferred_table_id, table_scope_note = build_priority_context(
        db, table_id, business_domain_id, question=question
    )
    await asyncio.sleep(0)

    knowledge_text = collect_knowledge_context_text(db, question, business_domain_id, table_id)

    if business_domain_id:
        dom = db.get(BusinessDomain, business_domain_id)
        if dom:
            dom_desc_row = (
                db.execute(
                    select(BusinessDomainDescription)
                    .where(BusinessDomainDescription.domain_id == business_domain_id)
                    .order_by(BusinessDomainDescription.created_at.desc())
                )
                .scalars()
                .first()
            )
            dom_desc = (dom_desc_row.content or "").strip() if dom_desc_row else ""
            dom_block = f"## DOMAIN CONTEXT — 当前业务域「{dom.name}」"
            if dom_desc:
                dom_block += f"\n{dom_desc}"
            dom_block += "\n（以上为该业务域的全局语义约束与分析惯例，生成 SQL 和解释时必须优先遵守）"
            knowledge_text = dom_block + "\n\n" + knowledge_text if knowledge_text.strip() else dom_block
    await asyncio.sleep(0)

    # -------- 阶段 3：意图分类 --------
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

    # -------- 构建 reasoning_2 --------
    reasoning_2_lines, reasoning_2_links = _build_reasoning_2(
        db, business_domain_id, knowledge_text, ref_n, priority_context, schema, table_scope_note
    )
    reasoning_2_detail = "\n".join(reasoning_2_lines)

    # -------- 通用问答分支 --------
    if intent != "sql_query":
        return await _handle_general_qa(
            db, question, q_preview, reason_txt, knowledge_text, priority_context,
            reasoning_2_detail, reasoning_2_links, pipeline_traces,
            emit, trace_row, chat_model,
        )

    # -------- SQL 查询分支 --------
    await trace_row("reasoning_1", "1. 明确用户输入，给出理解",
        "\n".join([f"用户问题摘要：{q_preview or '（空）'}", "判定为「SQL 数据分析」。", f"意图说明：{reason_txt or '（无）'}"]))
    await trace_row("reasoning_2", "2. 确认拿到的上下文信息", reasoning_2_detail, links=reasoning_2_links)

    await emit("answer_generating")

    few_shot = json.dumps(refs, ensure_ascii=False)
    copilot_context = SqlCopilotContext(
        knowledge=knowledge_text.strip(),
        datasource_priority=priority_context.strip(),
        schema=schema.strip(),
        few_shot_json=few_shot,
    )
    result = await generate_sql(question, summary_text, db, chat_model, copilot_context=copilot_context)

    # Resolve table_id for persistence
    resolved_table_id = table_id or preferred_table_id
    used_latest_table_fallback = False
    if resolved_table_id is None:
        latest_table = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().first()
        if latest_table:
            resolved_table_id = latest_table.id
            used_latest_table_fallback = True

    sql_text = sanitize_sql_text(str(result.get("sql") or ""))
    result["sql"] = sql_text

    # -------- 阶段 4：解析 SQL 引用的表（reasoning_3） --------
    ds_anchor, dialect_anchor, default_db = _resolve_datasource_anchor(
        db, table_id, preferred_table_id, resolved_table_id
    )
    r3_links = await _build_reasoning_3(
        db, sql_text, ds_anchor, dialect_anchor, default_db,
        table_id, preferred_table_id, resolved_table_id, used_latest_table_fallback,
        business_domain_id, trace_row,
    )

    # -------- 持久化 QueryExample + Embedding --------
    if resolved_table_id is not None:
        db.add(QueryExample(
            table_id=resolved_table_id, question=question,
            sql_text=result.get("sql", ""), explanation=result.get("explanation", ""),
        ))
        db.commit()
    await embed_and_store_async(db, "query", resolved_table_id or 0, f"{question} -> {result.get('sql', '')}")

    # -------- 阶段 5-7：执行 + 修复 + 结果 --------
    exp_raw = str(result.get("explanation") or "").strip()
    exp_show = (exp_raw[:1600] + ("…" if len(exp_raw) > 1600 else "")) if exp_raw else "（模型未给出说明）"

    execution = await _execute_with_repair(
        db, question, sql_text, summary_text, ds_anchor, dialect_anchor,
        default_db, resolved_table_id, result, emit, trace_row, copilot_context, chat_model,
    )

    # 第 4 步在修复/执行后补入
    sql_show_final = _format_sql_display(result.get("sql", ""), ds_anchor, dialect_anchor)
    insert_reasoning_4_after_reasoning_3(
        pipeline_traces,
        f"【判定与取数逻辑】\n{exp_show}\n\n【SQL（清洗后用于执行）】\n{sql_show_final}",
    )
    if trace_callback:
        for r4 in pipeline_traces:
            if r4.get("id") == "reasoning_4":
                await trace_callback(r4)
                break

    result["query_result"] = execution
    result["intent"] = "sql_query"
    result["answer"] = "已根据你的问题生成并执行 SQL，结果如下。"
    result["pipeline_trace"] = pipeline_traces
    return result


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _build_reasoning_2(
    db: Session,
    business_domain_id: int | None,
    knowledge_text: str,
    ref_n: int,
    priority_context: str,
    schema: str,
    table_scope_note: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    lines: list[str] = []
    links: list[dict[str, Any]] = []

    if business_domain_id:
        dom = db.get(BusinessDomain, business_domain_id)
        if dom:
            lines.append(f"业务域：「{dom.name}」（id={dom.id}）。")
            links.append({"kind": "business_domain", "id": dom.id, "matches": [f"「{dom.name}」", f"业务域：「{dom.name}」"]})
            stmt_kb = (
                select(KnowledgeBase)
                .join(BusinessDomainKnowledgeBase, KnowledgeBase.id == BusinessDomainKnowledgeBase.knowledge_base_id)
                .where(BusinessDomainKnowledgeBase.domain_id == business_domain_id)
            )
            kbs = list(db.execute(stmt_kb).scalars().all())
            if kbs:
                head = kbs[:3]
                suffix = " 等" if len(kbs) > 3 else ""
                lines.append("关联知识库：" + "、".join(f"「{k.name}」" for k in head) + suffix + "。")
                for k in kbs:
                    links.append({"kind": "knowledge_base", "id": k.id, "matches": [f"「{k.name}」", k.name]})

    lines.extend([
        f"业务/知识库约 {len(knowledge_text)} 字",
        f"相似历史问法 {ref_n} 条",
        f"表与数据源说明约 {len(priority_context)} 字",
        f"列语义 Schema 约 {len(schema)} 字。",
    ])
    if table_scope_note:
        lines.append(table_scope_note)
    return lines, links


async def _handle_general_qa(
    db: Session, question: str, q_preview: str, reason_txt: str,
    knowledge_text: str, priority_context: str,
    reasoning_2_detail: str, reasoning_2_links: list[dict[str, Any]],
    pipeline_traces: list[dict[str, Any]],
    emit, trace_row, chat_model: str | None,
) -> dict[str, Any]:
    await trace_row("reasoning_1", "1. 明确用户输入，给出理解",
        "\n".join([f"用户问题摘要：{q_preview or '（空）'}", "判定为「通用问答」。", f"意图说明：{reason_txt or '（无）'}"]))
    await trace_row("reasoning_2", "2. 确认拿到的上下文信息", reasoning_2_detail, links=reasoning_2_links)
    await trace_row("reasoning_gq", "3. 执行方式", "不进行单表 SQL 查询。\n结合上述上下文由模型生成自然语言回答。")

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
        explanation = "该问题更适合自然语言回答，无需执行 SQL"

    await embed_and_store_async(db, "query", 0, f"{question} -> {natural_answer}")
    return {
        "intent": "general_qa", "answer": natural_answer, "sql": "",
        "explanation": explanation,
        "query_result": {"ok": False, "columns": [], "rows": [], "error": "该问题无需SQL执行"},
        "pipeline_trace": pipeline_traces,
    }


def _resolve_datasource_anchor(
    db: Session, table_id: int | None, preferred_table_id: int | None, resolved_table_id: int | None,
) -> tuple[DataSource | None, str, str | None]:
    """解析执行数据源锚点和 SQL 方言。"""
    ds_anchor: DataSource | None = None
    dialect_anchor = "mysql"
    default_db: str | None = None

    anchor_tm: TableMeta | None = db.get(TableMeta, table_id) if table_id else None
    if anchor_tm is None and preferred_table_id:
        anchor_tm = db.get(TableMeta, preferred_table_id)
    if anchor_tm is None and resolved_table_id:
        anchor_tm = db.get(TableMeta, resolved_table_id)

    if anchor_tm and anchor_tm.datasource_id:
        ds_anchor = db.get(DataSource, anchor_tm.datasource_id)
        default_db = (anchor_tm.database_name or "").strip() or None
    elif resolved_table_id:
        rt = db.get(TableMeta, resolved_table_id)
        if rt and rt.datasource_id:
            ds_anchor = db.get(DataSource, rt.datasource_id)
            default_db = (rt.database_name or "").strip() or None
    if ds_anchor is None:
        ds_anchor = db.execute(select(DataSource).order_by(DataSource.created_at.desc())).scalars().first()
        if ds_anchor and not default_db:
            default_db = (str(ds_anchor.database or "").strip()) or None
    if ds_anchor:
        dialect_anchor = source_type_to_sqlglot_dialect(ds_anchor.source_type) or "mysql"

    return ds_anchor, dialect_anchor, default_db


async def _build_reasoning_3(
    db: Session,
    sql_text: str,
    ds_anchor: DataSource | None,
    dialect_anchor: str,
    default_db: str | None,
    table_id: int | None,
    preferred_table_id: int | None,
    resolved_table_id: int | None,
    used_latest_table_fallback: bool,
    business_domain_id: int | None,
    trace_row,
) -> list[dict[str, Any]]:
    """构建 reasoning_3：解析 SQL 中引用的表，输出信任级别判定。"""
    r3_links_map: dict[tuple[str, int], dict[str, Any]] = {}

    def _add_table_link(tm: TableMeta | None) -> None:
        if tm is None:
            return
        key = ("table", tm.id)
        if key in r3_links_map:
            return
        fq = f"{tm.database_name}.{tm.table_name}"
        r3_links_map[key] = {"kind": "table", "id": tm.id, "matches": [f"「{fq}」", fq, f"table_id={tm.id}", f"id={tm.id}。"]}

    primary_tm = db.get(TableMeta, table_id or preferred_table_id or resolved_table_id)

    # 解析 SQL 中的表引用
    sql_resolved: list[TableMeta] = []
    seen_sql_tid: set[int] = set()
    if sql_text.strip() and ds_anchor:
        refs_raw = extract_table_refs_from_sql(sql_text, dialect=dialect_anchor)
        for _cat, dbp, name in refs_raw:
            tm_hit = resolve_table_meta_for_trace(
                db, datasource_id=int(ds_anchor.id), default_database=default_db, db_part=dbp, table_name=name
            )
            if tm_hit and tm_hit.id not in seen_sql_tid:
                seen_sql_tid.add(tm_hit.id)
                sql_resolved.append(tm_hit)
        for tm_sql in sql_resolved:
            _add_table_link(tm_sql)

    scope_lines: list[str] = []

    def _r3_row(fq_b: str, trust: str, role: str, *, tm: TableMeta | None, narr: str,
                ds_fb: DataSource | None = None, db_fb: str | None = None) -> None:
        basis = reasoning3_basis_chain(
            db, business_domain_id=business_domain_id, tm=tm, table_narrative=narr,
            datasource_fallback=ds_fb, database_name_fallback=db_fb,
        )
        scope_lines.append(f"{fq_b}　[[trust:{trust}]]　角色：{role}　判断依据：{basis}")

    if sql_resolved:
        for tm in sql_resolved:
            fq = f"{tm.database_name}.{tm.table_name}"
            fq_b = f"「{fq}」"
            locked = bool(table_id and tm.id == table_id)
            if locked:
                _r3_row(fq_b, "high", "主分析表（与用户锁定一致）", tm=tm,
                        narr=f"请求锁定 table_id={table_id}。方言「{dialect_anchor}」解析生成 SQL 已引用该物理名。")
            elif table_id and primary_tm and primary_tm.id == table_id and tm.id != table_id:
                _r3_row(fq_b, "review", "查询涉及表（FROM/JOIN）", tm=tm,
                        narr=f"用户锁定主表为「{primary_tm.database_name}.{primary_tm.table_name}」，本表仍出现在方言解析的 JOIN/FROM 中。")
            elif len(sql_resolved) == 1:
                extra = "与上下文默认对齐表一致。" if primary_tm and tm.id == primary_tm.id else ""
                _r3_row(fq_b, "medium-high", "主分析表", tm=tm,
                        narr=f"未请求锁定单表。方言「{dialect_anchor}」解析生成 SQL 单表引用该登记名。{extra}")
            else:
                extra = "与上下文默认对齐表一致。" if primary_tm and tm.id == primary_tm.id else ""
                _r3_row(fq_b, "medium", "查询涉及表（FROM/JOIN）", tm=tm,
                        narr=f"方言「{dialect_anchor}」解析生成 SQL 多表 JOIN 之一。{extra}")

    if primary_tm and primary_tm.id not in seen_sql_tid:
        pfq = f"{primary_tm.database_name}.{primary_tm.table_name}"
        if table_id:
            _r3_row(f"「{pfq}」", "review", "用户锁定主表（SQL 未解析到该物理名）", tm=primary_tm,
                    narr=f"请求锁定 table_id={table_id}，但方言未解析出「{pfq}」全名。")
        else:
            tc = "low" if used_latest_table_fallback else "medium"
            _r3_row(f"「{pfq}」", tc, "上下文参考表（未出现在 SQL 解析结果）", tm=primary_tm,
                    narr="写入绑定曾回退到「最近创建表」。" if used_latest_table_fallback else "上下文默认对齐表，用于列语义注入。")

    if not scope_lines:
        _r3_row("（无表名）", "low", "—", tm=None, narr="无生成 SQL 文本或缺少数据源锚点。",
                ds_fb=ds_anchor, db_fb=default_db)

    if business_domain_id:
        dom_r3 = db.get(BusinessDomain, business_domain_id)
        if dom_r3:
            r3_links_map[("business_domain", dom_r3.id)] = {
                "kind": "business_domain", "id": dom_r3.id,
                "matches": [f"「{dom_r3.name}」", f"会话绑定「{dom_r3.name}」"],
            }
    if ds_anchor:
        ds_name = (ds_anchor.name or "").strip() or f"id={ds_anchor.id}"
        r3_links_map[("datasource", int(ds_anchor.id))] = {
            "kind": "datasource", "id": int(ds_anchor.id),
            "matches": [f"数据源「{ds_name}」", ds_name],
        }
    if table_id:
        _add_table_link(db.get(TableMeta, table_id))
    elif preferred_table_id:
        _add_table_link(db.get(TableMeta, preferred_table_id))

    await trace_row("reasoning_3", "3. 推断将使用的表", "\n".join(scope_lines),
                    links=list(r3_links_map.values()))
    return list(r3_links_map.values())


async def _execute_with_repair(
    db: Session, question: str, sql_text: str, summary_text: str,
    ds_anchor: DataSource | None, dialect_anchor: str, default_db: str | None,
    resolved_table_id: int | None, result: dict[str, Any],
    emit, trace_row, copilot_context: SqlCopilotContext, chat_model: str | None,
) -> dict[str, Any]:
    """执行 SQL（含最多 3 次自动修复），返回 execution 结果并写入 trace。"""
    execution: dict[str, Any] = {"ok": False, "columns": [], "rows": [], "error": "未生成 SQL"}
    if not sql_text or not ds_anchor:
        if not sql_text:
            await trace_row("reasoning_5", "5. 执行环境与 AST 校验", "无有效 SQL 文本，跳过数据源与方言绑定。")
            await trace_row("reasoning_7", "7. 执行结果", "执行状态：未执行（无 SQL 文本）。")
        else:
            await trace_row("reasoning_5", "5. 执行环境与 AST 校验", "未找到可用数据源，无法绑定执行环境与方言。")
            await trace_row("reasoning_7", "7. 执行结果", "执行状态：未执行（未配置可用数据源）。")
        return execution

    await emit("sql_executing")

    dialect = source_type_to_sqlglot_dialect(ds_anchor.source_type)
    dialect_label = str(dialect) if dialect else str(ds_anchor.source_type)

    # 构建连接信息
    conn_info = _build_conn_info(ds_anchor, default_db)

    attempted_sql = sql_text
    repair_attempts: list[dict[str, str]] = []
    last_ast_error = ""

    for attempt_idx in range(3):
        ast_ok, ast_err = validate_readonly_sql_ast(attempted_sql, dialect=dialect)
        if not ast_ok:
            last_ast_error = str(ast_err or "")
            execution = {"ok": False, "columns": [], "rows": [], "error": f"SQL 安全校验未通过：{ast_err}"}
        else:
            last_ast_error = ""
            try:
                execution = await asyncio.to_thread(execute_readonly_sql, conn_info, attempted_sql)
            except Exception as exc:
                execution = {"ok": False, "columns": [], "rows": [], "error": str(exc)}

        if execution.get("ok"):
            break
        if attempt_idx == 2:
            break

        current_error = str(execution.get("error") or "SQL执行失败")
        fix = await repair_failed_sql(
            question=question, failed_sql=attempted_sql, error_message=current_error,
            table_summary=summary_text, db=db, chat_model=chat_model, copilot_context=copilot_context,
        )
        next_sql = sanitize_sql_text(fix.get("sql", ""))
        repair_attempts.append({"reason": fix.get("reason", "自动修复"), "error": current_error, "sql": next_sql})
        if not next_sql or next_sql == attempted_sql:
            break
        attempted_sql = next_sql

    result["sql"] = sanitize_sql_text(str(attempted_sql or ""))
    if not execution.get("ok") and repair_attempts:
        final_err = str(execution.get("error") or "未知错误").strip()
        if len(final_err) > 1200:
            final_err = final_err[:1200] + "…"
        execution["error"] = final_err

    # 写入 reasoning_5 和 reasoning_7
    r5_detail = (
        f"数据源：{ds_anchor.name or ds_anchor.id}\n"
        f"连接类型：{ds_anchor.source_type}\n"
        f"解析出的 SQL 方言（用于语法树校验）：{dialect_label}\n"
        f"库/命名空间：{default_db or ds_anchor.database or '（默认）'}"
    )
    link_r5: list[dict[str, Any]] = [{"kind": "datasource", "id": ds_anchor.id,
                                         "matches": [f"数据源：{ds_anchor.name or ds_anchor.id}"]}]

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
    await trace_row("reasoning_5", "5. 执行环境与 AST 校验", f"{r5_detail}\n\n{ast_tail}", links=link_r5)

    if execution.get("ok"):
        rows_n = len(execution.get("rows") or [])
        cols_n = len(execution.get("columns") or [])
        r7_detail = f"执行状态：成功。\n结果集：{rows_n} 行 × {cols_n} 列。\n界面下方表格展示预览（最多 20 行）。"
    else:
        err = str(execution.get("error") or "未知错误").strip()
        if len(err) > 1000:
            err = err[:1000] + "…"
        r7_detail = f"执行状态：失败。\n原因摘要：{err}\n完整报错见对话中的「执行结果」区域。"
    await trace_row("reasoning_7", "7. 执行结果", r7_detail)

    return execution


def _build_conn_info(ds: DataSource, default_db: str | None) -> dict[str, str | int]:
    """从 DataSource 构建 schema_extractor 可用的连接信息字典。"""
    namespace = default_db or ds.database
    if _is_postgres_family(ds.source_type):
        return {"source_type": ds.source_type, "host": ds.host, "port": ds.port,
                "database": ds.database, "namespace": namespace or "public",
                "username": ds.username, "password": ds.password}
    if ds.source_type == "trino":
        return {"source_type": "trino", "host": ds.host, "port": ds.port,
                "database": ds.database, "namespace": namespace or ds.database,
                "username": ds.username, "password": ds.password}
    return {"source_type": ds.source_type, "host": ds.host, "port": ds.port,
            "database": namespace or ds.database, "username": ds.username, "password": ds.password}


def _format_sql_display(sql: str, ds_anchor: DataSource | None, dialect_anchor: str) -> str:
    """格式化 SQL 用于 trace 展示，最多 3200 字符。"""
    sql_disp = (sql or "").strip()
    if not sql_disp:
        return "（清洗后暂无可执行 SQL）"
    fmt_dialect = source_type_to_sqlglot_dialect(ds_anchor.source_type) if ds_anchor else dialect_anchor
    try:
        pretty = format_sql_for_display(sql_disp, dialect=str(fmt_dialect or "mysql"))
        if pretty.strip():
            sql_disp = pretty.strip()
    except Exception:
        pass
    return sql_disp[:3200] + ("…" if len(sql_disp) > 3200 else "")
