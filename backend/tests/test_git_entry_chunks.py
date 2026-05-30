"""Tests for git entry → LLM chunk adaptation."""

from __future__ import annotations

from types import SimpleNamespace

from services.extraction.git_entry_chunks import git_entries_as_llm_chunks


def test_git_entries_as_llm_chunks_builds_content():
    entry = SimpleNamespace(
        id=1,
        title="domain.py",
        body='"""领域模型"""\nclass CustomerType(str, Enum):\n    RESIDENTIAL = "RESIDENTIAL"\n' * 3,
        source_meta={"ref": "src/models/domain.py", "kind": "git_file"},
    )
    chunks = git_entries_as_llm_chunks([entry], min_body_chars=50)
    assert len(chunks) == 1
    assert "src/models/domain.py" in chunks[0].content
    assert "CustomerType" in chunks[0].content
    assert chunks[0].id is None


def test_git_entries_as_llm_chunks_skips_short_body():
    entry = SimpleNamespace(
        id=2,
        title="tiny.py",
        body="x = 1",
        source_meta={"ref": "tiny.py"},
    )
    assert git_entries_as_llm_chunks([entry], min_body_chars=50) == []
