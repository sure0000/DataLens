"""Tests for hybrid ontology concept matching."""
from unittest.mock import MagicMock, patch

from services.copilot.ontology_concept_match import (
    MIN_KEYWORD_SCORE,
    escape_sparql_literal,
    format_concept_embedding_content,
    hybrid_route_concepts,
    iri_to_embedding_ref_id,
    keyword_score,
    merge_concept_candidates,
    parse_concept_embedding_content,
    route_concepts_sparql,
)


def test_keyword_score_label_in_question():
    assert keyword_score("月度用电量", "2026年5月张晓明的月度用电量是多少？") >= 0.99


def test_keyword_score_token_overlap():
    score = keyword_score("用电量", "2026年5月张晓明的月度用电量是多少？")
    assert score >= MIN_KEYWORD_SCORE


def test_keyword_score_no_match():
    assert keyword_score("库存周转", "2026年5月张晓明的月度用电量是多少？") == 0.0


def test_escape_sparql_literal_quotes():
    assert escape_sparql_literal('say "hi"') == 'say \\"hi\\"'


def test_iri_to_embedding_ref_id_stable():
    iri = "https://datalens.local/data/concept/metric.monthly_kwh"
    assert iri_to_embedding_ref_id(iri) == iri_to_embedding_ref_id(iri)


def test_parse_concept_embedding_content():
    content = format_concept_embedding_content(
        kb_id=3,
        iri="https://datalens.local/data/concept/x",
        concept_type="Metric",
        label="月度用电量",
        body_text="月度用电量；用户当月总用电",
    )
    meta = parse_concept_embedding_content(content)
    assert meta["kb_id"] == "3"
    assert meta["iri"].endswith("/x")
    assert meta["label"] == "月度用电量"
    assert "当月" in meta["body"]


def test_merge_concept_candidates_keeps_best_score():
    a = {"iri": "http://x", "label": "A", "match_score": 0.5, "match_source": "keyword"}
    b = {"iri": "http://x", "label": "A", "match_score": 0.9, "match_source": "embedding"}
    merged = merge_concept_candidates([a], [b], top_k=5)
    assert len(merged) == 1
    assert merged[0]["match_score"] == 0.9
    assert merged[0]["match_source"] == "embedding"


def test_route_concepts_sparql_uses_contains_direction():
    store = MagicMock()
    store.sparql_query.return_value = [
        {
            "concept": "https://datalens.local/data/concept/m1",
            "type": "https://datalens.local/ontology/Metric",
            "label": "月度用电量",
            "definition": "当月总用电",
            "confidence": "90",
            "status": "approved",
        }
    ]
    hits = route_concepts_sparql(store, [1], "2026年5月张晓明的月度用电量是多少？", top_k=5)
    assert len(hits) == 1
    assert hits[0]["label"] == "月度用电量"
    sparql = store.sparql_query.call_args[0][0]
    assert "CONTAINS" in sparql
    assert "月度用电量" not in sparql or "CONTAINS(LCASE" in sparql
    assert "altLabel" in sparql


def test_hybrid_route_concepts_merges_paths():
    store = MagicMock()
    store.sparql_query.return_value = []
    db = MagicMock()
    with patch(
        "services.copilot.ontology_concept_match.search_ontology_concept_embeddings",
        return_value=[
            {
                "iri": "http://m",
                "type": "Metric",
                "label": "月度用电量",
                "definition": "",
                "confidence": 0.8,
                "status": "",
                "match_score": 0.75,
                "match_source": "embedding",
            }
        ],
    ):
        with patch(
            "services.copilot.ontology_concept_match.route_concepts_keyword_memory",
            return_value=[],
        ):
            hits = hybrid_route_concepts(store, db, [1], "2026年5月张晓明的月度用电量是多少？", top_k=5)
    assert len(hits) == 1
    assert hits[0]["match_source"] == "embedding"
