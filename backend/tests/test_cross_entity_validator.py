"""Tests for cross-entity referential integrity validation."""

import pytest
from services.extraction.cross_entity_validator import (
    CrossEntityReport,
    validate_cross_entity_consistency,
)
from services.ontology_triple_cleaner import RawTriple


NS = "https://datalens.local/ontology/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _make_triple(s, p, o, is_uri=False):
    return RawTriple(subject=s, predicate=p, object=o, object_is_uri=is_uri)


class TestCrossEntityValidation:
    def test_passes_when_all_refs_exist_in_batch(self):
        """A dependsOn B, and both A and B are declared in the same batch."""
        triples = [
            _make_triple("http://a", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://b", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://a", f"{NS}dependsOn", "http://b", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert report.passed
        assert len(report.violations) == 0

    def test_detects_missing_depends_on_target(self):
        """A dependsOn B, but B is not in the batch or graph."""
        triples = [
            _make_triple("http://a", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://a", f"{NS}dependsOn", "http://missing", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert not report.passed
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v["predicate_short"] == "dependsOn"
        assert v["missing_target"] == "http://missing"

    def test_detects_missing_derived_from_target(self):
        """Metric A derivedFrom Metric B, but B is missing."""
        triples = [
            _make_triple("http://m1", RDF_TYPE, f"{NS}Metric", True),
            _make_triple("http://m1", f"{NS}derivedFrom", "http://m2", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert not report.passed
        assert len(report.violations) == 1
        assert report.violations[0]["predicate_short"] == "derivedFrom"

    def test_ignores_literal_objects(self):
        """Literal objects should not trigger reference checks."""
        triples = [
            _make_triple("http://a", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://a", f"{NS}dependsOn", "just a string", False),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert report.passed

    def test_detects_orphan_business_rule(self):
        """BusinessRule with no valid appliesTo target."""
        triples = [
            _make_triple("http://rule1", RDF_TYPE, f"{NS}BusinessRule", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert not report.passed
        assert any(v["predicate_short"] == "appliesTo" for v in report.violations)

    def test_business_rule_with_valid_applies_to_passes(self):
        """BusinessRule with appliesTo to an existing entity passes."""
        triples = [
            _make_triple("http://rule1", RDF_TYPE, f"{NS}BusinessRule", True),
            _make_triple("http://term1", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://rule1", f"{NS}appliesTo", "http://term1", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert report.passed

    def test_detects_missing_computed_from_table(self):
        """Metric computedFromTable should reference an existing entity."""
        triples = [
            _make_triple("http://m1", RDF_TYPE, f"{NS}Metric", True),
            _make_triple("http://m1", f"{NS}computedFromTable", "http://missing_table", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert not report.passed

    def test_aggregates_over_missing_dimension(self):
        """Metric aggregatesOver should reference an existing Dimension."""
        triples = [
            _make_triple("http://m1", RDF_TYPE, f"{NS}Metric", True),
            _make_triple("http://m1", f"{NS}aggregatesOver", "http://dim_missing", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert not report.passed
        assert any(v["predicate_short"] == "aggregatesOver" for v in report.violations)

    def test_stats_are_populated(self):
        triples = [
            _make_triple("http://a", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://b", RDF_TYPE, f"{NS}BusinessTerm", True),
            _make_triple("http://a", f"{NS}dependsOn", "http://b", True),
        ]
        report = validate_cross_entity_consistency(triples, kb_id=1, store=None)
        assert report.stats["total_triples_checked"] == 3
        assert report.stats["reference_triples_checked"] == 1
        assert report.stats["violations_found"] == 0
        assert report.stats["batch_entities"] == 2
