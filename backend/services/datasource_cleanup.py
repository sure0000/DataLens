"""Cascade cleanup before deleting a DataSource row."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models import (
    BusinessDomainSelection,
    ColumnMeta,
    DataSource,
    Embedding,
    KnowledgeDatabaseImport,
    QueryExample,
    TableMeta,
    TableSummary,
)
from services.embedding_service import COLUMN_EMBEDDING_REF, TABLE_EMBEDDING_REF
from services.source_cascade_cleanup import cleanup_database_import


def cleanup_datasource(db: Session, datasource_id: int) -> dict[str, int]:
    """Remove rows that reference *datasource_id* so the DataSource can be deleted."""
    stats = {
        "database_imports": 0,
        "domain_selections": 0,
        "tables": 0,
    }

    imports = (
        db.execute(
            select(KnowledgeDatabaseImport).where(KnowledgeDatabaseImport.datasource_id == datasource_id)
        )
        .scalars()
        .all()
    )
    for di in imports:
        cleanup_database_import(db, kb_id=di.knowledge_base_id, import_id=di.id)
        db.delete(di)
        stats["database_imports"] += 1
    if imports:
        db.flush()

    sel_result = db.execute(
        delete(BusinessDomainSelection).where(BusinessDomainSelection.datasource_id == datasource_id)
    )
    stats["domain_selections"] = int(sel_result.rowcount or 0)

    table_ids = list(
        db.execute(select(TableMeta.id).where(TableMeta.datasource_id == datasource_id)).scalars().all()
    )
    if table_ids:
        column_ids = list(
            db.execute(select(ColumnMeta.id).where(ColumnMeta.table_id.in_(table_ids))).scalars().all()
        )
        if column_ids:
            db.execute(
                delete(Embedding).where(
                    Embedding.ref_type == COLUMN_EMBEDDING_REF,
                    Embedding.ref_id.in_(column_ids),
                )
            )
        db.execute(
            delete(Embedding).where(
                Embedding.ref_type == TABLE_EMBEDDING_REF,
                Embedding.ref_id.in_(table_ids),
            )
        )
        db.execute(delete(QueryExample).where(QueryExample.table_id.in_(table_ids)))
        db.execute(delete(ColumnMeta).where(ColumnMeta.table_id.in_(table_ids)))
        db.execute(delete(TableSummary).where(TableSummary.table_id.in_(table_ids)))
        db.execute(delete(TableMeta).where(TableMeta.id.in_(table_ids)))
        stats["tables"] = len(table_ids)

    return stats


def delete_datasource_row(db: Session, row: DataSource) -> dict[str, int | bool]:
    """Cascade-delete dependents, then remove the DataSource (caller commits)."""
    stats = cleanup_datasource(db, row.id)
    db.delete(row)
    return {"success": True, **stats}
