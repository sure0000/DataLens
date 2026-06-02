"""Tests for entity version tracking and semantic change detection (P3.1)."""

import pytest
from services.extraction.entity_version_tracker import (
    _detect_semantic_changes,
    _TRACKED_PROPERTIES,
    _TRACKED_RELATIONSHIPS,
)
from services.ontology_triple_cleaner import RawTriple
from ontology import NS


def _triple(subj, pred, obj, is_uri=False):
    return RawTriple(subj, pred, obj, is_uri)


class TestDetectSemanticChanges:
    def test_new_entity_detects_added_properties(self):
        """New properties not in existing state are detected as additions."""
        new_triples = [
            _triple("http://example/term/a", "http://www.w3.org/2004/02/skos/core#prefLabel", "GMV"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, {})
        assert any("新增标签" in c for c in changes)

    def test_label_changed(self):
        """prefLabel change is detected."""
        existing = {"http://www.w3.org/2004/02/skos/core#prefLabel": ["GMV"]}
        new_triples = [
            _triple("http://example/term/a", "http://www.w3.org/2004/02/skos/core#prefLabel", "总交易额"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert any("标签" in c for c in changes)

    def test_definition_changed(self):
        """definition change is detected."""
        existing = {"http://www.w3.org/2004/02/skos/core#definition": ["旧定义"]}
        new_triples = [
            _triple("http://example/term/a", "http://www.w3.org/2004/02/skos/core#definition", "新定义"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert any("定义" in c for c in changes)

    def test_formula_changed(self):
        """formula change is detected."""
        existing = {f"{NS}formula": ["SUM(amount)"]}
        new_triples = [
            _triple("http://example/metric/a", f"{NS}formula", "SUM(amount) / COUNT(*)"),
        ]
        changes = _detect_semantic_changes("http://example/metric/a", new_triples, existing)
        assert any("公式" in c for c in changes)

    def test_confidence_changed(self):
        """confidence change is detected."""
        existing = {f"{NS}confidence": ["70.0"]}
        new_triples = [
            _triple("http://example/term/a", f"{NS}confidence", "85.0"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert any("置信度" in c for c in changes)

    def test_no_change_when_identical(self):
        """Identical old and new values produce no changes."""
        existing = {
            "http://www.w3.org/2004/02/skos/core#prefLabel": ["GMV"],
            f"{NS}confidence": ["80.0"],
        }
        new_triples = [
            _triple("http://example/term/a", "http://www.w3.org/2004/02/skos/core#prefLabel", "GMV"),
            _triple("http://example/term/a", f"{NS}confidence", "80.0"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert changes == []

    def test_relationship_added(self):
        """New relationship is detected."""
        existing = {}
        new_triples = [
            _triple("http://example/term/a", f"{NS}dependsOn", "http://example/term/b", is_uri=True),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert any("依赖关系" in c for c in changes)

    def test_relationship_removed(self):
        """Removed relationship is detected."""
        existing = {f"{NS}dependsOn": ["http://example/term/b"]}
        new_triples = []
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert any("依赖关系" in c for c in changes)

    def test_relationship_modified(self):
        """Relationship change (+add/-remove) is detected."""
        existing = {f"{NS}dependsOn": ["http://example/term/b"]}
        new_triples = [
            _triple("http://example/term/a", f"{NS}dependsOn", "http://example/term/c", is_uri=True),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert any("依赖关系" in c for c in changes)

    def test_multiple_changes_combined(self):
        """Multiple property changes produce multiple change notes."""
        existing = {
            "http://www.w3.org/2004/02/skos/core#prefLabel": ["旧名称"],
            f"{NS}confidence": ["70.0"],
        }
        new_triples = [
            _triple("http://example/term/a", "http://www.w3.org/2004/02/skos/core#prefLabel", "新名称"),
            _triple("http://example/term/a", f"{NS}confidence", "90.0"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert len(changes) >= 2

    def test_ignores_rdf_type_changes(self):
        """rdf:type is not a tracked property."""
        existing = {"http://www.w3.org/1999/02/22-rdf-syntax-ns#type": ["http://old/Type"]}
        new_triples = [
            _triple("http://example/term/a", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", f"{NS}BusinessTerm", is_uri=True),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        assert changes == []

    def test_other_entity_triples_filtered_out(self):
        """Only triples matching the target entity IRI are compared."""
        existing = {"http://www.w3.org/2004/02/skos/core#prefLabel": ["GMV"]}
        # All new triples are for a different entity, so target entity sees removals
        new_triples = [
            _triple("http://example/term/other", "http://www.w3.org/2004/02/skos/core#prefLabel", "GMV"),
        ]
        changes = _detect_semantic_changes("http://example/term/a", new_triples, existing)
        # Entity "a" has existing state but no new triples → removals detected
        assert any("移除标签" in c for c in changes)
