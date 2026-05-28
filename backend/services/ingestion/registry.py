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


def _normalized_doc_title(value: str) -> str:
    title = value.strip().lower()
    for ext in (".md", ".txt", ".html", ".htm", ".docx", ".pdf", ".csv", ".xlsx"):
        if title.endswith(ext):
            return title[: -len(ext)].strip()
    return title


def _to_str(value: Any) -> str:
    return str(value).strip()


def _sorted_csv(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    normalized = sorted(_to_str(v) for v in values if _to_str(v))
    return ",".join(normalized)


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


def _dedupe_key(pkg: dict[str, Any]) -> str | None:
    source_ref = pkg.get("source_ref")
    if not isinstance(source_ref, dict):
        source_ref = {}
    connector = _to_str(pkg.get("connector") or "")
    asset_kind = _to_str(pkg.get("asset_kind") or "")
    kb_id = _to_str(pkg.get("kb_id") or "")

    owner = _to_str(source_ref.get("owner") or "")
    repo = _to_str(source_ref.get("repo") or "")
    branch = _to_str(source_ref.get("branch") or "")
    if connector == "git" and owner and repo:
        return f"gitrepo:{kb_id}:{owner}:{repo}:{branch}:{asset_kind}"

    git_source_id = source_ref.get("git_source_id")
    if git_source_id is not None:
        return f"git:{kb_id}:{git_source_id}:{connector}:{asset_kind}"

    datasource_id = source_ref.get("datasource_id")
    databases = _sorted_csv(source_ref.get("database_names") or source_ref.get("databases"))
    if connector == "database" and datasource_id is not None:
        return f"dbscope:{kb_id}:{datasource_id}:{databases}:{asset_kind}"

    import_id = source_ref.get("import_id")
    if import_id is not None:
        return f"dbimport:{kb_id}:{import_id}:{connector}:{asset_kind}"

    source_id = source_ref.get("source_id")
    object_id = source_ref.get("object_id")
    if source_id is not None and object_id is not None:
        return f"api:{kb_id}:{source_id}:{object_id}:{connector}:{asset_kind}"

    source_id_alt = source_ref.get("api_source_id")
    if source_id_alt is not None and object_id is not None:
        return f"api:{kb_id}:{source_id_alt}:{object_id}:{connector}:{asset_kind}"

    filename = _to_str(source_ref.get("filename") or source_ref.get("ref") or pkg.get("title") or "")
    if connector == "file" and filename:
        return f"file:{kb_id}:{_normalized_doc_title(filename)}:{asset_kind}"

    entry_id = source_ref.get("entry_id")
    if entry_id is not None:
        return f"entry:{kb_id}:{entry_id}:{connector}:{asset_kind}"

    linked_entry_ids = pkg.get("linked_entry_ids")
    if isinstance(linked_entry_ids, list) and len(linked_entry_ids) == 1:
        return f"entrylist:{kb_id}:{linked_entry_ids[0]}:{connector}:{asset_kind}"

    document_id = source_ref.get("document_id") or pkg.get("linked_document_id")
    if document_id is not None:
        return f"doc:{kb_id}:{document_id}:{connector}:{asset_kind}"

    title = _to_str(pkg.get("title") or "")
    if title and connector and asset_kind:
        normalized_title = _normalized_doc_title(title) if connector == "file" else title.lower()
        return f"title:{kb_id}:{normalized_title}:{connector}:{asset_kind}"
    return None


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
    normalized_title = title.strip() or "未命名证据包"
    normalized_source_ref = source_ref if isinstance(source_ref, dict) else {}
    normalized_linked_entry_ids = linked_entry_ids if isinstance(linked_entry_ids, list) else []
    candidate = {
        "kb_id": kb_id,
        "connector": connector,
        "asset_kind": asset_kind,
        "title": normalized_title,
        "source_ref": normalized_source_ref,
        "linked_entry_ids": normalized_linked_entry_ids,
        "linked_document_id": linked_document_id,
    }
    target_key = _dedupe_key(candidate)

    row: EvidencePackage | None = None
    if target_key:
        rows = db.execute(
            select(EvidencePackage).where(
                EvidencePackage.knowledge_base_id == kb_id,
                EvidencePackage.connector == connector,
                EvidencePackage.asset_kind == asset_kind,
            )
        ).scalars().all()
        for existed in rows:
            existed_key = _dedupe_key(_row_to_dict(existed))
            if existed_key == target_key:
                row = existed
                break

    if row is None:
        row = EvidencePackage(
            knowledge_base_id=kb_id,
            asset_kind=asset_kind,
            connector=connector,
            title=normalized_title,
            source_ref=normalized_source_ref,
            linked_entry_ids=normalized_linked_entry_ids,
            linked_document_id=linked_document_id,
            processing_state=processing_state,
        )
        db.add(row)
    else:
        row.title = normalized_title
        row.source_ref = normalized_source_ref
        row.linked_entry_ids = normalized_linked_entry_ids
        row.linked_document_id = linked_document_id
        row.processing_state = processing_state
        row.created_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    emit("evidence.registered", kb_id=kb_id, package_id=row.id, asset_kind=asset_kind)
    return row


def _dedupe_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pkg in packages:
        key = _dedupe_key(pkg)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(pkg)
    return deduped


def list_all_packages(db: Session, kb_id: int) -> list[dict[str, Any]]:
    """DB-registered packages first, then synthetic-only sources not linked to a row."""
    db_rows = db.execute(
        select(EvidencePackage)
        .where(EvidencePackage.knowledge_base_id == kb_id)
        .order_by(EvidencePackage.id.desc())
    ).scalars().all()
    persistent = _dedupe_packages([_row_to_dict(r) for r in db_rows])

    synthetic = list_synthetic_packages(db, kb_id)
    synthetic = [p for p in synthetic if not (isinstance(p.get("source_ref"), dict) and p["source_ref"].get("document_pipeline"))]
    synthetic = _dedupe_packages(synthetic)

    if persistent:
        persistent_keys = {k for k in (_dedupe_key(p) for p in persistent) if k}
        synthetic = [p for p in synthetic if (_dedupe_key(p) not in persistent_keys)]

    return persistent + synthetic


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
