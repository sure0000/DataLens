"""embedding_service 单测：Few-shot 域隔离（P0-5）。"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.embedding_service import _search_similar_with_vector


def test_search_similar_filters_by_allowed_table_ids():
    row_a = MagicMock(ref_type="query", ref_id=10, content="q1 -> sql1")
    row_b = MagicMock(ref_type="query", ref_id=99, content="q2 -> sql2")

    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [row_a]
    db.execute.return_value.scalars.return_value = scalars

    qv = [0.1] * 1536
    out = _search_similar_with_vector(
        db, qv, top_k=5, table_id=None, ref_type="query", allowed_table_ids={10, 20}
    )
    assert len(out) == 1
    assert out[0]["ref_id"] == 10


def test_search_similar_empty_allowed_returns_empty():
    db = MagicMock()
    qv = [0.1] * 1536
    out = _search_similar_with_vector(
        db, qv, top_k=5, table_id=None, ref_type="query", allowed_table_ids=set()
    )
    assert out == []
    db.execute.assert_not_called()
