"""Copilot 域内表路由：P0-1~P0-3 单测。"""

from __future__ import annotations

from types import SimpleNamespace

from services.context_builder import (
    _fq_table_name_in_blob,
    match_tables_by_name_in_blob,
    merge_domain_candidate_table_ids,
    select_candidates_with_gradient_fallback,
)


def _table(tid: int, db: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=tid, database_name=db, table_name=name)


def test_rrf_merge_table_embedding_only_when_knowledge_empty():
    """知识未命中时，表向量直搜结果仍能进入候选。"""
    embedding_hits = [(42, 0.12), (7, 0.35), (99, 0.58)]
    ids, sources = merge_domain_candidate_table_ids(
        [],
        {},
        embedding_hits,
        max_candidates=3,
    )
    assert ids == [42, 7, 99]
    assert sources[42] == ["table_embedding"]
    assert sources[7] == ["table_embedding"]


def test_rrf_merge_boosts_table_in_both_signals():
    """同时被知识与表向量命中的表应排在前列。"""
    knowledge_ids = [10, 20]
    knowledge_sources = {
        10: {"knowledge", "explicit_link"},
        20: {"knowledge"},
    }
    embedding_hits = [(30, 0.1), (10, 0.2), (40, 0.3)]

    ids, sources = merge_domain_candidate_table_ids(
        knowledge_ids,
        knowledge_sources,
        embedding_hits,
        max_candidates=4,
    )

    assert 10 in ids[:2]
    assert set(sources[10]) == {"explicit_link", "knowledge", "table_embedding"}
    assert "table_embedding" in sources[30]
    assert "knowledge" in sources[20]
    assert "explicit_link" not in sources.get(20, [])


def test_merge_respects_max_candidates():
    knowledge_ids = [1, 2, 3, 4, 5]
    knowledge_sources = {i: {"knowledge"} for i in knowledge_ids}
    embedding_hits = [(6, 0.1), (7, 0.2)]

    ids, _sources = merge_domain_candidate_table_ids(
        knowledge_ids,
        knowledge_sources,
        embedding_hits,
        max_candidates=3,
    )

    assert len(ids) == 3


def test_gradient_fallback_high_confidence():
    scores = {1: 0.05, 2: 0.03, 3: 0.01}
    sources = {1: {"knowledge"}, 2: {"table_embedding"}, 3: {"knowledge"}}
    ids, out_src, reason = select_candidates_with_gradient_fallback(
        scores,
        sources,
        max_candidates=2,
        max_candidates_expanded=5,
        min_score=0.012,
        min_score_relaxed=0.006,
    )
    assert ids == [1, 2]
    assert reason == ""
    assert out_src[1] == ["knowledge"]


def test_gradient_fallback_expanded_when_below_min_score():
    scores = {1: 0.008, 2: 0.007}
    sources = {1: {"table_embedding"}, 2: {"table_embedding"}}
    ids, _out_src, reason = select_candidates_with_gradient_fallback(
        scores,
        sources,
        max_candidates=1,
        max_candidates_expanded=2,
        min_score=0.012,
        min_score_relaxed=0.006,
    )
    assert ids == [1, 2]
    assert reason == "low_confidence_expanded_top_k"


def test_gradient_fallback_domain_full_when_no_scores():
    ids, _out_src, reason = select_candidates_with_gradient_fallback(
        {},
        {},
        max_candidates=10,
        max_candidates_expanded=20,
        min_score=0.012,
        min_score_relaxed=0.006,
    )
    assert ids == []
    assert reason == "no_semantic_signals"


def test_fq_table_name_boundary_match():
    blob = "请查询 sales.orders 的 GMV，关联 sales.order_items"
    assert _fq_table_name_in_blob("sales", "orders", blob.lower())
    assert _fq_table_name_in_blob("sales", "order_items", blob.lower())
    assert not _fq_table_name_in_blob("sales", "order", blob.lower())


def test_short_table_name_not_matched_by_substring():
    tables = [
        _table(1, "sales", "order"),
        _table(2, "sales", "order_items"),
    ]
    blob = "分析 sales.order_items 明细"
    matched = match_tables_by_name_in_blob(
        tables, blob, already_matched=set(), allowed={1, 2}
    )
    assert 2 in matched
    assert 1 not in matched


def test_long_table_name_token_match():
    tables = [_table(3, "dw", "customer_profile")]
    blob = "按 customer_profile 维度 breakdown"
    matched = match_tables_by_name_in_blob(
        tables, blob, already_matched=set(), allowed={3}
    )
    assert matched == [3]
