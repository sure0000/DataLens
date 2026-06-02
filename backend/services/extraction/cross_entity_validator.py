"""Cross-entity referential integrity validation.

Runs after all extractors complete to verify that cross-references
(dependsOn, derivedFrom, aggregatesOver, appliesTo, computedFromTable, etc.)
point to entities that actually exist in the graph or current batch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ontology import NS, kb_graph_iri

_logger = logging.getLogger(__name__)

# ── Reference predicates that MUST point to existing entities ──────────
_REFERENCE_PREDICATES: dict[str, str] = {
    f"{NS}dependsOn": "dependsOn",
    f"{NS}derivedFrom": "derivedFrom",
    f"{NS}aggregatesOver": "aggregatesOver",
    f"{NS}appliesTo": "appliesTo",
    f"{NS}computedFromTable": "computedFromTable",
    f"{NS}mapsToColumn": "mapsToColumn",
    f"{NS}groundedBy": "groundedBy",
    f"{NS}precedes": "precedes",
    f"{NS}generalizes": "generalizes",
    f"{NS}usedBy": "usedBy",
    f"{NS}triggers": "triggers",
    f"{NS}hasMeasure": "hasMeasure",
    f"{NS}hasDimension": "hasDimension",
    f"{NS}leftTable": "leftTable",
    f"{NS}rightTable": "rightTable",
    f"{NS}belongsToDomain": "belongsToDomain",
    f"{NS}materializedFrom": "materializedFrom",
    f"{NS}partOf": "partOf",
    f"{NS}hasSource": "hasSource",
    f"{NS}producesConcept": "producesConcept",
    f"{NS}documentedBy": "documentedBy",
    f"{NS}hasChunk": "hasChunk",
    f"{NS}originatedFrom": "originatedFrom",
    f"{NS}belongsToDataSource": "belongsToDataSource",
}

# ── Predicates where the target SHOULD have an rdf:type declaration ────
_TYPED_TARGET_PREDICATES: dict[str, str] = {
    f"{NS}computedFromTable": "dl:PhysicalTable",
    f"{NS}leftTable": "dl:PhysicalTable",
    f"{NS}rightTable": "dl:PhysicalTable",
    f"{NS}materializedFrom": "dl:PhysicalTable or dl:View",
    f"{NS}belongsToDataSource": "dl:DataSource",
}


@dataclass
class CrossEntityViolation:
    source: str
    predicate: str
    missing_target: str
    severity: str  # "error" | "warning"
    fix_hint: str


@dataclass
class CrossEntityReport:
    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _build_subject_index(triples: list[Any]) -> set[str]:
    """Build a set of all subject IRIs — entities that have at least one declaration."""
    return {str(t.subject) for t in triples}


def _query_existing_iris(store: Any, kb_id: int) -> set[str]:
    """Query all subject IRIs already in the knowledge base's production graph."""
    graph_iri = kb_graph_iri(kb_id)
    query = f"""
        SELECT DISTINCT ?s WHERE {{
            GRAPH <{graph_iri}> {{ ?s ?p ?o . }}
        }}
    """
    try:
        rows = store.sparql_query(query)
        return {row["s"] for row in rows if row.get("s")}
    except Exception:
        _logger.warning("Failed to query existing IRIs for kb=%s", kb_id, exc_info=True)
        return set()


def validate_cross_entity_consistency(
    triples: list[Any],
    kb_id: int,
    store: Any | None = None,
) -> CrossEntityReport:
    """Validate referential integrity across extraction results.

    Checks that URI-reference predicates point to entities that exist
    either in the current batch or in the knowledge base's production graph.
    """
    violations: list[dict[str, Any]] = []

    # Build index from current batch subjects (declared entities only)
    batch_subject_index = _build_subject_index(triples)

    # Query existing IRIs from the production graph
    existing_iris: set[str] = set()
    if store is not None:
        existing_iris = _query_existing_iris(store, kb_id)

    # Combined index: batch-declared entities + existing graph entities
    full_index = batch_subject_index | existing_iris

    for t in triples:
        pred = str(t.predicate)
        if pred not in _REFERENCE_PREDICATES:
            continue
        if not getattr(t, "object_is_uri", False):
            continue

        target = str(t.object)
        source = str(t.subject)

        # Rule 1: Target must exist somewhere (batch or existing graph)
        if target not in full_index:
            short_pred = _REFERENCE_PREDICATES[pred]
            violations.append({
                "source": source,
                "predicate": pred,
                "predicate_short": short_pred,
                "missing_target": target,
                "severity": "warning",
                "fix_hint": (
                    f"Entity {target} referenced via {short_pred} "
                    f"was not found in extraction results or existing graph"
                ),
            })

        # Rule 2: For typed-target predicates, check rdf:type exists
        if pred in _TYPED_TARGET_PREDICATES and target in full_index:
            expected_type = _TYPED_TARGET_PREDICATES[pred]
            type_found = any(
                str(t2.subject) == target
                and str(t2.predicate) == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
                for t2 in triples
            )
            if not type_found and target not in existing_iris:
                violations.append({
                    "source": source,
                    "predicate": pred,
                    "predicate_short": _REFERENCE_PREDICATES[pred],
                    "missing_target": target,
                    "severity": "warning",
                    "fix_hint": (
                        f"Target {target} is missing rdf:type declaration "
                        f"(expected {expected_type})"
                    ),
                })

    # Rule 3: No orphan BusinessRule (appliesTo must exist)
    for t in triples:
        if str(t.predicate) == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
            if str(t.object) == f"{NS}BusinessRule":
                rule_iri = str(t.subject)
                has_applies_to = any(
                    str(t2.subject) == rule_iri
                    and str(t2.predicate) == f"{NS}appliesTo"
                    and getattr(t2, "object_is_uri", False)
                    and str(t2.object) in full_index
                    for t2 in triples
                )
                if not has_applies_to:
                    violations.append({
                        "source": rule_iri,
                        "predicate": f"{NS}appliesTo",
                        "predicate_short": "appliesTo",
                        "missing_target": "(none)",
                        "severity": "warning",
                        "fix_hint": "BusinessRule has no valid appliesTo target",
                    })

    stats = {
        "total_triples_checked": len(triples),
        "reference_triples_checked": sum(
            1 for t in triples if str(t.predicate) in _REFERENCE_PREDICATES
        ),
        "violations_found": len(violations),
        "batch_entities": len(batch_subject_index),
        "existing_entities_queried": len(existing_iris),
        "combined_index_size": len(full_index),
    }

    return CrossEntityReport(
        passed=len(violations) == 0,
        violations=violations,
        stats=stats,
    )
