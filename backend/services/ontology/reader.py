"""Ontology reader — SPARQL query with transparent inference graph support.

Queries can optionally include inferred triples by UNION-ing the
production and inferred graphs.
"""

from __future__ import annotations

import logging
from typing import Any

from ontology import INFERRED_GRAPH_PREFIX, kb_graph_iri, quarantine_graph_iri

_logger = logging.getLogger(__name__)


class OntologyReader:
    """Reads ontology data with optional inference graph inclusion.

    Usage:
        reader = OntologyReader(store)
        terms = reader.list_terms(kb_id=1)
        metrics = reader.list_metrics(kb_id=1, include_inferred=True)
    """

    _ALT_LABEL_SEP = "|||"

    def __init__(self, store: Any):
        self._store = store

    def _fetch_alt_labels(self, kb_id: int, class_name: str) -> dict[str, list[str]]:
        """Fetch skos:altLabel values grouped by subject IRI for a class."""
        graph = kb_graph_iri(kb_id)
        ns = "https://datalens.local/ontology/"
        skos = "http://www.w3.org/2004/02/skos/core#"
        query = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT ?s (GROUP_CONCAT(?s_raw; separator='{self._ALT_LABEL_SEP}') AS ?synonyms) WHERE {{
          GRAPH <{graph}> {{
            ?s a dl:{class_name} .
            OPTIONAL {{ ?s skos:altLabel ?s_raw . }}
          }}
        }} GROUP BY ?s
        """
        try:
            rows = self._store.sparql_query(query)
        except Exception as exc:
            _logger.warning("OntologyReader altLabel query failed for class=%s kb=%s: %s", class_name, kb_id, exc)
            return {}
        result: dict[str, list[str]] = {}
        for row in rows:
            iri = str(row.get("s", ""))
            syns = str(row.get("synonyms", ""))
            result[iri] = [s.strip() for s in syns.split(self._ALT_LABEL_SEP) if s.strip()]
        return result

    # ── Concept queries ──────────────────────────────────────

    def list_terms(
        self, kb_id: int, *, limit: int = 500, include_inferred: bool = False,
    ) -> list[dict[str, str]]:
        terms = self._query_concepts(
            kb_id, "BusinessTerm",
            ["label", "definition", "status", "confidence"],
            limit, include_inferred,
        )
        syn_map = self._fetch_alt_labels(kb_id, "BusinessTerm")
        for term in terms:
            term["synonyms"] = syn_map.get(term["iri"], [])
        return terms

    def list_metrics(
        self, kb_id: int, *, limit: int = 500, include_inferred: bool = False,
    ) -> list[dict[str, str]]:
        return self._query_concepts(
            kb_id, "Metric",
            ["label", "formula", "caliber", "status", "confidence"],
            limit, include_inferred,
        )

    def list_dimensions(
        self, kb_id: int, *, limit: int = 500, include_inferred: bool = False,
    ) -> list[dict[str, str]]:
        return self._query_concepts(
            kb_id, "Dimension",
            ["label", "dimensionType", "confidence"],
            limit, include_inferred,
        )

    def list_business_rules(
        self, kb_id: int, *, limit: int = 500, include_inferred: bool = False,
    ) -> list[dict[str, str]]:
        return self._query_concepts(
            kb_id, "BusinessRule",
            ["label", "ruleExpression", "ruleType", "status", "confidence"],
            limit, include_inferred,
        )

    def list_business_concepts(
        self, kb_id: int, *, limit: int = 500, include_inferred: bool = False,
    ) -> list[dict[str, str]]:
        return self._query_concepts(
            kb_id, "BusinessConcept",
            ["label", "definition", "status", "confidence"],
            limit, include_inferred,
        )

    def list_physical_tables(
        self, kb_id: int, *, limit: int = 200,
    ) -> list[dict[str, str]]:
        return self._query_concepts(
            kb_id, "PhysicalTable",
            ["platformId", "businessSummary", "sensitivityLevel"],
            limit, include_inferred=False,
        )

    def _query_concepts(
        self, kb_id: int, class_name: str, props: list[str],
        limit: int, include_inferred: bool,
    ) -> list[dict[str, str]]:
        graph = kb_graph_iri(kb_id)
        ns = "https://datalens.local/ontology/"
        skos = "http://www.w3.org/2004/02/skos/core#"

        select_parts = ["?s"]
        optional_parts = []
        for p in props:
            var = f"?{p}"
            select_parts.append(var)
            if p == "label":
                optional_parts.append(f"OPTIONAL {{ ?s <{skos}prefLabel> {var} . }}")
            elif p == "definition":
                optional_parts.append(f"OPTIONAL {{ ?s <{skos}definition> {var} . }}")
            else:
                optional_parts.append(f"OPTIONAL {{ ?s <{ns}{p}> {var} . }}")

        def _make_query(source_graph: str) -> str:
            return f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            SELECT {' '.join(select_parts)} WHERE {{
              GRAPH <{source_graph}> {{
                ?s a dl:{class_name} .
                {' '.join(optional_parts)}
              }}
            }}
            ORDER BY ?label
            LIMIT {limit}
            """

        query = _make_query(graph)
        if include_inferred:
            inf_graph = f"{INFERRED_GRAPH_PREFIX}{kb_id}"
            query = f"{{\n{_make_query(graph)}\n}} UNION {{\n{_make_query(inf_graph)}\n}}"

        try:
            rows = self._store.sparql_query(query)
        except Exception as exc:
            _logger.warning("OntologyReader query failed for class=%s kb=%s: %s", class_name, kb_id, exc)
            return []

        out: list[dict[str, str]] = []
        for row in rows:
            item: dict[str, str] = {"iri": str(row.get("s", ""))}
            for p in props:
                item[p] = str(row.get(p, ""))
            out.append(item)
        return out

    # ── Graph traversal ──────────────────────────────────────

    def get_concept_neighborhood(
        self, concept_iri: str, kb_id: int, *, radius: int = 1,
    ) -> dict[str, Any]:
        """Return the 1-hop neighborhood of a concept for graph visualization."""
        graph = kb_graph_iri(kb_id)
        query = f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX dl: <https://datalens.local/ontology/>
        SELECT ?p ?o ?label WHERE {{
          GRAPH <{graph}> {{
            {{ <{concept_iri}> ?p ?o . }}
            UNION
            {{ ?s ?p <{concept_iri}> . BIND(?s AS ?o) }}
          }}
          OPTIONAL {{ ?o <http://www.w3.org/2004/02/skos/core#prefLabel> ?label . }}
        }}
        LIMIT 200
        """
        try:
            rows = self._store.sparql_query(query)
        except Exception as exc:
            _logger.warning("Neighborhood query failed: %s", exc)
            rows = []

        nodes = {concept_iri}
        edges: list[dict] = []
        for row in rows:
            o_val = str(row.get("o", ""))
            if o_val:
                nodes.add(o_val)
            edges.append({
                "predicate": str(row.get("p", "")),
                "object": o_val,
                "label": str(row.get("label", "")),
            })

        return {"nodes": list(nodes), "edges": edges, "center": concept_iri}

    # ── Stats ────────────────────────────────────────────────

    def kb_stats(self, kb_id: int) -> dict[str, Any]:
        """Return production + quarantine stats for a knowledge base."""
        prod_graph = kb_graph_iri(kb_id)
        q_graph = quarantine_graph_iri(kb_id)

        prod_terms = self.list_terms(kb_id, limit=1)
        prod_metrics = self.list_metrics(kb_id, limit=1)
        prod_tables = self.list_physical_tables(kb_id, limit=1)

        # Count triples via SPARQL
        try:
            rows = self._store.sparql_query(
                f"SELECT (COUNT(*) AS ?c) WHERE {{ GRAPH <{prod_graph}> {{ ?s ?p ?o }} }}"
            )
            prod_count = int(rows[0]["c"]) if rows else 0
        except Exception:
            prod_count = -1

        try:
            rows = self._store.sparql_query(
                f"SELECT (COUNT(*) AS ?c) WHERE {{ GRAPH <{q_graph}> {{ ?s ?p ?o }} }}"
            )
            q_count = int(rows[0]["c"]) if rows else 0
        except Exception:
            q_count = -1

        return {
            "kb_id": kb_id,
            "production_graph": prod_graph,
            "quarantine_graph": q_graph,
            "production_triples": prod_count,
            "quarantine_triples": q_count,
        }
