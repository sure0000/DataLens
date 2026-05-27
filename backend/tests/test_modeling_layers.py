"""Tests for ontology modeling layer summary and pagination."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.ontology import modeling_layers as ml


@pytest.fixture
def mock_counts():
    return {
        "vocabulary": 10,
        "rule": 5,
        "entity-concept": 3,
        "dimension": 2,
        "relation": 8,
        "attribute": 100,
    }


def test_get_cleaning_results_summary_excludes_items(mock_counts):
    db = MagicMock()
    with patch.object(ml, "_count_queries", return_value=mock_counts):
        result = ml.get_cleaning_results(db, kb_id=1)

    assert result["ok"] is True
    assert result["kb_id"] == 1
    for key, layer in result["layers"].items():
        assert "total" in layer
        assert "label" in layer
        assert "items" not in layer


def test_get_cleaning_results_include_items(mock_counts):
    db = MagicMock()
    sample_items = [{"s": "http://example.org/t1", "label": "Term"}]

    with patch.object(ml, "_count_queries", return_value=mock_counts):
        with patch.object(ml, "_fetch_layer_items", return_value=sample_items):
            result = ml.get_cleaning_results(db, kb_id=1, include_items=True)

    assert result["layers"]["vocabulary"]["items"] == sample_items


def test_get_modeling_layer_pagination():
    items = [{"s": f"http://ex.org/i{n}", "label": f"L{n}"} for n in range(12)]

    with patch.object(ml, "_count_queries", return_value={"vocabulary": 12}):
        with patch.object(ml, "_fetch_layer_items", return_value=items):
            page0 = ml.get_modeling_layer(1, "vocabulary", limit=5, offset=0)
            page1 = ml.get_modeling_layer(1, "vocabulary", limit=5, offset=5)
            last = ml.get_modeling_layer(1, "vocabulary", limit=5, offset=10)

    assert page0["ok"] is True
    assert page0["total"] == 12
    assert len(page0["items"]) == 5
    assert page0["items"][0]["label"] == "L0"
    assert page0["has_more"] is True
    assert page0["offset"] == 0
    assert page0["limit"] == 5

    assert len(page1["items"]) == 5
    assert page1["items"][0]["label"] == "L5"
    assert page1["has_more"] is True

    assert len(last["items"]) == 2
    assert last["has_more"] is False


def test_get_modeling_layer_unknown_key():
    result = ml.get_modeling_layer(1, "not-a-layer")
    assert result["ok"] is False
    assert "未知清洗层" in result["error"]


def test_normalize_layer_key_aliases():
    assert ml.normalize_layer_key("entity_concept") == "entity-concept"
    assert ml.normalize_layer_key("vocabulary") == "vocabulary"
    assert ml.normalize_layer_key("invalid") is None


def test_count_queries_sees_inserted_business_term(monkeypatch):
    """五层计数须能匹配入图时使用的 rdf:type 谓词（修复错误 rdf: 前缀）。"""
    import os

    from config import get_settings
    from ontology import NS, kb_graph_iri
    from services import ontology_store as osmod
    from services.ontology_store import insert_graph

    monkeypatch.setenv("FUSEKI_FALLBACK_MEMORY", "true")
    monkeypatch.delenv("FUSEKI_URL", raising=False)
    get_settings.cache_clear()
    osmod.reset_triple_store()

    kb_id = 42
    graph = kb_graph_iri(kb_id)
    insert_graph(
        graph,
        f"<http://ex/term1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{NS}BusinessTerm> .\n"
        f'<http://ex/term1> <http://www.w3.org/2004/02/skos/core#prefLabel> "GMV"@zh .\n'
        f'<http://ex/term1> <{NS}joinableWith> <http://ex/table2> .\n',
    )

    counts = ml._count_queries(kb_id)
    assert counts["vocabulary"] >= 1
    assert counts["relation"] >= 1

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    summary = ml.get_cleaning_results(db, kb_id=kb_id)
    assert summary["layers"]["vocabulary"]["total"] >= 1
    assert summary["layers"]["relation"]["total"] >= 1

    osmod.reset_triple_store()
    get_settings.cache_clear()
