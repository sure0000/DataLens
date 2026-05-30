"""Evidence package registry — persistent rows + merge with synthesized sources."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Document, EvidencePackage, KnowledgeGitSource
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
        return f"gitrepo:{kb_id}:{owner}:{repo}:{branch}"

    git_source_id = source_ref.get("git_source_id")
    if git_source_id is not None and connector == "git":
        return f"git:{kb_id}:{git_source_id}"

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
        if connector == "git":
            rows = db.execute(
                select(EvidencePackage).where(
                    EvidencePackage.knowledge_base_id == kb_id,
                    EvidencePackage.connector == "git",
                )
            ).scalars().all()
        else:
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


def _prefer_evidence_package(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """合并同一来源的重复证据包视图，保留进度更完整的一条。"""
    if current.get("persistent") and not candidate.get("persistent"):
        return current
    if candidate.get("persistent") and not current.get("persistent"):
        return candidate

    cur_idx = int(current.get("indexed_document_count") or 0)
    cand_idx = int(candidate.get("indexed_document_count") or 0)
    if cur_idx != cand_idx:
        return current if cur_idx > cand_idx else candidate

    state_rank = {
        "ready_for_extraction": 4,
        "indexed": 3,
        "normalized": 2,
        "registered": 1,
    }
    cur_rank = state_rank.get(str(current.get("processing_state") or ""), 0)
    cand_rank = state_rank.get(str(candidate.get("processing_state") or ""), 0)
    if cur_rank != cand_rank:
        return current if cur_rank > cand_rank else candidate

    cur_db = current.get("db_id")
    cand_db = candidate.get("db_id")
    if isinstance(cur_db, int) and isinstance(cand_db, int) and cur_db != cand_db:
        return current if cur_db < cand_db else candidate
    return current


def _dedupe_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for pkg in packages:
        key = _dedupe_key(pkg)
        if key and key in seen:
            idx = seen[key]
            deduped[idx] = _prefer_evidence_package(deduped[idx], pkg)
            continue
        if key:
            seen[key] = len(deduped)
        deduped.append(pkg)
    return deduped


def _resolve_git_source_id(db: Session, kb_id: int, src: dict[str, Any]) -> int | None:
    """Resolve git_source_id from source_ref, including owner/repo fallback."""
    git_source_id = src.get("git_source_id")
    if git_source_id is not None:
        try:
            return int(git_source_id)
        except (TypeError, ValueError):
            pass

    owner = _to_str(src.get("owner") or "")
    repo = _to_str(src.get("repo") or "")
    if not owner or not repo:
        return None

    gs = db.execute(
        select(KnowledgeGitSource.id).where(
            KnowledgeGitSource.knowledge_base_id == kb_id,
            KnowledgeGitSource.owner == owner,
            KnowledgeGitSource.repo == repo,
        ).limit(1)
    ).scalar_one_or_none()
    if gs is None:
        return None

    gid = int(gs)
    src["git_source_id"] = gid
    return gid


def _hydrate_git_packages(db: Session, kb_id: int, packages: list[dict[str, Any]]) -> None:
    """Attach git sync / pipeline / entry linkage for persistent git evidence packages."""
    from services.ingestion.evidence import (
        _git_file_entry_ids,
        _git_processing_state,
        _git_sync_ok,
        _latest_git_pipeline_status,
    )

    for pkg in packages:
        if pkg.get("connector") != "git":
            continue
        src = pkg.get("source_ref")
        if not isinstance(src, dict):
            continue
        gid = _resolve_git_source_id(db, kb_id, src)
        if gid is None:
            continue

        db_id = pkg.get("db_id")
        if isinstance(db_id, int) and pkg.get("persistent"):
            row = db.get(EvidencePackage, db_id)
            if row is not None and isinstance(row.source_ref, dict):
                if row.source_ref.get("git_source_id") != gid:
                    row.source_ref = {**row.source_ref, "git_source_id": gid}
                    row.updated_at = datetime.utcnow()
                    db.flush()

        gs = db.get(KnowledgeGitSource, gid)
        if gs is None or gs.knowledge_base_id != kb_id:
            continue

        git_entry_ids = _git_file_entry_ids(db, kb_id, gid)
        if git_entry_ids:
            pkg["linked_entry_ids"] = git_entry_ids

        pipeline_status = _latest_git_pipeline_status(db, kb_id, gid)
        pkg["processing_state"] = _git_processing_state(gs.last_sync_status, pipeline_status)

        if not _git_sync_ok(gs.last_sync_status):
            continue

        entry_ids = pkg.get("linked_entry_ids")
        if not isinstance(entry_ids, list) or not entry_ids:
            continue

        docs = db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id.in_(entry_ids),
            )
        ).scalars().all()
        if not docs:
            continue
        total = len(docs)
        indexed = sum(1 for d in docs if (d.status or "") == "indexed")
        failed = sum(1 for d in docs if (d.status or "") == "failed")
        pkg["document_count"] = total
        pkg["indexed_document_count"] = indexed
        pkg["failed_document_count"] = failed


def _hydrate_package_document_stats(db: Session, kb_id: int, packages: list[dict[str, Any]]) -> None:
    """Attach per-package document/index/failed counts for frontend status dots."""
    if not packages:
        return

    linked_doc_ids: set[int] = set()
    linked_entry_ids: set[int] = set()

    for pkg in packages:
        lid = pkg.get("linked_document_id")
        if isinstance(lid, int):
            linked_doc_ids.add(lid)

        entry_ids = pkg.get("linked_entry_ids")
        if isinstance(entry_ids, list):
            for eid in entry_ids:
                if isinstance(eid, int):
                    linked_entry_ids.add(eid)

        src = pkg.get("source_ref")
        if isinstance(src, dict) and isinstance(src.get("entry_id"), int):
            linked_entry_ids.add(int(src["entry_id"]))

    docs_by_id: dict[int, Document] = {}
    docs_by_entry: dict[int, list[Document]] = {}

    if linked_doc_ids:
        docs = db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.id.in_(linked_doc_ids),
            )
        ).scalars().all()
        docs_by_id = {int(d.id): d for d in docs}

    if linked_entry_ids:
        docs = db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id.in_(linked_entry_ids),
            )
        ).scalars().all()
        for d in docs:
            if d.knowledge_entry_id is None:
                continue
            docs_by_entry.setdefault(int(d.knowledge_entry_id), []).append(d)

    for pkg in packages:
        matched: dict[int, Document] = {}

        lid = pkg.get("linked_document_id")
        if isinstance(lid, int):
            d = docs_by_id.get(lid)
            if d is not None:
                matched[int(d.id)] = d

        entry_ids: set[int] = set()
        raw_entry_ids = pkg.get("linked_entry_ids")
        if isinstance(raw_entry_ids, list):
            for eid in raw_entry_ids:
                if isinstance(eid, int):
                    entry_ids.add(eid)
        src = pkg.get("source_ref")
        if isinstance(src, dict) and isinstance(src.get("entry_id"), int):
            entry_ids.add(int(src["entry_id"]))

        for eid in entry_ids:
            for d in docs_by_entry.get(eid, []):
                matched[int(d.id)] = d

        if not matched:
            continue

        docs = list(matched.values())
        total = len(docs)
        indexed = sum(1 for d in docs if (d.status or "") == "indexed")
        failed = sum(1 for d in docs if (d.status or "") == "failed")
        pkg["document_count"] = total
        pkg["indexed_document_count"] = indexed
        pkg["failed_document_count"] = failed


def list_all_packages(db: Session, kb_id: int) -> list[dict[str, Any]]:
    """DB-registered packages first, then synthetic-only sources not linked to a row."""
    db_rows = db.execute(
        select(EvidencePackage)
        .where(EvidencePackage.knowledge_base_id == kb_id)
        .order_by(EvidencePackage.id.desc())
    ).scalars().all()
    persistent = _dedupe_packages([_row_to_dict(r) for r in db_rows])
    _hydrate_git_packages(db, kb_id, persistent)
    _hydrate_package_document_stats(db, kb_id, persistent)

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
