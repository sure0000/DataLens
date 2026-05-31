"""Ontology-driven copilot router — hybrid concept match + SPARQL table routing."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ontology import NS, kb_graph_iri
from services.copilot.ontology_concept_match import hybrid_route_concepts

_logger = logging.getLogger(__name__)


class OntologyRouter:
    """Routes user questions to relevant concepts, tables, and metrics via RDF + pgvector."""

    def __init__(self, store: Any):
        self._store = store

    def route_concepts(
        self,
        kb_ids: list[int],
        query_text: str,
        *,
        top_k: int = 10,
        db: Session | None = None,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Find concepts via substring SPARQL, embedding similarity, and keyword overlap."""
        return hybrid_route_concepts(
            self._store,
            db,
            kb_ids,
            query_text,
            top_k=top_k,
            query_vector=query_vector,
        )

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
            {{ GRAPH <{g}> {{
              ?concept (<{ns}computedFromTable>|<{ns}mapsToColumn>) ?table .
              ?table a <{ns}PhysicalTable> .
              OPTIONAL {{ ?table <{skos}prefLabel> ?tableName . }}
              OPTIONAL {{ ?table <{ns}businessSummary> ?summary . }}
              OPTIONAL {{ ?table <{ns}platformId> ?platformId . }}
            }} }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?table ?tableName ?summary ?platformId WHERE {{
          FILTER({concept_filters})
          {' UNION '.join(graph_blocks)}
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
            {{ GRAPH <{g}> {{
              {{ ?table (<{ns}transformsFrom>|<{ns}joinableWith>) ?neighbor . }}
              UNION
              {{ ?neighbor (<{ns}transformsFrom>|<{ns}joinableWith>) ?table . }}
              ?neighbor a <{ns}PhysicalTable> .
            }} }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        SELECT DISTINCT ?neighbor WHERE {{
          FILTER({table_filters})
          {' UNION '.join(graph_blocks)}
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
        self,
        kb_ids: list[int],
        question: str,
        *,
        top_k: int = 10,
        db: Session | None = None,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        """Complete routing: concepts → tables → lineage expansion."""
        concepts = self.route_concepts(
            kb_ids,
            question,
            top_k=top_k,
            db=db,
            query_vector=query_vector,
        )
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
            "strategy": "ontology_hybrid",
        }
