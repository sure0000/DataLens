"""Evidence package registry — persistent rows + merge with synthesized sources."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import EvidencePackage
from services.ingestion.evidence import (
    ASSET_LABELS,
    CONNECTOR_LABELS,
    list_evidence_packages as list_synthetic_packages,
)
from services.ingestion.events import emit


def _row_to_dict(row: EvidencePackage) -> dict[str, Any]:
    return {
        "id": f"ep-{row.id}",
        "db_id": row.id,
        "kb_id": row.knowledge_base_id,
        "display_id": f"EP-{1000 + row.id}",
        "asset_kind": row.asset_kind,
        "asset_label": ASSET_LABELS.get(row.asset_kind, row.asset_kind),
        "connector": row.connector,
        "connector_label": CONNECTOR_LABELS.get(row.connector, row.connector),
        "title": row.title,
        "source_ref": row.source_ref if isinstance(row.source_ref, dict) else {},
        "processing_state": row.processing_state,
        "linked_entry_ids": row.linked_entry_ids if isinstance(row.linked_entry_ids, list) else [],
        "linked_document_id": row.linked_document_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "persistent": True,
    }


def register_package(
    db: Session,
    kb_id: int,
    *,
    asset_kind: str,
    connector: str,
    title: str,
    source_ref: dict[str, Any] | None = None,
    linked_entry_ids: list[int] | None = None,
    linked_document_id: int | None = None,
    processing_state: str = "registered",
) -> EvidencePackage:
    row = EvidencePackage(
        knowledge_base_id=kb_id,
        asset_kind=asset_kind,
        connector=connector,
        title=title.strip() or "未命名证据包",
        source_ref=source_ref or {},
        linked_entry_ids=linked_entry_ids or [],
        linked_document_id=linked_document_id,
        processing_state=processing_state,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    emit("evidence.registered", kb_id=kb_id, package_id=row.id, asset_kind=asset_kind)
    return row


def normalize_package(db: Session, kb_id: int, package_id: int) -> dict[str, Any]:
    row = db.get(EvidencePackage, package_id)
    if not row or row.knowledge_base_id != kb_id:
        return {"ok": False, "error": "证据包不存在"}

    row.processing_state = "normalized"
    row.updated_at = datetime.utcnow()
    db.commit()

    emit(
        "evidence.normalized",
        kb_id=kb_id,
        package_id=row.id,
        asset_kind=row.asset_kind,
        connector=row.connector,
        linked_entry_ids=row.linked_entry_ids,
        db=db,
    )

    # Physical schema packages are ready for population/extraction downstream
    if row.asset_kind == "physical_schema":
        row.processing_state = "ready_for_extraction"
        db.commit()

    return {"ok": True, "package": _row_to_dict(row)}


def list_all_packages(db: Session, kb_id: int) -> list[dict[str, Any]]:
    """DB-registered packages first, then synthetic-only sources not linked to a row."""
    db_rows = db.execute(
        select(EvidencePackage)
        .where(EvidencePackage.knowledge_base_id == kb_id)
        .order_by(EvidencePackage.id.desc())
    ).scalars().all()
    persistent = [_row_to_dict(r) for r in db_rows]
    persistent_ids = {r["db_id"] for r in persistent}

    synthetic = list_synthetic_packages(db, kb_id)
    # Drop synthetic doc pipeline row if we have persistent packages (avoid duplicate noise)
    if persistent:
        synthetic = [p for p in synthetic if not p.get("source_ref", {}).get("document_pipeline")]

    return persistent + synthetic
