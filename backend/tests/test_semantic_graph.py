"""Phase 3 语义关系图：同步与 graph_router 单测。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.routing.graph_router import (
    _neighbor_ref_from_relation,
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


def test_neighbor_ref_from_semantic_relation():
    primary = SimpleNamespace(id=1, database_name="sales", table_name="orders")
    rel = SimpleNamespace(
        relation_type="table_join",
        source_ref="orders",
        target_ref="order_items",
    )
    assert _neighbor_ref_from_relation(primary, rel) == "order_items"


def test_semantic_graph_neighbor_ids():
    db = MagicMock()
    primary = SimpleNamespace(id=10, database_name="sales", table_name="orders")
    neighbor = SimpleNamespace(id=20, database_name="sales", table_name="order_items")
    rel = SimpleNamespace(
        relation_type="table_join",
        source_ref="orders",
        target_ref="order_items",
    )
    db.execute.return_value.scalars.return_value.all.return_value = [rel]

    ids = _semantic_graph_neighbor_ids(
        db,
        [3],
        primary,
        [primary, neighbor],
        allowed={20},
        skip_ids=set(),
        top_k=4,
    )
    assert ids == [20]


def test_apply_graph_expansion_adds_semantic_graph_source():
    db = MagicMock()
    primary = SimpleNamespace(id=10, database_name="dw", table_name="orders")
    neighbor = SimpleNamespace(id=20, database_name="dw", table_name="customers")
    lg = SimpleNamespace(source_table="dw.orders", target_table="dw.customers")
    rel = SimpleNamespace(
        relation_type="table_join",
        source_ref="orders",
        target_ref="payments",
    )
    pay = SimpleNamespace(id=30, database_name="dw", table_name="payments")

    db.execute.return_value.scalars.return_value.all.side_effect = [[rel]]

    scores = {10: 0.05}
    sources: dict[int, set[str]] = {10: {"table_embedding"}}

    with patch("services.routing.graph_router.apply_lineage_expansion") as mock_lineage:
        mock_lineage.return_value = (scores, sources)
        with patch("services.routing.graph_router.get_settings") as mock_settings:
            mock_settings.return_value.copilot_lineage_expand_top_k = 4
            mock_settings.return_value.copilot_routing_weight_lineage = 0.006
            mock_settings.return_value.rrf_k = 60
            mock_settings.return_value.copilot_join_blacklist = ""
            new_scores, new_sources = apply_graph_expansion(
                db,
                [1],
                [primary, neighbor, pay],
                10,
                scores,
                sources,
                routing_bundle=None,
            )

    assert 30 in new_scores
    assert "semantic_graph" in new_sources[30]
