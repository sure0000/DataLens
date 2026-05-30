"""Adapt git KnowledgeEntry bodies as chunk-like inputs for LLM extractors."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from services.extraction.code_patterns.router import entry_path

_DEFAULT_MIN_BODY_CHARS = 50
_DEFAULT_MAX_CHARS = 8000


def git_entries_as_llm_chunks(
    entries: list[Any],
    *,
    min_body_chars: int = _DEFAULT_MIN_BODY_CHARS,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> list[Any]:
    """Build pseudo-chunks from synced git file bodies (no Document index required)."""
    chunks: list[Any] = []
    for entry in entries:
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < min_body_chars:
            continue
        ref = entry_path(entry)
        truncated = body[:max_chars]
        prefix = f"# File: {ref}\n\n" if ref else ""
        chunks.append(
            SimpleNamespace(
                id=None,
                content=f"{prefix}{truncated}",
                semantic_meta={},
            )
        )
    return chunks
