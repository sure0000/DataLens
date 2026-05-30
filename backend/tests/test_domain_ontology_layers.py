"""Tests for business-domain ontology layer aggregation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.ontology.domain_aggregation import domain_layer_detail, domain_layers_summary


def test_domain_layers_summary_sums_counts():
    kb = MagicMock()
    kb.id = 1
    kb.name = "KB-A"

    with (
        patch(
            "services.ontology.domain_aggregation._domain_kb_rows",
            return_value=[kb],
        ),
        patch(
            "services.ontology.domain_aggregation._merge_layer_counts",
            return_value={
                "vocabulary": 3,
                "rule": 2,
                "entity-concept": 5,
                "dimension": 1,
                "relation": 4,
                "attribute": 10,
            },
        ),
        patch(
            "services.ontology.modeling_layers.build_layers_summary",
            side_effect=lambda counts: {k: {"total": v, "label": k} for k, v in counts.items()},
        ),
    ):
        result = domain_layers_summary(MagicMock(), domain_id=9)

    assert result["ok"] is True
    assert result["domain_id"] == 9
    assert result["knowledge_base_count"] == 1
    assert result["layers"]["vocabulary"]["total"] == 3
    assert result["layers"]["attribute"]["total"] == 10


def test_domain_layer_detail_enriches_origin():
    kb = MagicMock()
    kb.id = 7
    kb.name = "Sales KB"
    item = {"s": "http://ex/term/1", "label": "GMV"}

    with (
        patch(
            "services.ontology.domain_aggregation._domain_kb_rows",
            return_value=[kb],
        ),
        patch(
            "services.ontology.domain_aggregation._filter_kb_ids",
            side_effect=lambda rows, _kb_filter: rows,
        ),
        patch(
            "services.ontology.domain_aggregation.fetch_grounded_sources",
            return_value={"http://ex/term/1": {"source_label": "指标手册.pdf"}},
        ),
        patch(
            "services.ontology.modeling_layers.fetch_items_for_layer",
            return_value=[item],
        ),
        patch(
            "services.ontology.modeling_layers.get_layer_metadata",
            return_value={
                "layer_key": "vocabulary",
                "label": "词汇层",
                "description": "业务术语定义",
                "ontology_class": "dl:BusinessTerm",
                "criteria": None,
            },
        ),
        patch(
            "services.ontology.modeling_layers.normalize_layer_key",
            return_value="vocabulary",
        ),
    ):
        result = domain_layer_detail(MagicMock(), domain_id=9, layer_key="vocabulary", limit=10, offset=0)

    assert result["ok"] is True
    assert result["total"] == 1
    assert result["items"][0]["label"] == "GMV"
    assert result["items"][0]["origin"]["knowledge_base_name"] == "Sales KB"
    assert result["items"][0]["origin"]["source_label"] == "指标手册.pdf"


def test_domain_layer_detail_unknown_layer():
    with patch("services.ontology.modeling_layers.normalize_layer_key", return_value=None):
        result = domain_layer_detail(MagicMock(), domain_id=1, layer_key="unknown")
    assert result["ok"] is False
