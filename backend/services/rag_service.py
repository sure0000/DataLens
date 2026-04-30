import json
from typing import Any
from collections.abc import Awaitable, Callable

import asyncio
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import ColumnMeta, DataSource, QueryExample, TableMeta, TableSummary
from services.embedding_service import embed_and_store_async, search_similar_async
from services.llm_service import (
    answer_general_question,
    classify_question_intent,
    generate_sql,
    guardrail_for_question,
    repair_failed_sql,
    sanitize_sql_text,
)
from services.schema_extractor import execute_readonly_sql


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


async def answer(
    db: Session,
    question: str,
    table_id: int | None = None,
    stage_callback: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    async def emit(stage: str) -> None:
        if stage_callback:
            await stage_callback(stage)

    await emit("intent_recognizing")
    refs = await search_similar_async(db, question, top_k=5, table_id=table_id)
    priority_context, schema, summary_text, preferred_table_id = _build_priority_context(db, table_id)
    intent_info = await classify_question_intent(question)
    intent = intent_info.get("intent", "general_qa")

    if intent != "sql_query":
        guardrail = guardrail_for_question(question)
        await emit("answer_generating")
        if guardrail:
            natural_answer = guardrail["answer"]
            explanation = guardrail["reason"]
        else:
            natural_answer = await answer_general_question(question, context_hint=priority_context)
            explanation = intent_info.get("reason", "该问题更适合自然语言回答，无需执行 SQL")
        await embed_and_store_async(db, "query", table_id or 0, f"{question} -> {natural_answer}")
        return {
            "intent": "general_qa",
            "answer": natural_answer,
            "sql": "",
            "explanation": explanation,
            "query_result": {"ok": False, "columns": [], "rows": [], "error": "该问题无需SQL执行"},
        }

    await emit("answer_generating")
    llm_context = "\n\n".join(
        [
            priority_context,
            "[结构化字段]",
            schema,
            "[历史相似问答]",
            json.dumps(refs, ensure_ascii=False),
        ]
    )
    result = await generate_sql(question, llm_context, summary_text)

    # query_examples.table_id has FK constraint, so we must persist a real table id.
    resolved_table_id = table_id
    if resolved_table_id is None and preferred_table_id:
        resolved_table_id = preferred_table_id
    if resolved_table_id is None:
        latest_table = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().first()
        if latest_table:
            resolved_table_id = latest_table.id

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

            for attempt_idx in range(3):
                try:
                    execution = await asyncio.to_thread(execute_readonly_sql, conn_info, attempted_sql)
                except Exception as exc:  # noqa: BLE001
                    execution = {"ok": False, "columns": [], "rows": [], "error": str(exc)}

                if execution.get("ok"):
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
                    table_schema=llm_context,
                    table_summary=summary_text,
                )
                next_sql = sanitize_sql_text(fix.get("sql", ""))
                reason = fix.get("reason", "自动修复")
                repair_attempts.append({"reason": reason, "error": current_error, "sql": next_sql})

                if not next_sql or next_sql == attempted_sql:
                    break
                attempted_sql = next_sql

            if not execution.get("ok") and repair_attempts:
                report_lines = [
                    "SQL 执行失败，系统已自动尝试修复但仍未成功：",
                    *[
                        f"{idx + 1}. 错误：{item['error']}；修复：{item['reason']}"
                        for idx, item in enumerate(repair_attempts)
                    ],
                    f"最终错误：{execution.get('error', '未知错误')}",
                ]
                execution["error"] = "\n".join(report_lines)
        else:
            execution = {"ok": False, "columns": [], "rows": [], "error": "未配置可用数据源"}

    result["query_result"] = execution
    result["intent"] = "sql_query"
    result["answer"] = "已根据你的问题生成并执行 SQL，结果如下。"
    return result
