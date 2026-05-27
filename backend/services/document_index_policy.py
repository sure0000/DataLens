"""Document indexing attempt limits and semantic-clean readiness checks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Document

MAX_AUTO_INDEX_ATTEMPTS = 3

_DOC_SOURCE_TYPES = frozenset({"file", "api"})


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
    """Raise ValueError if a document-backed source is not indexed."""
    if source_type not in _DOC_SOURCE_TYPES:
        return

    doc = db.execute(
        select(Document).where(
            Document.knowledge_base_id == kb_id,
            Document.knowledge_entry_id == source_id,
        )
    ).scalars().first()
    if doc is None:
        raise ValueError("该源尚无文档索引记录，请等待导入流水线完成")
    if doc.status == "failed":
        attempts = int(doc.index_attempts or 0)
        if attempts >= MAX_AUTO_INDEX_ATTEMPTS:
            raise ValueError(
                f"文档索引已失败 {attempts} 次，请先使用「手动索引」完成索引后再进行语义清洗"
            )
        raise ValueError(
            f"文档索引失败（{doc.error_message or '未知原因'}），请先重试索引"
        )
    if doc.status != "indexed":
        raise ValueError(f"文档尚未完成索引（当前：{doc.status}），请稍候或先完成索引")
