"""Phase 1 轻量语义层：grounding 解析与 role 聚合单测。"""

from __future__ import annotations

from types import SimpleNamespace

from services.chunk_semantic_structuring import _normalize_semantic_meta
from services.context_builder import candidate_table_ids_from_domain_knowledge
from services.semantic_grounding import (
    dominant_semantic_role,
    infer_semantic_role_hints,
    match_tables_from_grounding,
    table_ids_from_bound_refs,
)


def _table(tid: int, db: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=tid, database_name=db, table_name=name)


def test_normalize_semantic_meta_defaults_invalid_role():
    meta = _normalize_semantic_meta({"semantic_role": "unknown", "confidence": 120})
    assert meta["semantic_role"] == "general_reference"
    assert meta["confidence"] == 100.0
    assert meta["grounding"]["table_refs"] == []


def test_normalize_semantic_meta_keeps_grounding():
    meta = _normalize_semantic_meta(
        {
            "semantic_role": "business_metric",
            "grounding": {
                "table_refs": [" sales.orders ", ""],
                "column_refs": ["orders.amount"],
            },
            "confidence": 88,
        }
    )
    assert meta["semantic_role"] == "business_metric"
    assert meta["grounding"]["table_refs"] == ["sales.orders"]
    assert meta["grounding"]["column_refs"] == ["orders.amount"]


def test_normalize_semantic_meta_parses_join_edges():
    meta = _normalize_semantic_meta(
        {
            "semantic_role": "join_guide",
            "join_edges": [
                {"left": "sales.orders", "right": "order_items", "on": "orders.id = order_items.order_id"},
                {"left": "", "right": "x"},
            ],
        }
    )
    assert len(meta["join_edges"]) == 1
    assert meta["join_edges"][0]["left"] == "sales.orders"


def test_infer_semantic_role_hints():
    assert "business_metric" in infer_semantic_role_hints("近30天 GMV 口径是多少")
    assert "join_guide" in infer_semantic_role_hints("orders 和 order_items 怎么关联")


def test_table_ids_from_bound_refs():
    tables = [_table(5, "sales", "orders")]
    ids = table_ids_from_bound_refs(tables, ["sales.orders"], allowed={5})
    assert ids == {5}


def test_match_tables_from_grounding_fq_and_column_refs():
    tables = [
        _table(1, "sales", "orders"),
        _table(2, "sales", "order_items"),
        _table(3, "sales", "order"),
    ]
    grounding = {
        "table_refs": ["sales.orders"],
        "column_refs": ["order_items.line_id"],
    }
    matched = match_tables_from_grounding(
        tables,
        grounding,
        already_matched=set(),
        allowed={1, 2, 3},
    )
    assert matched == [1, 2]


def test_match_tables_from_grounding_resolves_explicit_short_table_ref():
    tables = [_table(1, "sales", "order"), _table(2, "sales", "orders")]
    grounding = {"table_refs": ["order"], "column_refs": []}
    matched = match_tables_from_grounding(
        tables,
        grounding,
        already_matched=set(),
        allowed={1, 2},
    )
    assert matched == [1]


def test_dominant_semantic_role_weighted_by_confidence():
    role = dominant_semantic_role(
        [
            {"semantic_role": "general_reference", "confidence": 40},
            {"semantic_role": "business_metric", "confidence": 90},
            {"semantic_role": "business_metric", "confidence": 20},
        ]
    )
    assert role == "business_metric"


def test_candidate_table_ids_uses_semantic_grounding_on_chunks():
    """chunk hit 的 semantic_meta.grounding 应优先锚表。"""
    tables = [_table(10, "sales", "orders"), _table(20, "sales", "customers")]
    merged_hits = {
        "chunk:1": {
            "source_type": "chunk",
            "chunk_id": 1,
            "title": "指标说明",
            "summary": "",
            "snippet": "本段未出现表名",
            "semantic_meta": {
                "semantic_role": "business_metric",
                "grounding": {"table_refs": ["sales.orders"], "column_refs": []},
                "confidence": 90,
            },
        }
    }

    class _FakeSession:
        def execute(self, *_args, **_kwargs):
            class _R:
                def scalars(self):
                    return self

                def all(self):
                    return []

            return _R()

    ids, sources = candidate_table_ids_from_domain_knowledge(
        _FakeSession(),
        "GMV 口径",
        business_domain_id=1,
        domain_tables=tables,
        merged_hits=merged_hits,
    )
    assert ids == [10]
    assert "semantic_grounding" in sources[10]
