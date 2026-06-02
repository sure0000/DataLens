"""Tests for hierarchy builder cycle detection and depth governance (P2.3)."""

import pytest
from services.extraction.hierarchy_builder import (
    _compute_depths,
    _detect_cycles,
    _quarantine_cycles_and_deep_paths,
    MAX_HIERARCHY_DEPTH,
    SKOS_BROADER,
    SKOS_NARROWER,
)
from services.ontology_triple_cleaner import RawTriple


def _broader(child, parent):
    return RawTriple(child, SKOS_BROADER, parent, True)

def _narrower(parent, child):
    return RawTriple(parent, SKOS_NARROWER, child, True)


class TestCycleDetection:
    def test_no_cycle_linear_chain(self):
        """A → B → C: no cycles."""
        parent_map = {"http://a": "http://b", "http://b": "http://c"}
        cycles = _detect_cycles(parent_map)
        assert len(cycles) == 0

    def test_detects_simple_cycle(self):
        """A → B → A: one cycle."""
        parent_map = {"http://a": "http://b", "http://b": "http://a"}
        cycles = _detect_cycles(parent_map)
        assert len(cycles) == 1

    def test_detects_three_node_cycle(self):
        """A → B → C → A: one cycle."""
        parent_map = {"http://a": "http://b", "http://b": "http://c", "http://c": "http://a"}
        cycles = _detect_cycles(parent_map)
        assert len(cycles) == 1

    def test_no_cycle_tree(self):
        """Tree structure: no cycles."""
        parent_map = {
            "http://a": "http://root",
            "http://b": "http://root",
            "http://c": "http://a",
        }
        cycles = _detect_cycles(parent_map)
        assert len(cycles) == 0

    def test_self_loop(self):
        """A → A: self-loop is a cycle."""
        parent_map = {"http://a": "http://a"}
        cycles = _detect_cycles(parent_map)
        assert len(cycles) == 1


class TestDepthComputation:
    def test_linear_depth(self):
        """root → a → b → c: depth increases linearly."""
        parent_map = {"http://a": "http://root", "http://b": "http://a", "http://c": "http://b"}
        depths = _compute_depths(parent_map)
        assert depths["http://root"] == 0
        assert depths["http://a"] == 1
        assert depths["http://b"] == 2
        assert depths["http://c"] == 3

    def test_disconnected_gets_zero(self):
        """Node not in parent_map gets depth 0."""
        parent_map = {"http://a": "http://root"}
        depths = _compute_depths(parent_map)
        assert depths.get("http://orphan", 0) == 0


class TestQuarantine:
    def test_removes_cycle_edge(self):
        """A → B → A: the cyclic edge is removed."""
        triples = [
            _broader("http://a", "http://b"),
            _narrower("http://b", "http://a"),
            _broader("http://b", "http://a"),
            _narrower("http://a", "http://b"),
        ]
        clean, warnings = _quarantine_cycles_and_deep_paths(triples)
        assert len(warnings) == 1
        assert warnings[0]["type"] == "cycle_detected"

    def test_preserves_valid_edges(self):
        """Valid tree edges survive quarantine."""
        triples = [
            _broader("http://a", "http://root"),
            _narrower("http://root", "http://a"),
            _broader("http://b", "http://root"),
            _narrower("http://root", "http://b"),
        ]
        clean, warnings = _quarantine_cycles_and_deep_paths(triples)
        assert len(warnings) == 0
        assert len(clean) == 4

    def test_warns_deep_hierarchy(self):
        """Chain deeper than MAX_HIERARCHY_DEPTH generates warnings."""
        triples = []
        for i in range(MAX_HIERARCHY_DEPTH + 2):
            child = f"http://node{i}"
            parent = f"http://node{i+1}"
            triples.append(_broader(child, parent))
            triples.append(_narrower(parent, child))
        clean, warnings = _quarantine_cycles_and_deep_paths(triples)
        deep_warnings = [w for w in warnings if w["type"] == "depth_exceeded"]
        assert len(deep_warnings) > 0
