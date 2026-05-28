"""Document indexing attempt limits and semantic-clean readiness checks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import Document

MAX_AUTO_INDEX_ATTEMPTS = 3


def bump_index_attempt(doc: Document) -> int:
    doc.index_attempts = int(doc.index_attempts or 0) + 1
    return doc.index_attempts


def can_auto_retry_index(doc: Document) -> bool:
    if not (doc.raw_text or "").strip():
        return False
    if doc.status == "pending":
        return True
    return doc.status == "failed" and int(doc.index_attempts or 0) < MAX_AUTO_INDEX_ATTEMPTS


def can_manual_index(doc: Document) -> bool:
    return doc.status == "failed" and bool((doc.raw_text or "").strip())


def assert_document_indexed_for_semantic_clean(
    db: Session,
    kb_id: int,
    source_id: int,
    source_type: str,
) -> None:
    """Raise ValueError if source is not ready for semantic cleaning."""
    from services.source_index_policy import assert_document_indexed_for_semantic_clean as _assert

    _assert(db, kb_id, source_id, source_type)
