"""Per-chunk progress callbacks for long-running LLM extraction loops."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

ChunkProgressCallback = Callable[[int, int], Awaitable[None] | None]


def nonempty_chunks(chunks: list[Any]) -> list[Any]:
    out: list[Any] = []
    for chunk in chunks:
        content = getattr(chunk, "content", "") or ""
        if content.strip():
            out.append(chunk)
    return out


async def iter_chunks_with_progress(
    chunks: list[Any],
    on_chunk_progress: ChunkProgressCallback | None = None,
) -> AsyncIterator[Any]:
    """Yield chunks with non-empty content; invoke callback as (done, total) before each."""
    eligible = nonempty_chunks(chunks)
    total = len(eligible)
    for index, chunk in enumerate(eligible, start=1):
        if on_chunk_progress is not None:
            result = on_chunk_progress(index, total)
            if result is not None:
                await result
        yield chunk
