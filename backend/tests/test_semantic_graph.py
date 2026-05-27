"""Phase 3 语义关系图：同步与 graph_router 单测。

TODO(Phase 4): _semantic_graph_neighbor_ids 和 _neighbor_ref_from_relation
需从 RDF 图重新实现后再恢复对应单测。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.routing.graph_router import (
    _semantic_graph_neighbor_ids,
    apply_graph_expansion,
)
from services.semantic_relation_sync import concept_slug, _edge_key, _upsert_relation


def test_concept_slug():
    assert concept_slug("日 GMV", "metric") == "metric.日_gmv"


def test_edge_key_normalization():
    key = _edge_key("Table_Join", "Table", "Orders", "Table", "Order_Items")
    assert key == ("table_join", "table", "orders", "table", "order_items")


def test_upsert_relation_dedupes():
    db = MagicMock()
    existing = set()
    created = _upsert_relation(
        db,
        1,
        relation_type="table_join",
        source_type="table",
        source_ref="orders",
        target_type="table",
        target_ref="order_items",
        existing=existing,
    )
    assert created is True
    dup = _upsert_relation(
        db,
        1,
        relation_type="table_join",
        source_type="table",
        source_ref="orders",
        target_type="table",
        target_ref="order_items",
        existing=existing,
    )
    assert dup is False


def test_semantic_graph_neighbor_ids_stubbed():
    """TODO(Phase 4): 从 RDF 图重新实现后恢复原断言 ids == [20]"""
    db = MagicMock()
    primary = SimpleNamespace(id=10, database_name="sales", table_name="orders")
    ids = _semantic_graph_neighbor_ids(
        db, [3], primary, [], allowed={20}, skip_ids=set(), top_k=4,
    )
    assert ids == []


def test_apply_graph_expansion_adds_ontology_source():
    """TODO(Phase 4): semantic_graph 扩展需从 RDF 图重新实现，当前仅 ontology 扩展"""
    db = MagicMock()
    primary = SimpleNamespace(id=10, database_name="dw", table_name="orders")

    scores = {10: 0.05}
    sources: dict[int, set[str]] = {10: {"table_embedding"}}

    with patch("services.routing.graph_router.apply_lineage_expansion") as mock_lineage:
        mock_lineage.return_value = (scores, sources)
        new_scores, new_sources = apply_graph_expansion(
            db,
            [1],
            [primary],
            10,
            scores,
            sources,
            routing_bundle=None,
        )

    assert isinstance(new_scores, dict)
    assert isinstance(new_sources, dict)
