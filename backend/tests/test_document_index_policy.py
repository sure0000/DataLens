"""文档索引次数与语义清洗前置条件。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.document_index_policy import (
    MAX_AUTO_INDEX_ATTEMPTS,
    assert_document_indexed_for_semantic_clean,
    bump_index_attempt,
    can_auto_retry_index,
    can_manual_index,
)


def test_bump_index_attempt():
    doc = SimpleNamespace(index_attempts=0)
    assert bump_index_attempt(doc) == 1
    assert bump_index_attempt(doc) == 2


def test_can_auto_retry_until_max():
    doc = SimpleNamespace(status="failed", index_attempts=0, raw_text="x")
    assert can_auto_retry_index(doc) is True
    doc.index_attempts = MAX_AUTO_INDEX_ATTEMPTS
    assert can_auto_retry_index(doc) is False
    doc.status = "pending"
    doc.index_attempts = 0
    assert can_auto_retry_index(doc) is True


def test_can_manual_index_when_failed_with_body():
    doc = SimpleNamespace(status="failed", index_attempts=MAX_AUTO_INDEX_ATTEMPTS, raw_text="body")
    assert can_manual_index(doc) is True
    doc.status = "indexed"
    assert can_manual_index(doc) is False
    doc.status = "failed"
    doc.raw_text = ""
    assert can_manual_index(doc) is False


def test_assert_semantic_clean_requires_indexed():
    doc = SimpleNamespace(
        knowledge_base_id=1,
        knowledge_entry_id=10,
        status="chunking",
        index_attempts=1,
        error_message=None,
    )
    db = SimpleNamespace()
    db.execute = lambda *_a, **_k: SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: doc))

    with pytest.raises(ValueError, match="尚未完成索引"):
        assert_document_indexed_for_semantic_clean(db, 1, 10, "file")
