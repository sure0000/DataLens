"""OntologyWriter — unified write path for all semantic data.

All semantic writes go through:
  1. Convert input → RawTriple list
  2. run clean_triples() pipeline (syntax, link, TBox, dedup, status gate)
  3. SHACL validation
  4. Pass → insert into production named graph
  5. Fail → store in quarantine named graph
  6. Trigger incremental reasoning (eventually)
  7. Async flush PG cache (eventually)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ontology import NS, kb_graph_iri, term_iri, metric_iri, dimension_iri, rule_iri, concept_slug, chunk_iri, domain_iri
from services.ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result

_logger = logging.getLogger(__name__)

# TTL string helpers
_TTL_ESCAPE = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r"})


def _ttl_string(value: str) -> str:
    return f'"""{value.translate(_TTL_ESCAPE)}"""'


def _ttl_uri(iri: str) -> str:
    return f"<{iri}>"


# ─────────────────────────────────────────────────────────
# Input types
# ─────────────────────────────────────────────────────────


@dataclass
class TermInput:
    domain_id: int
    name: str
    definition: str
    term_type: str = "other"  # metric|enum|time|dimension|other
    related_fields: list[str] = field(default_factory=list)
    confidence: float = 70.0
    status: str = "draft"
    chunk_id: int | None = None


@dataclass
class MetricInput:
    domain_id: int
    name: str
    formula: str
    caliber: str = ""
    bound_table_ids: list[int] = field(default_factory=list)
    derived_from_metric_id: int | None = None
    confidence: float = 70.0
    status: str = "draft"
    chunk_id: int | None = None


@dataclass
class DimensionInput:
    domain_id: int
    name: str
    dim_type: str = "category"  # time|geo|category|hierarchy
    related_fields: list[str] = field(default_factory=list)
    confidence: float = 70.0
    chunk_id: int | None = None


@dataclass
class RelationInput:
    kb_id: int
    subject_iri: str
    predicate: str  # full URI
    object_iri: str
    is_uri: bool = True
    confidence: float = 70.0


@dataclass
class LineageInput:
    kb_id: int
    source_table_id: int
    target_table_id: int
    source_field: str = ""
    target_field: str = ""
    layer: str = "DWD"  # ODS|DWD|DWS|ADS|DM
    transform_logic: str = ""
    confidence: float = 70.0
    chunk_id: int | None = None


@dataclass
class PhysicalTableInput:
    table_id: int
    datasource_id: int
    table_name: str
    business_summary: str = ""
    row_count: int = 0
    sensitivity: str = "internal"


# ─────────────────────────────────────────────────────────
# Writer
# ─────────────────────────────────────────────────────────


class OntologyWriter:
    """Unified write interface for ontology ABox population.

    All writes pass through: clean_triples() → SHACL validation → production graph.
    """

    def __init__(self, store: Any, validator: Any, quarantine_manager: Any):
        self._store = store
        self._validator = validator
        self._quarantine = quarantine_manager

    # ── Term ──────────────────────────────────────────

    def write_term(self, kb_id: int, term: TermInput) -> dict[str, Any]:
        """Write a dl:BusinessTerm to the KB's production graph."""
        term_slug = concept_slug(term.name, "term")
        iri = term_iri(term.domain_id, term_slug)
        graph = kb_graph_iri(kb_id)

        triples: list[RawTriple] = [
            RawTriple(iri, str("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), f"{NS}BusinessTerm", True, graph=graph),
            RawTriple(iri, str("http://www.w3.org/2004/02/skos/core#prefLabel"), term.name, False, "zh", graph, term.confidence),
            RawTriple(iri, str("http://www.w3.org/2004/02/skos/core#definition"), term.definition, False, "zh", graph, term.confidence),
            RawTriple(iri, f"{NS}approvalStatus", term.status, False, lang=None, graph=graph, confidence=term.confidence),
            RawTriple(iri, f"{NS}confidence", str(term.confidence), False, graph=graph, confidence=term.confidence),
            RawTriple(iri, f"{NS}belongsToDomain", domain_iri(term.domain_id), True, graph=graph, confidence=term.confidence),
        ]

        for col in term.related_fields:
            triples.append(RawTriple(iri, f"{NS}mapsToColumn", col, True, graph=graph, confidence=term.confidence))

        if term.chunk_id:
            triples.append(RawTriple(iri, f"{NS}groundedBy", chunk_iri(term.chunk_id), True, graph=graph, confidence=term.confidence))

        result = clean_triples(triples, kb_id=kb_id)
        return persist_clean_result(result, kb_id)

    # ── Metric ────────────────────────────────────────

    def write_metric(self, kb_id: int, metric: MetricInput) -> dict[str, Any]:
        """Write a dl:Metric to the KB's production graph."""
        metric_slug = concept_slug(metric.name, "metric")
        iri = metric_iri(metric.domain_id, metric_slug)
        graph = kb_graph_iri(kb_id)

        triples: list[RawTriple] = [
            RawTriple(iri, str("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), f"{NS}Metric", True, graph=graph),
            RawTriple(iri, str("http://www.w3.org/2004/02/skos/core#prefLabel"), metric.name, False, "zh", graph, metric.confidence),
            RawTriple(iri, f"{NS}formula", metric.formula, False, graph=graph, confidence=metric.confidence),
            RawTriple(iri, f"{NS}approvalStatus", metric.status, False, graph=graph, confidence=metric.confidence),
            RawTriple(iri, f"{NS}confidence", str(metric.confidence), False, graph=graph, confidence=metric.confidence),
            RawTriple(iri, f"{NS}belongsToDomain", domain_iri(metric.domain_id), True, graph=graph, confidence=metric.confidence),
        ]

        if metric.caliber:
            triples.append(RawTriple(iri, f"{NS}caliber", metric.caliber, False, graph=graph, confidence=metric.confidence))

        from ontology import table_iri

        for table_id in metric.bound_table_ids:
            triples.append(RawTriple(iri, f"{NS}computedFromTable", table_iri(table_id), True, graph=graph, confidence=metric.confidence))

        if metric.derived_from_metric_id is not None:
            derived_iri = metric_iri(metric.domain_id, concept_slug(str(metric.derived_from_metric_id), "metric"))
            triples.append(RawTriple(iri, f"{NS}derivedFrom", derived_iri, True, graph=graph, confidence=metric.confidence))

        if metric.chunk_id:
            triples.append(RawTriple(iri, f"{NS}groundedBy", chunk_iri(metric.chunk_id), True, graph=graph, confidence=metric.confidence))

        result = clean_triples(triples, kb_id=kb_id)
        return persist_clean_result(result, kb_id)

    # ── Dimension ─────────────────────────────────────

    def write_dimension(self, kb_id: int, dim: DimensionInput) -> dict[str, Any]:
        """Write a dl:Dimension to the KB's production graph."""
        dim_slug = concept_slug(dim.name, "dim")
        iri = dimension_iri(dim.domain_id, dim_slug)
        graph = kb_graph_iri(kb_id)

        triples: list[RawTriple] = [
            RawTriple(iri, str("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), f"{NS}Dimension", True, graph=graph),
            RawTriple(iri, str("http://www.w3.org/2004/02/skos/core#prefLabel"), dim.name, False, "zh", graph, dim.confidence),
            RawTriple(iri, f"{NS}dimensionType", dim.dim_type, False, graph=graph, confidence=dim.confidence),
            RawTriple(iri, f"{NS}confidence", str(dim.confidence), False, graph=graph, confidence=dim.confidence),
        ]

        if dim.chunk_id:
            triples.append(RawTriple(iri, f"{NS}groundedBy", chunk_iri(dim.chunk_id), True, graph=graph, confidence=dim.confidence))

        result = clean_triples(triples, kb_id=kb_id)
        return persist_clean_result(result, kb_id)

    # ── Relation ──────────────────────────────────────

    def write_relation(self, relation: RelationInput) -> dict[str, Any]:
        """Write a single semantic relation triple."""
        graph = kb_graph_iri(relation.kb_id)
        triple = RawTriple(
            relation.subject_iri,
            relation.predicate,
            relation.object_iri,
            relation.is_uri,
            graph=graph,
            confidence=relation.confidence,
        )
        result = clean_triples([triple], kb_id=relation.kb_id)
        return persist_clean_result(result, relation.kb_id)

    # ── Lineage ───────────────────────────────────────

    def write_lineage(self, lineage: LineageInput) -> dict[str, Any]:
        """Write a dl:LineageAssertion to the KB's production graph."""
        from ontology import table_iri

        graph = kb_graph_iri(lineage.kb_id)
        source_iri = table_iri(lineage.source_table_id)
        target_iri = table_iri(lineage.target_table_id)

        # LineageAssertion subject
        lin_iri = f"{graph}/lineage/{lineage.source_table_id}_{lineage.target_table_id}"

        triples: list[RawTriple] = [
            RawTriple(lin_iri, str("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), f"{NS}LineageAssertion", True, graph=graph),
            RawTriple(lin_iri, f"{NS}transformsFrom", source_iri, True, graph=graph, confidence=lineage.confidence),
            RawTriple(lin_iri, f"{NS}layer", lineage.layer, False, graph=graph, confidence=lineage.confidence),
            RawTriple(lin_iri, f"{NS}confidence", str(lineage.confidence), False, graph=graph, confidence=lineage.confidence),
        ]

        if lineage.source_field:
            triples.append(RawTriple(lin_iri, f"{NS}sourceField", lineage.source_field, False, graph=graph, confidence=lineage.confidence))
        if lineage.target_field:
            triples.append(RawTriple(lin_iri, f"{NS}targetField", lineage.target_field, False, graph=graph, confidence=lineage.confidence))
        if lineage.transform_logic:
            triples.append(RawTriple(lin_iri, f"{NS}transformLogic", lineage.transform_logic, False, graph=graph, confidence=lineage.confidence))

        result = clean_triples(triples, kb_id=lineage.kb_id)
        return persist_clean_result(result, lineage.kb_id)

    # ── Physical Table ────────────────────────────────

    def write_physical_table(self, kb_id: int, pt: PhysicalTableInput) -> dict[str, Any]:
        """Write/update a dl:PhysicalTable in the KB's production graph."""
        from ontology import table_iri, datasource_iri

        iri = table_iri(pt.table_id)
        graph = kb_graph_iri(kb_id)
        ds_iri = datasource_iri(pt.datasource_id)

        triples: list[RawTriple] = [
            RawTriple(iri, str("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), f"{NS}PhysicalTable", True, graph=graph),
            RawTriple(iri, f"{NS}platformId", str(pt.table_id), False, graph=graph),
            RawTriple(iri, f"{NS}belongsToDataSource", ds_iri, True, graph=graph),
            RawTriple(iri, f"{NS}sensitivityLevel", pt.sensitivity, False, graph=graph),
        ]

        if pt.table_name:
            triples.append(RawTriple(iri, str("http://www.w3.org/2004/02/skos/core#prefLabel"), pt.table_name, False, "zh", graph))
        if pt.business_summary:
            triples.append(RawTriple(iri, f"{NS}businessSummary", pt.business_summary, False, graph=graph))
        if pt.row_count > 0:
            triples.append(RawTriple(iri, f"{NS}rowCount", str(pt.row_count), False, graph=graph))

        result = clean_triples(triples, kb_id=kb_id)
        return persist_clean_result(result, kb_id)

    # ── Bulk ──────────────────────────────────────────

    def write_many(self, kb_id: int, triples: list[Any]) -> dict[str, Any]:
        """Write a batch of RawTriples through the full cleaning pipeline.

        Args:
            kb_id: Knowledge base ID.
            triples: List of RawTriple objects or dicts with RawTriple fields.

        Returns:
            Summary dict with written, quarantined, and stats.
        """
        raw: list[RawTriple] = []
        for t in triples:
            if isinstance(t, RawTriple):
                raw.append(t)
            elif isinstance(t, dict):
                raw.append(RawTriple(**t))

        result = clean_triples(raw, kb_id=kb_id)
        return persist_clean_result(result, kb_id)
