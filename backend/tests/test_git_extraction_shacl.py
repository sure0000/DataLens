"""Regression: git lineage/join triples must pass SHACL when written in one batch."""
from __future__ import annotations

from ontology import NS, kb_graph_iri
from services.extraction.join_extractor import _code_table_triples, _code_table_iri
from services.extraction.lineage_extractor import _VALID_LAYERS
from services.ontology_triple_cleaner import RawTriple, clean_triples, triples_to_ttl
from services.ontology_validation import validate_ttl


RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def test_lineage_extractor_shape_requires_source_or_target_field():
    kb_id = 1
    graph = kb_graph_iri(kb_id)
    lin_iri = f"{graph}/lineage/1"
    triples = [
        RawTriple(lin_iri, RDF_TYPE, f"{NS}LineageAssertion", True, graph=graph),
        RawTriple(lin_iri, f"{NS}transformsFrom", "orders", True, graph=graph),
        RawTriple(lin_iri, f"{NS}layer", "DWD", False, graph=graph),
        RawTriple(lin_iri, f"{NS}sourceField", "orders", False, graph=graph),
    ]
    result = clean_triples(triples, kb_id=kb_id)
    report = validate_ttl(triples_to_ttl(result.production))
    assert report.get("conforms") or report.get("skipped")


def test_join_batch_uses_code_table_stubs_without_domain_link():
    kb_id = 2
    graph = kb_graph_iri(kb_id)
    left_iri = _code_table_iri(kb_id, "orders")
    right_iri = _code_table_iri(kb_id, "customers")
    join_iri = f"{graph}/join/1"
    triples = [
        *_code_table_triples(kb_id, "orders"),
        *_code_table_triples(kb_id, "customers"),
        RawTriple(join_iri, RDF_TYPE, f"{NS}JoinRelation", True, graph=graph, confidence=80),
        RawTriple(join_iri, f"{NS}joinKey", "id", False, graph=graph, confidence=80),
        RawTriple(join_iri, f"{NS}joinType", "inner", False, graph=graph, confidence=80),
        RawTriple(join_iri, f"{NS}confidence", "80", False, graph=graph, confidence=80),
        RawTriple(join_iri, f"{NS}leftTable", left_iri, True, graph=graph, confidence=80),
        RawTriple(join_iri, f"{NS}rightTable", right_iri, True, graph=graph, confidence=80),
    ]
    result = clean_triples(triples, kb_id=kb_id)
    report = validate_ttl(triples_to_ttl(result.production))
    assert report.get("conforms") or report.get("skipped")


def test_valid_layers_constant():
    assert "DWD" in _VALID_LAYERS
