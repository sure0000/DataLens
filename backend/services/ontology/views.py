"""Read-only SPARQL-backed view API for ontology presentation layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ontology import NS, kb_graph_iri
from services.ingestion.evidence import list_evidence_packages
from services.ontology.modeling_status import get_modeling_status
from services.ontology.relation_predicates import (
    relation_predicate_in_clause,
    relation_predicate_local_names,
)
from services.ontology.reader import OntologyReader
from services.ontology_rdf_browser import fetch_kb_rdf_view
from services.ontology_store import sparql_query
from services.triple_store import get_triple_store


def _reader() -> OntologyReader:
    return OntologyReader(get_triple_store())


def view_overview(db: Session, kb_id: int) -> dict[str, Any]:
    modeling = get_modeling_status(db, kb_id)
    packages = list_evidence_packages(db, kb_id)
    rdf: dict[str, Any] = {}
    try:
        rdf = fetch_kb_rdf_view(kb_id)
    except Exception:
        rdf = {}
    prod = rdf.get("production", {})

    return {
        "ok": True,
        "kb_id": kb_id,
        "modeling": modeling,
        "evidence_package_count": len(packages),
        "production": {
            "term_count": prod.get("term_count", 0),
            "metric_count": prod.get("metric_count", 0),
            "physical_table_count": prod.get("physical_table_count", 0),
            "triple_count": prod.get("triple_count", 0),
        },
        "quarantine": rdf.get("quarantine", {}),
    }


def view_terms(
    kb_id: int,
    *,
    status: str | None = None,
    limit: int = 200,
    include_inferred: bool = False,
) -> dict[str, Any]:
    items = _reader().list_terms(kb_id, limit=limit, include_inferred=include_inferred)
    if status:
        items = [t for t in items if (t.get("status") or "draft") == status]
    return {"ok": True, "kb_id": kb_id, "total": len(items), "terms": items}


def view_graph(kb_id: int, *, center: str | None = None) -> dict[str, Any]:
    graph_iri = kb_graph_iri(kb_id)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    try:
        rdf = fetch_kb_rdf_view(kb_id)
        for t in rdf.get("production", {}).get("terms", []):
            nodes.append(
                {
                    "id": t["iri"],
                    "type": "BusinessTerm",
                    "label": t.get("label", ""),
                    "status": t.get("status"),
                }
            )
        for m in rdf.get("production", {}).get("metrics", []):
            nodes.append(
                {
                    "id": m["iri"],
                    "type": "Metric",
                    "label": m.get("label", ""),
                    "status": m.get("status"),
                }
            )
        for tbl in rdf.get("production", {}).get("physical_tables", []):
            nodes.append(
                {
                    "id": tbl["iri"],
                    "type": "PhysicalTable",
                    "label": (tbl.get("summary") or "")[:60] or f"表 #{tbl.get('platform_id')}",
                    "platform_id": tbl.get("platform_id"),
                }
            )
    except Exception:
        pass

    ns = str(NS)
    rel_filter = relation_predicate_in_clause()
    relation_limit = 500
    try:
        rows = sparql_query(
            f"""
            PREFIX dl: <{ns}>
            SELECT ?s ?p ?o WHERE {{
              GRAPH <{graph_iri}> {{
                ?s ?p ?o .
                FILTER(isIRI(?o))
                FILTER(?p IN ({rel_filter}))
              }}
            }}
            LIMIT {relation_limit}
            """
        )
        for i, row in enumerate(rows):
            s = str(row.get("s", ""))
            p = str(row.get("p", ""))
            o = str(row.get("o", ""))
            if not s or not o:
                continue
            edges.append(
                {
                    "id": f"e{i}",
                    "source": s,
                    "target": o,
                    "type": p.split("#")[-1] if "#" in p else p.split("/")[-1],
                    "predicate": p,
                }
            )
    except Exception:
        pass

    neighborhood = None
    if center:
        neighborhood = _reader().get_concept_neighborhood(center, kb_id)

    return {
        "ok": True,
        "kb_id": kb_id,
        "graph_iri": graph_iri,
        "nodes": nodes,
        "edges": edges,
        "edge_filter": {
            "source": "rdf_production_graph",
            "object_filter": "isIRI",
            "predicates": relation_predicate_local_names(),
            "limit": relation_limit,
        },
        "center": center,
        "neighborhood": neighborhood,
    }


def view_lineage(kb_id: int, *, table: str | None = None) -> dict[str, Any]:
    """Lineage edges (transformsFrom) optionally filtered by table IRI or platform id."""
    graph_iri = kb_graph_iri(kb_id)
    ns = str(NS)
    filter_clause = ""
    if table:
        if table.startswith("http"):
            filter_clause = f"FILTER(?s = <{table}> || ?o = <{table}>)"
        else:
            filter_clause = f'FILTER(CONTAINS(STR(?s), "{table}") || CONTAINS(STR(?o), "{table}"))'

    rows: list[dict] = []
    try:
        rows = sparql_query(
            f"""
            PREFIX dl: <{ns}>
            SELECT ?s ?o ?logic WHERE {{
              GRAPH <{graph_iri}> {{
                ?s dl:transformsFrom ?o .
                OPTIONAL {{ ?s dl:transformLogic ?logic }}
                {filter_clause}
              }}
            }}
            LIMIT 200
            """
        )
    except Exception:
        rows = []

    edges = [
        {
            "source": str(r.get("o", "")),
            "target": str(r.get("s", "")),
            "transform_logic": str(r.get("logic", "")),
        }
        for r in rows
        if r.get("s") and r.get("o")
    ]

    return {"ok": True, "kb_id": kb_id, "table": table, "edges": edges, "total": len(edges)}


def view_triples(kb_id: int, *, limit: int = 300) -> dict[str, Any]:
    graph_iri = kb_graph_iri(kb_id)
    rows: list[dict] = []
    try:
        rows = sparql_query(
            f"""
            SELECT ?s ?p ?o WHERE {{
              GRAPH <{graph_iri}> {{
                ?s ?p ?o .
              }}
            }}
            LIMIT {int(limit)}
            """
        )
    except Exception:
        rows = []

    triples = [
        {
            "subject": str(r.get("s", "")),
            "predicate": str(r.get("p", "")),
            "object": str(r.get("o", "")),
        }
        for r in rows
        if r.get("s") and r.get("p")
    ]
    return {"ok": True, "kb_id": kb_id, "graph_iri": graph_iri, "triples": triples, "total": len(triples)}
