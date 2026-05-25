"""retrieval_service 单测：统一 KB 检索（P0-4）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.retrieval_service import search_kb_hybrid_unified


@patch("services.retrieval_service.search_chunks_hybrid")
@patch("services.retrieval_service.search_entries_hybrid")
def test_search_kb_hybrid_unified_merges_entry_and_chunk(mock_entries, mock_chunks):
    mock_entries.return_value = [
        {
            "entry_id": 1,
            "title": "条目A",
            "summary": "简述",
            "snippet": "正文A",
            "rrf_score": 0.03,
        }
    ]
    mock_chunks.return_value = [
        {
            "chunk_id": 50,
            "document_id": 9,
            "content": "文档分块内容",
        }
    ]

    doc = MagicMock(id=9, title="流水线文档")
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [doc]

    results = search_kb_hybrid_unified(db, kb_id=3, query="GMV", top_k=4)
    assert len(results) >= 2
    types = {r["source_type"] for r in results}
    assert "entry" in types
    assert "chunk" in types
    chunk_hit = next(r for r in results if r["source_type"] == "chunk")
    assert chunk_hit["title"] == "流水线文档"
    assert "文档分块" in chunk_hit["snippet"]
