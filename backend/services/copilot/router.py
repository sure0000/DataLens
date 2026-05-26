"""Ontology-driven copilot router — SPARQL-based concept and table routing.

Replaces the 5 legacy routing modules (domain_router, metric_router,
lineage_router, graph_router, ontology_router) with a single unified
router that queries the RDF knowledge graph directly.
"""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri

_logger = logging.getLogger(__name__)


class OntologyRouter:
    """Routes user questions to relevant concepts, tables, and metrics via SPARQL.

    All routing queries hit the RDF production + inferred graphs directly.
    No PostgreSQL semantic tables are involved.
    """

    def __init__(self, store: Any):
        self._store = store

    def route_concepts(
        self, kb_ids: list[int], query_text: str, *, top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Find concepts (terms/metrics) matching the user query.

        Strategy: text match against skos:prefLabel and skos:altLabel across
        all specified KB production graphs.
        """
        ns = NS
        skos = "http://www.w3.org/2004/02/skos/core#"

        # Build UNION across KB graphs
        graph_blocks = []
        for kb_id in kb_ids:
            g = kb_graph_iri(kb_id)
            graph_blocks.append(f"""
            GRAPH <{g}> {{
              ?concept a ?type ;
                       <{skos}prefLabel> ?label .
              OPTIONAL {{ ?concept <{skos}definition> ?definition . }}
              OPTIONAL {{ ?concept <{ns}confidence> ?confidence . }}
              OPTIONAL {{ ?concept <{ns}approvalStatus> ?status . }}
              FILTER(
                REGEX(LCASE(?label), LCASE("{query_text[:100]}"), "i") ||
                REGEX(LCASE(?definition), LCASE("{query_text[:100]}"), "i")
              )
            }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?concept ?type ?label ?definition ?confidence ?status WHERE {{
          {{ {' UNION '.join(graph_blocks)} }}
        }}
        ORDER BY DESC(?confidence)
        LIMIT {top_k}
        """

        try:
            rows = self._store.sparql_query(sparql)
        except Exception as exc:
            _logger.warning("Concept routing failed: %s", exc)
            return []

        return [
            {
                "iri": str(r.get("concept", "")),
                "type": str(r.get("type", "")).replace(ns, ""),
                "label": str(r.get("label", "")),
                "definition": str(r.get("definition", "")),
                "confidence": float(r.get("confidence", 0) or 0),
                "status": str(r.get("status", "")),
            }
            for r in rows
        ]

    def route_tables(
        self, kb_ids: list[int], concept_iris: list[str], *, top_k: int = 15,
    ) -> list[dict[str, Any]]:
        """Find physical tables linked to the matched concepts.

        Follows: dl:mapsToColumn → dl:PhysicalColumn → schema:isPartOf → dl:PhysicalTable
        and: dl:computedFromTable → dl:PhysicalTable
        """
        ns = NS
        skos = "http://www.w3.org/2004/02/skos/core#"

        concept_filters = " || ".join(
            f'(?concept = <{iri}>)' for iri in concept_iris[:20]
        )

        graph_blocks = []
        for kb_id in kb_ids:
            g = kb_graph_iri(kb_id)
            graph_blocks.append(f"""
            GRAPH <{g}> {{
              ?concept (<{ns}computedFromTable>|<{ns}mapsToColumn>) ?table .
              ?table a <{ns}PhysicalTable> .
              OPTIONAL {{ ?table <{skos}prefLabel> ?tableName . }}
              OPTIONAL {{ ?table <{ns}businessSummary> ?summary . }}
              OPTIONAL {{ ?table <{ns}platformId> ?platformId . }}
            }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?table ?tableName ?summary ?platformId WHERE {{
          FILTER({concept_filters})
          {{ {' UNION '.join(graph_blocks)} }}
        }}
        LIMIT {top_k}
        """

        try:
            rows = self._store.sparql_query(sparql)
        except Exception as exc:
            _logger.warning("Table routing failed: %s", exc)
            return []

        return [
            {
                "iri": str(r.get("table", "")),
                "name": str(r.get("tableName", "")),
                "summary": str(r.get("summary", "")),
                "platform_id": str(r.get("platformId", "")),
            }
            for r in rows
        ]

    def expand_lineage(
        self, kb_ids: list[int], table_iris: list[str], *, max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Expand candidate tables via lineage (transformsFrom / joinableWith)."""
        ns = NS

        table_filters = " || ".join(
            f'(?table = <{iri}>)' for iri in table_iris[:10]
        )

        graph_blocks = []
        for kb_id in kb_ids:
            g = kb_graph_iri(kb_id)
            graph_blocks.append(f"""
            GRAPH <{g}> {{
              {{ ?table (<{ns}transformsFrom>|<{ns}joinableWith>) ?neighbor . }}
              UNION
              {{ ?neighbor (<{ns}transformsFrom>|<{ns}joinableWith>) ?table . }}
              ?neighbor a <{ns}PhysicalTable> .
            }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        SELECT DISTINCT ?neighbor WHERE {{
          FILTER({table_filters})
          {{ {' UNION '.join(graph_blocks)} }}
        }}
        LIMIT 30
        """

        try:
            rows = self._store.sparql_query(sparql)
        except Exception as exc:
            _logger.warning("Lineage expansion failed: %s", exc)
            return []

        return [{"iri": str(r.get("neighbor", ""))} for r in rows]

    def full_route(
        self, kb_ids: list[int], question: str, *, top_k: int = 10,
    ) -> dict[str, Any]:
        """Complete routing: concepts → tables → lineage expansion."""
        concepts = self.route_concepts(kb_ids, question, top_k=top_k)
        concept_iris = [c["iri"] for c in concepts if c.get("iri")]

        tables = []
        expanded = []
        if concept_iris:
            tables = self.route_tables(kb_ids, concept_iris, top_k=top_k)
            table_iris = [t["iri"] for t in tables if t.get("iri")]
            if table_iris:
                expanded = self.expand_lineage(kb_ids, table_iris)

        return {
            "concepts": concepts,
            "tables": tables,
            "expanded_tables": expanded,
            "strategy": "ontology_sparql",
        }
