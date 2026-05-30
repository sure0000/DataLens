"""导入源级索引就绪检查。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.source_index_policy import assert_document_indexed_for_semantic_clean


def _scalar_result(value):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: value))


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class FakeSession:
    def __init__(self, *, api_source=None, entry_ids=None, documents=None, entries=None):
        self.api_source = api_source
        self.entry_ids = entry_ids or []
        self.documents = documents or []
        self.entries = entries or []

    def get(self, model, pk):
        if model.__name__ == "KnowledgeApiSource" and self.api_source and pk == self.api_source.id:
            return self.api_source
        return None

    def execute(self, stmt):
        sql = str(stmt).lower()
        if "knowledge_entries" in sql and "knowledge_base_id" in sql:
            return SimpleNamespace(scalars=lambda: _ScalarResult(self.entries))
        return _scalar_result(self.documents[0] if self.documents else None)

    def scalars(self, stmt):
        sql = str(stmt).lower()
        if "documents" in sql:
            return _ScalarResult(self.documents)
        if "knowledge_entries" in sql:
            return _ScalarResult(self.entry_ids)
        return _ScalarResult([])


def test_git_source_with_synced_entries_ok_without_docs():
    db = FakeSession(entry_ids=[1, 2])
    assert_document_indexed_for_semantic_clean(db, 1, 5, "git")


def test_git_source_no_entries_raises():
    db = FakeSession(entry_ids=[])
    with pytest.raises(ValueError, match="暂无已同步文件"):
        assert_document_indexed_for_semantic_clean(db, 1, 5, "git")


def test_api_source_requires_indexed_doc():
    api_src = SimpleNamespace(
        id=3, knowledge_base_id=1, integration="notion", object_id="page-1"
    )
    entry = SimpleNamespace(
        id=10,
        knowledge_base_id=1,
        source_meta={"kind": "notion_api", "api_source_id": "3", "ref": "page-1"},
    )
    doc = SimpleNamespace(
        status="indexed",
        index_attempts=1,
        error_message=None,
        knowledge_entry_id=10,
    )
    db = FakeSession(api_source=api_src, documents=[doc])
    db.entries = [entry]
    assert_document_indexed_for_semantic_clean(db, 1, 3, "api")


def test_file_entry_not_indexed_raises():
    doc = SimpleNamespace(status="chunking", index_attempts=1, error_message=None)
    db = FakeSession(documents=[doc])
    with pytest.raises(ValueError, match="尚未完成索引"):
        assert_document_indexed_for_semantic_clean(db, 1, 10, "file")


def test_database_skips_check():
    db = FakeSession()
    assert_document_indexed_for_semantic_clean(db, 1, 1, "database")
