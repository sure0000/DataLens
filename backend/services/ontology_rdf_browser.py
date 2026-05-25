"""Read ontology ABox from RDF store for UI (direct graph walk; avoids SPARQL parser races)."""
from __future__ import annotations

from typing import Any

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, SKOS

from ontology import NS, kb_graph_iri, quarantine_graph_iri
from services.ontology_store import get_named_graph, sparql_query, use_fuseki_backend
from services.sparql_queries import (
    count_quarantine,
    count_triples_in_graph,
    list_rdf_metrics,
    list_rdf_physical_tables,
    list_rdf_terms,
)

DL = NS
DL_BUSINESS_TERM = URIRef(f"{DL}BusinessTerm")
DL_METRIC = URIRef(f"{DL}Metric")
DL_PHYSICAL_TABLE = URIRef(f"{DL}PhysicalTable")
DL_QUARANTINED = URIRef(f"{DL}QuarantinedAssertion")
DL_APPROVAL = URIRef(f"{DL}approvalStatus")
DL_FORMULA = URIRef(f"{DL}formula")
DL_PLATFORM_ID = URIRef(f"{DL}platformId")
DL_BUSINESS_SUMMARY = URIRef(f"{DL}businessSummary")

_MAX_LIST = 500


def _lit_value(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, Literal):
        return str(obj)
    return str(obj)


def _scalar(rows: list[dict], key: str = "c") -> int:
    if not rows:
        return 0
    val = rows[0].get(key)
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _row_val(row: dict, key: str) -> str:
    v = row.get(key)
    if v is None:
        return ""
    return str(v)


def _fetch_via_sparql(prod_graph: str, q_graph: str) -> dict[str, Any]:
    """Fuseki backend: SPARQL over HTTP (thread-safe)."""
    prod_triples = _scalar(sparql_query(count_triples_in_graph(prod_graph)))
    q_count = _scalar(sparql_query(count_quarantine(q_graph)))
    term_rows = sparql_query(list_rdf_terms(prod_graph, limit=_MAX_LIST))
    metric_rows = sparql_query(list_rdf_metrics(prod_graph, limit=_MAX_LIST))
    table_rows = sparql_query(list_rdf_physical_tables(prod_graph, limit=200))
    terms = [
        {
            "iri": _row_val(r, "term"),
            "label": _row_val(r, "label"),
            "definition": _row_val(r, "definition"),
            "status": _row_val(r, "status") or "draft",
        }
        for r in term_rows
    ]
    metrics = [
        {
            "iri": _row_val(r, "metric"),
            "label": _row_val(r, "label"),
            "formula": _row_val(r, "formula"),
            "status": _row_val(r, "status") or "draft",
        }
        for r in metric_rows
    ]
    tables = [
        {
            "iri": _row_val(r, "table"),
            "platform_id": _row_val(r, "platformId"),
            "summary": _row_val(r, "summary"),
        }
        for r in table_rows
    ]
    return {
        "triple_count": prod_triples,
        "terms": terms,
        "metrics": metrics,
        "physical_tables": tables,
        "quarantine_count": q_count,
    }


def _fetch_via_graph_walk(prod_graph: str, q_graph: str) -> dict[str, Any]:
    """Local Trig: iterate named graphs (no rdflib SPARQL parser)."""
    prod_g = get_named_graph(prod_graph)
    q_g = get_named_graph(q_graph)

    terms: list[dict[str, str]] = []
    for subj in prod_g.subjects(RDF.type, DL_BUSINESS_TERM):
        terms.append(
            {
                "iri": str(subj),
                "label": _lit_value(prod_g.value(subj, SKOS.prefLabel)),
                "definition": _lit_value(prod_g.value(subj, SKOS.definition)),
                "status": _lit_value(prod_g.value(subj, DL_APPROVAL)) or "draft",
            }
        )
    terms.sort(key=lambda x: x["label"])
    terms = terms[:_MAX_LIST]

    metrics: list[dict[str, str]] = []
    for subj in prod_g.subjects(RDF.type, DL_METRIC):
        metrics.append(
            {
                "iri": str(subj),
                "label": _lit_value(prod_g.value(subj, SKOS.prefLabel)),
                "formula": _lit_value(prod_g.value(subj, DL_FORMULA)),
                "status": _lit_value(prod_g.value(subj, DL_APPROVAL)) or "draft",
            }
        )
    metrics.sort(key=lambda x: x["label"])
    metrics = metrics[:_MAX_LIST]

    tables: list[dict[str, str]] = []
    for subj in prod_g.subjects(RDF.type, DL_PHYSICAL_TABLE):
        tables.append(
            {
                "iri": str(subj),
                "platform_id": _lit_value(prod_g.value(subj, DL_PLATFORM_ID)),
                "summary": _lit_value(prod_g.value(subj, DL_BUSINESS_SUMMARY)),
            }
        )
    tables.sort(key=lambda x: x["platform_id"])

    q_count = sum(1 for _ in q_g.subjects(RDF.type, DL_QUARANTINED))

    return {
        "triple_count": len(prod_g),
        "terms": terms,
        "metrics": metrics,
        "physical_tables": tables,
        "quarantine_count": q_count,
    }


def fetch_kb_rdf_view(kb_id: int) -> dict[str, Any]:
    """Summarize production + quarantine graphs for one knowledge base."""
    prod_graph = kb_graph_iri(kb_id)
    q_graph = quarantine_graph_iri(kb_id)

    if use_fuseki_backend():
        raw = _fetch_via_sparql(prod_graph, q_graph)
    else:
        raw = _fetch_via_graph_walk(prod_graph, q_graph)

    terms = raw["terms"]
    metrics = raw["metrics"]
    tables = raw["physical_tables"]

    return {
        "graph_iri": prod_graph,
        "quarantine_graph_iri": q_graph,
        "production": {
            "triple_count": raw["triple_count"],
            "term_count": len(terms),
            "metric_count": len(metrics),
            "physical_table_count": len(tables),
            "terms": terms,
            "metrics": metrics,
            "physical_tables": tables,
        },
        "quarantine": {
            "triple_count": raw["quarantine_count"],
            "assertion_count": raw["quarantine_count"],
        },
    }
