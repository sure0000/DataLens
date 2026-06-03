"""Ontology-driven copilot router — hybrid concept match + SPARQL table routing."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ontology import NS, kb_graph_iri
from services.copilot.ontology_concept_match import hybrid_route_concepts
from services.ontology.relation_predicates import SKOS_NS

_logger = logging.getLogger(__name__)

# Concept-to-concept predicates that describe semantic relationships
_CONCEPT_RELATION_PREDICATES: tuple[str, ...] = (
    f"{NS}dependsOn",
    f"{NS}derivedFrom",
    f"{NS}relatedTo",
    f"{SKOS_NS}related",
    f"{SKOS_NS}broader",
    f"{SKOS_NS}narrower",
)

# Chinese labels for concept relationship predicates
_PREDICATE_LABEL_ZH: dict[str, str] = {
    "dependsOn": "依赖",
    "derivedFrom": "派生自",
    "relatedTo": "关联",
    "related": "相关",
    "broader": "上层概念",
    "narrower": "下层概念",
}


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
        SELECT DISTINCT ?concept ?table ?tableName ?summary ?platformId WHERE {{
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
                "source_concept_iri": str(r.get("concept", "")),
            }
            for r in rows
        ]

    def expand_lineage(
        self, kb_ids: list[int], table_iris: list[str], *, max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Expand candidate tables via lineage (transformsFrom / joinableWith)."""
        ns = NS
        skos = "http://www.w3.org/2004/02/skos/core#"

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
              OPTIONAL {{ ?neighbor <{skos}prefLabel> ?neighborName . }}
            }} }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?neighbor ?neighborName WHERE {{
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

        return [
            {
                "iri": str(r.get("neighbor", "")),
                "name": str(r.get("neighborName", "")),
            }
            for r in rows
        ]

    def expand_concept_relations(
        self, kb_ids: list[int], concept_iris: list[str],
    ) -> list[dict[str, Any]]:
        """Find semantic relationships between matched concepts.

        Queries concept-to-concept predicates (dependsOn, relatedTo,
        derivedFrom, skos:related, skos:broader, skos:narrower) in both
        directions so we surface how matched concepts relate to each other
        and to neighbouring concepts in the ontology graph.
        """
        ns = NS
        skos = "http://www.w3.org/2004/02/skos/core#"

        if not concept_iris:
            return []

        # Build FILTER that matches when either subject or object is a matched concept
        iri_conditions = " || ".join(
            f'(?subject = <{iri}> || ?object = <{iri}>)'
            for iri in concept_iris[:20]
        )

        pred_in_clause = ", ".join(
            f"<{p}>" for p in _CONCEPT_RELATION_PREDICATES
        )

        graph_blocks = []
        for kb_id in kb_ids:
            g = kb_graph_iri(kb_id)
            graph_blocks.append(f"""
            {{ GRAPH <{g}> {{
              ?subject ?predicate ?object .
              OPTIONAL {{ ?subject <{skos}prefLabel> ?subjectLabel . }}
              OPTIONAL {{ ?object <{skos}prefLabel> ?objectLabel . }}
            }} }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?subject ?subjectLabel ?predicate ?object ?objectLabel WHERE {{
          FILTER({iri_conditions})
          FILTER(?predicate IN ({pred_in_clause}))
          {' UNION '.join(graph_blocks)}
        }}
        LIMIT 50
        """

        try:
            rows = self._store.sparql_query(sparql)
        except Exception as exc:
            _logger.warning("Concept relation expansion failed: %s", exc)
            return []

        def _local_name(iri: str) -> str:
            """Extract the local name from a predicate IRI."""
            return iri.rsplit("#", 1)[-1] if "#" in iri else iri.rsplit("/", 1)[-1]

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for r in rows:
            subj_iri = str(r.get("subject", ""))
            pred_iri = str(r.get("predicate", ""))
            obj_iri = str(r.get("object", ""))
            dedup_key = (subj_iri, pred_iri, obj_iri)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            pred_local = _local_name(pred_iri)
            results.append({
                "subject_iri": subj_iri,
                "subject_label": str(r.get("subjectLabel", "")) or _local_name(subj_iri),
                "predicate": pred_iri,
                "predicate_label": pred_local,
                "object_iri": obj_iri,
                "object_label": str(r.get("objectLabel", "")) or _local_name(obj_iri),
            })

        return results

    def full_route(
        self,
        kb_ids: list[int],
        question: str,
        *,
        top_k: int = 10,
        db: Session | None = None,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        """Complete routing: concepts → relations → tables → lineage expansion."""
        concepts = self.route_concepts(
            kb_ids,
            question,
            top_k=top_k,
            db=db,
            query_vector=query_vector,
        )
        concept_iris = [c["iri"] for c in concepts if c.get("iri")]

        concept_relations = []
        if concept_iris:
            concept_relations = self.expand_concept_relations(kb_ids, concept_iris)

        tables = []
        expanded = []
        if concept_iris:
            tables = self.route_tables(kb_ids, concept_iris, top_k=top_k)
            table_iris = [t["iri"] for t in tables if t.get("iri")]
            if table_iris:
                expanded = self.expand_lineage(kb_ids, table_iris)

        return {
            "concepts": concepts,
            "concept_relations": concept_relations,
            "tables": tables,
            "expanded_tables": expanded,
            "strategy": "ontology_hybrid",
        }
