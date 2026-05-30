"""知识库数据库导入 — 从已连接的数据源中选择数据库作为知识源。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from routers.datasources import _extract_business_description
from models import (
    DataSource,
    KnowledgeBase,
    KnowledgeDatabaseImport,
    KnowledgeEntry,
    TableMeta,
    TableSummary,
)
from services.source_cascade_cleanup import cleanup_database_import

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-database-imports"])


class DatabaseImportRequest(BaseModel):
    datasource_id: int
    database_names: list[str]


def _to_row(di: KnowledgeDatabaseImport) -> dict:
    return {
        "id": di.id,
        "knowledge_base_id": di.knowledge_base_id,
        "datasource_id": di.datasource_id,
        "datasource_name": di.datasource_name,
        "database_names": di.database_names,
        "status": di.status,
        "last_error": di.last_error,
        "created_at": di.created_at.isoformat() if di.created_at else None,
        "updated_at": di.updated_at.isoformat() if di.updated_at else None,
    }


@router.get("/{kb_id}/database-imports")
def list_database_imports(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    rows = (
        db.execute(
            select(KnowledgeDatabaseImport)
            .where(KnowledgeDatabaseImport.knowledge_base_id == kb_id)
            .order_by(KnowledgeDatabaseImport.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {"imports": [_to_row(r) for r in rows]}


@router.post("/{kb_id}/database-imports")
def create_database_import(kb_id: int, body: DatabaseImportRequest, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")

    ds = db.get(DataSource, body.datasource_id)
    if not ds:
        raise HTTPException(status_code=404, detail="datasource not found")

    if not body.database_names:
        raise HTTPException(status_code=400, detail="database_names must not be empty")

    import_row = KnowledgeDatabaseImport(
        knowledge_base_id=kb_id,
        datasource_id=ds.id,
        datasource_name=ds.name,
        database_names=body.database_names,
        status="imported",
    )
    db.add(import_row)
    db.flush()

    db_names_str = ", ".join(body.database_names)
    clean_title = f"{ds.name} / {db_names_str}"
    entry = KnowledgeEntry(
        knowledge_base_id=kb_id,
        title=clean_title,
        summary=f"数据源 {ds.name} 的数据库 schema 导入：{db_names_str}",
        body=f"数据源: {ds.name}\n类型: {ds.source_type}\n数据库: {db_names_str}",
        source_meta={
            "kind": "database",
            "datasource_id": ds.id,
            "datasource_name": ds.name,
            "database_names": body.database_names,
            "import_id": import_row.id,
        },
        sort_order=0,
    )
    db.add(entry)
    db.commit()
    db.refresh(import_row)

    try:
        from services.ingestion.connectors import register_evidence_from_import

        register_evidence_from_import(
            db,
            kb_id,
            title=clean_title,
            route_key="database-imports",
            source_ref={
                "import_id": import_row.id,
                "datasource_id": ds.id,
                "database_names": body.database_names,
            },
            linked_entry_ids=[entry.id],
            processing_state="ready_for_extraction",
        )
    except Exception:
        pass

    try:
        from services.extraction.orchestrator import trigger_extraction_pipeline_background

        trigger_extraction_pipeline_background(
            kb_id,
            source_type=f"source:database",
            source_id=import_row.id,
        )
    except Exception:
        pass

    return _to_row(import_row)


@router.get("/{kb_id}/database-imports/{import_id}")
def get_database_import_detail(kb_id: int, import_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")

    di = db.get(KnowledgeDatabaseImport, import_id)
    if not di or di.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="database import not found")

    tables = []
    for db_name in di.database_names:
        table_rows = (
            db.execute(
                select(TableMeta)
                .where(
                    TableMeta.datasource_id == di.datasource_id,
                    TableMeta.database_name == db_name,
                )
                .order_by(TableMeta.created_at.desc())
            )
            .scalars()
            .all()
        )
        seen: set[str] = set()
        for t in table_rows:
            if t.table_name in seen:
                continue
            seen.add(t.table_name)
            summary = (
                db.execute(
                    select(TableSummary)
                    .where(TableSummary.table_id == t.id)
                    .order_by(TableSummary.generated_at.desc())
                )
                .scalars()
                .first()
            )
            tables.append(
                {
                    "id": t.id,
                    "table_name": t.table_name,
                    "database_name": t.database_name,
                    "status": t.status,
                    "row_count": t.row_count,
                    "ai_summary": (
                        _extract_business_description(summary.summary)
                        if summary and summary.summary
                        else None
                    ),
                    "use_cases": summary.use_cases if summary else None,
                    "analyzed_at": t.created_at.isoformat() if t.created_at else None,
                }
            )

    return {
        "import": _to_row(di),
        "datasource": {
            "id": di.datasource_id,
            "name": di.datasource_name,
        },
        "tables": tables,
    }


@router.delete("/{kb_id}/database-imports/{import_id}")
def delete_database_import(kb_id: int, import_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="knowledge base not found")

    di = db.get(KnowledgeDatabaseImport, import_id)
    if not di or di.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="database import not found")

    stats = cleanup_database_import(db, kb_id=kb_id, import_id=import_id)

    db.delete(di)
    db.commit()
    return {"ok": True, **stats.to_dict()}
