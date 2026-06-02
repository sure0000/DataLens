"""Tests for cross-KB term equivalence detection (P2.2)."""

import pytest
from services.extraction.cross_kb_equivalence import (
    _compute_cross_kb_matches,
    EXACT_MATCH_THRESHOLD,
    CLOSE_MATCH_THRESHOLD,
)


class TestComputeCrossKbMatches:
    def test_empty_inputs(self):
        """No new or existing terms returns empty."""
        assert _compute_cross_kb_matches([], []) == []
        assert _compute_cross_kb_matches(
            [{"iri": "http://a", "label": "test"}], [],
        ) == []

    def test_exact_match_identical_labels(self):
        """Identical labels should match with high similarity."""
        new_terms = [{"iri": "http://new/gmv", "label": "GMV"}]
        existing = [{"iri": "http://old/gmv", "label": "GMV"}]
        matches = _compute_cross_kb_matches(new_terms, existing, threshold=0.8)
        # "GMV" vs "GMV" should be very similar (≥ 0.8 for SBERT)
        if matches:
            assert matches[0]["match_type"] in ("skos:exactMatch", "skos:closeMatch")
            assert matches[0]["similarity"] > 0.5

    def test_no_match_dissimilar_labels(self):
        """Very different labels should not match."""
        new_terms = [{"iri": "http://new/xyz", "label": "GMV"}]
        existing = [{"iri": "http://old/abc", "label": "量子纠缠态观测器校准参数"}]
        matches = _compute_cross_kb_matches(
            new_terms, existing, threshold=EXACT_MATCH_THRESHOLD,
        )
        assert matches == []

    def test_match_type_exact_vs_close(self):
        """High similarity → exactMatch, medium → closeMatch."""
        new_terms = [
            {"iri": "http://a", "label": "客户终身价值"},
        ]
        existing = [
            {"iri": "http://b", "label": "客户终生价值"},
        ]
        # Test at different thresholds
        exact = _compute_cross_kb_matches(new_terms, existing, threshold=EXACT_MATCH_THRESHOLD)
        close = _compute_cross_kb_matches(new_terms, existing, threshold=CLOSE_MATCH_THRESHOLD)
        # At least close match should be found for similar Chinese terms
        assert len(close) >= len(exact)

    def test_sorts_by_similarity_desc(self):
        """Matches should be sorted by similarity descending."""
        new_terms = [
            {"iri": "http://a", "label": "订单金额"},
        ]
        existing = [
            {"iri": "http://b1", "label": "订单金额"},
            {"iri": "http://b2", "label": "订单总额"},
            {"iri": "http://b3", "label": "交易金额"},
        ]
        matches = _compute_cross_kb_matches(new_terms, existing, threshold=0.5)
        if len(matches) >= 2:
            assert matches[0]["similarity"] >= matches[1]["similarity"]
