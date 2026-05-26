import asyncio
import logging
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import (
    BusinessDomain,
    BusinessDomainDescription,
    BusinessDomainKnowledgeBase,
    BusinessDomainSelection,
    ColumnMeta,
    DataSource,
    KnowledgeBase,
    KnowledgeEntry,
    TableMeta,
    TableSummary,
)
from services.embedding_service import embed_and_store
from services.llm_models import has_any_llm_key, resolve_effective_model
from services.llm_service import analyze_table, batch_analyze_columns
from services.runtime_llm_config import get_semantic_llm_model_stored
from services.profiler import merge_enum_semantic_output, profile_column
from services.schema_extractor import get_columns, get_ddl, get_row_count, get_sample, get_tables_meta_for_database
from services.codebase_analyzer import catch_up_pending_refs

router = APIRouter(prefix="/api", tags=["analyze"])

_logger = logging.getLogger(__name__)


class AnalyzeBody(BaseModel):
    source_type: str
    host: str
    port: int
    database: str
    username: str
    password: str


def _build_table_business_context(
    db: Session, table: TableMeta, table_name: str, conn_info: dict, column_names: list[str] | None = None,
) -> dict:
    datasource_desc = ""
    datasource_name = ""
    if table.datasource_id:
        datasource = db.get(DataSource, table.datasource_id)
        if datasource:
            datasource_desc = datasource.description or ""
            datasource_name = datasource.name

    table_comment = ""
    database_desc = f"{table.database_name} 数据库"
    try:
        tables_meta = get_tables_meta_for_database(conn_info, table.database_name)
        database_desc = f"{table.database_name} 数据库，包含 {len(tables_meta)} 张表"
        table_comment = next((t.get("comment", "") for t in tables_meta if t.get("name") == table_name), "")
    except Exception:  # noqa: BLE001
        pass

    prev_summary = ""
    prev_table = (
        db.execute(
            select(TableMeta)
            .where(
                TableMeta.datasource_id == table.datasource_id,
                TableMeta.database_name == table.database_name,
                TableMeta.table_name == table_name,
                TableMeta.id != table.id,
                TableMeta.status == "done",
            )
            .order_by(TableMeta.created_at.desc())
        )
        .scalars()
        .first()
    )
    if prev_table:
        summary_row = db.execute(select(TableSummary).where(TableSummary.table_id == prev_table.id)).scalar_one_or_none()
        if summary_row and summary_row.summary:
            prev_summary = summary_row.summary

    domain_contexts: list[dict[str, str]] = []
    domain_knowledge_entries: list[dict[str, str]] = []
    if table.datasource_id:
        selection_rows = (
            db.execute(
                select(BusinessDomainSelection).where(
                    BusinessDomainSelection.datasource_id == table.datasource_id,
                    BusinessDomainSelection.database_name == table.database_name,
                    (
                        (BusinessDomainSelection.table_name == table_name)
                        | (BusinessDomainSelection.table_name.is_(None))
                    ),
                )
            )
            .scalars()
            .all()
        )
        if selection_rows:
            domain_ids = list(dict.fromkeys([row.domain_id for row in selection_rows]))
            domains = db.execute(select(BusinessDomain).where(BusinessDomain.id.in_(domain_ids))).scalars().all()
            domain_map = {d.id: d for d in domains}
            desc_rows = (
                db.execute(
                    select(BusinessDomainDescription)
                    .where(BusinessDomainDescription.domain_id.in_(domain_ids))
                    .order_by(BusinessDomainDescription.created_at.desc())
                )
                .scalars()
                .all()
            )
            latest_desc: dict[int, str] = {}
            for row in desc_rows:
                if row.domain_id not in latest_desc:
                    latest_desc[row.domain_id] = row.content

            for row in selection_rows:
                domain = domain_map.get(row.domain_id)
                if not domain:
                    continue
                domain_contexts.append(
                    {
                        "domain_id": row.domain_id,
                        "domain_name": domain.name,
                        "domain_description": latest_desc.get(row.domain_id, ""),
                        "selection_scope": "database" if row.table_name is None else "table",
                    }
                )

        domain_ids_for_kb = list(dict.fromkeys([row.domain_id for row in selection_rows]))
        if domain_ids_for_kb:
            kb_rows = (
                db.execute(
                    select(BusinessDomainKnowledgeBase.knowledge_base_id).where(
                        BusinessDomainKnowledgeBase.domain_id.in_(domain_ids_for_kb)
                    )
                )
                .scalars()
                .all()
            )
            kb_ids = list(dict.fromkeys(kb_rows))
            if kb_ids:
                entries = (
                    db.execute(
                        select(KnowledgeEntry)
                        .where(KnowledgeEntry.knowledge_base_id.in_(kb_ids))
                        .order_by(KnowledgeEntry.sort_order.asc(), KnowledgeEntry.id.asc())
                    )
                    .scalars()
                    .all()
                )
                kb_map: dict[int, str] = {}
                if entries:
                    kb_meta_rows = (
                        db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))).scalars().all()
                    )
                    kb_map = {k.id: k.name for k in kb_meta_rows}

                # Relevance scoring: check title/summary against table_name + column_names
                search_terms = [table_name.lower()]
                if column_names:
                    search_terms.extend([cn.lower() for cn in column_names])

                def _relevance_score(entry: KnowledgeEntry) -> int:
                    blob = f"{entry.title or ''} {entry.summary or ''}".lower()
                    score = 0
                    for term in search_terms:
                        if len(term) < 3:
                            continue
                        if term in blob:
                            score += 1
                    # Bonus for table_name match in title
                    if table_name.lower() in (entry.title or "").lower():
                        score += 3
                    return score

                scored = [(_relevance_score(e), e) for e in entries]
                scored.sort(key=lambda x: x[0], reverse=True)

                seen_titles: set[str] = set()
                for score, e in scored:
                    title = (e.title or "").strip()
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    body = (e.body or "").strip()
                    max_len = 3000 if score > 0 else 800
                    if len(body) > max_len:
                        body = body[:max_len] + "…"
                    domain_knowledge_entries.append(
                        {
                            "title": title,
                            "summary": (e.summary or "").strip(),
                            "body": body,
                            "kb_name": kb_map.get(e.knowledge_base_id, ""),
                        }
                    )
                    if len(domain_knowledge_entries) >= 20:
                        break

    return {
        "table_name": table_name,
        "datasource_name": datasource_name,
        "datasource_description": datasource_desc,
        "database_name": table.database_name,
        "database_description": database_desc,
        "table_business_description": table_comment,
        "previous_table_description": prev_summary,
        "domain_contexts": domain_contexts,
        "domain_knowledge_entries": domain_knowledge_entries,
    }


