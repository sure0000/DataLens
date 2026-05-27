"""P1 路由：指标/术语、routing bundle、列扩表。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.context_builder import apply_column_dimension_expansion, compute_domain_table_scores
from services.routing.metric_router import _keyword_score, search_metrics_and_terms


def test_keyword_score_exact_name_match():
    assert _keyword_score("GMV", "近30天 GMV 趋势") >= 0.99


def test_keyword_score_prefix_table_not_exact():
    # token 部分重叠但非完整子串名命中
    assert _keyword_score("orders", "order_items 明细") < 0.99


def test_search_metrics_and_terms_keyword_only():
    """TODO(Phase 4): 更新测试以从 RDF 图中查询（旧 MetricDefinition / BusinessTerm 表已移除）。"""
    db = MagicMock()
    text, bound, bonuses = search_metrics_and_terms(
        db,
        "近30天 GMV",
        [3],
        [SimpleNamespace(id=10, database_name="sales", table_name="orders")],
        query_vector=None,
        embed_texts=None,
    )
    assert isinstance(text, str)
    assert isinstance(bound, set)
    assert isinstance(bonuses, dict)


def test_column_expansion_adds_dimension_table():
    db = MagicMock()
    col_rows = MagicMock()
    col_rows.scalars.return_value.all.return_value = ["dimension"]
    db.execute.return_value = col_rows

    scores = {1: 0.05}
    sources: dict[int, set[str]] = {1: {"table_embedding"}}

    with patch("services.context_builder.search_column_embeddings") as mock_col:
        mock_col.return_value = [(2, 0.1)]
        new_scores, new_sources = apply_column_dimension_expansion(
            db,
            "按渠道 breakdown",
            {1, 2},
            scores,
            sources,
            primary_table_id=1,
            query_vector=[0.1] * 8,
            top_k=2,
            weight=0.008,
            rrf_k=60,
        )
    assert 2 in new_scores
    assert "column_embedding" in new_sources[2]


def test_metric_bound_bonus_in_scores():
    scores, sources = compute_domain_table_scores(
        [1],
        {1: {"knowledge"}},
        [],
        weight_knowledge=1.0,
        weight_table_emb=1.0,
        explicit_link_bonus=0.02,
        rrf_k=60,
        metric_bound_bonus={1: 0.04},
    )
    assert scores[1] > 0.04
    assert "metric_term" in sources[1]