async def _run_analyze(table_id: int, table_name: str, conn_info: dict) -> None:
    db: Session = SessionLocal()
    try:
        t = db.get(TableMeta, table_id)
        if not t:
            return
        t.status = "analyzing"
        db.commit()

        cols = get_columns(conn_info, table_name)
        sample = get_sample(conn_info, table_name)
        row_count = get_row_count(conn_info, table_name)
        ddl = get_ddl(conn_info, table_name)
        t.row_count = row_count
        t.ddl = ddl

        profiles = [
            profile_column(sample, c["column_name"], row_count, c.get("data_type"), c.get("column_type")) for c in cols
        ]
        semantic_model_ref = (
            resolve_effective_model(get_semantic_llm_model_stored(db), db) if has_any_llm_key(db) else ""
        )
        col_names_for_ctx = [c["column_name"] for c in cols]
        business_context = _build_table_business_context(db, t, table_name, conn_info, col_names_for_ctx)

        # Separate columns into LLM-worthy vs skipped (high null rate or single value)
        quality_indices: list[int] = []
        skip_indices: list[int] = []
        for i, (c, p) in enumerate(zip(cols, profiles, strict=False)):
            skip = False
            if p.get("null_ratio", 0) > 0.95:
                skip = True
            elif p.get("distinct_count", 0) <= 1:
                skip = True
            if skip:
                skip_indices.append(i)
            else:
                quality_indices.append(i)

        # Fallback semantics for skipped columns
        def _fallback_semantic(column_name: str, data_type: str | None) -> dict[str, Any]:
            ctype = (data_type or "").lower()
            stype = "dimension"
            if any(x in ctype for x in ["int", "decimal", "float", "double"]):
                stype = "metric"
            elif "date" in ctype or "time" in ctype:
                stype = "time"
            elif "id" in column_name.lower():
                stype = "id"
            return {"desc": f"{column_name}（未发送LLM分析：数据质量过低）", "type": stype, "is_usable": False, "reason": "数据质量过低，跳过LLM分析"}

        semantic_map: dict[int, dict[str, Any]] = {}
        for idx in skip_indices:
            semantic_map[idx] = _fallback_semantic(cols[idx]["column_name"], cols[idx].get("data_type"))

        # Only send quality columns to LLM
        if quality_indices:
            quality_cols = [cols[i] for i in quality_indices]
            quality_profiles = [profiles[i] for i in quality_indices]
            quality_semantic = await batch_analyze_columns(
                table_name,
                list(zip(quality_cols, quality_profiles)),
                db,
                semantic_model_ref=semantic_model_ref,
                business_context=business_context,
            )
            for qi, s in zip(quality_indices, quality_semantic, strict=False):
                semantic_map[qi] = s

        semantic = [semantic_map[i] for i in range(len(cols))]
        semantic = [merge_enum_semantic_output(s, p) for s, p in zip(semantic, profiles, strict=False)]
        rows_for_summary = []
        for c, p, s in zip(cols, profiles, semantic, strict=False):
            qm = dict(p.get("quality_metrics") or {})
            if s.get("aggregation"):
                qm["aggregation_hint"] = s["aggregation"]
            col = ColumnMeta(
                table_id=table_id,
                column_name=c["column_name"],
                data_type=c["data_type"],
                comment=c["comment"],
                semantic_desc=s.get("desc"),
                semantic_type=s.get("type"),
                is_usable=s.get("is_usable"),
                usable_reason=s.get("reason"),
                null_ratio=p.get("null_ratio"),
                distinct_count=p.get("distinct_count"),
                sample_values=p.get("sample_values"),
                top_values=p.get("top_values"),
                quality_metrics=qm,
            )
            rows_for_summary.append(
                {
                    "column_name": c["column_name"],
                    "data_type": c["data_type"],
                    "semantic_desc": s.get("desc"),
                    "semantic_type": s.get("type"),
                    "null_ratio": p.get("null_ratio", 0),
                    "enum": (p.get("quality_metrics") or {}).get("enum"),
                }
            )
            db.add(col)
            embed_and_store(
                db,
                "column",
                table_id,
                f"{table_name}.{c['column_name']}: {s.get('desc','')}，样本值：{p.get('sample_values',[])}",
                commit=False,
            )

        summary = await analyze_table(
            table_name,
            rows_for_summary,
            row_count,
            db,
            business_context=business_context,
            semantic_model_ref=semantic_model_ref,
        )
        db.add(
            TableSummary(
                table_id=table_id,
                summary=summary.get("summary"),
                use_cases="|".join(summary.get("use_cases", [])),
                key_columns="|".join(summary.get("key_columns", [])),
                warnings=summary.get("warnings", ""),
            )
        )
        embed_and_store(
            db,
            "table",
            table_id,
            f"{table_name}: {summary.get('summary','')}，分析场景：{summary.get('use_cases',[])}",
            commit=False,
        )
        t.status = "done"
        db.commit()

        try:
            from services.ingestion.events import emit

            emit("schema.analyzed", table_id=table_id, db=db)
        except Exception:
            pass

        # 将之前暂存的代码库表引用与新分析的表匹配
        try:
            await catch_up_pending_refs(db, table_id=table_id)
        except Exception:
            _logger.warning("Codebase catch-up failed for table_id=%s", table_id, exc_info=True)
    except Exception:  # noqa: BLE001
        _logger.exception("Analysis failed for table_id=%s table=%s", table_id, table_name)
        t = db.get(TableMeta, table_id)
        if t:
            t.status = "error"
            db.commit()
    finally:
        db.close()


def schedule_table_analyze(
    db: Session, table_name: str, conn_info: dict, source_type: str, database_name: str, datasource_id: int | None = None
) -> int:
    table = TableMeta(
        table_name=table_name,
        database_name=database_name,
        source_type=source_type,
        datasource_id=datasource_id,
        status="pending",
    )
    db.add(table)
    db.commit()
    db.refresh(table)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run_analyze(table.id, table_name, conn_info))
    except RuntimeError:
        threading.Thread(target=lambda: asyncio.run(_run_analyze(table.id, table_name, conn_info)), daemon=True).start()
    return table.id


@router.post("/analyze/{table_name}")
async def analyze(table_name: str, body: AnalyzeBody, db: Session = Depends(get_db)) -> dict:
    conn_info = body.model_dump()
    table_id = schedule_table_analyze(db, table_name, conn_info, body.source_type, body.database)
    return {"table_id": table_id, "status": "analyzing"}
