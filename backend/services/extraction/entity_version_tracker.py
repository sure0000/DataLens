"""Entity version tracking and semantic change detection (P3.1).

Before writing extraction results to the graph, compares new triples against
existing entity state to detect meaningful semantic changes. Appends version
metadata (dl:version, dl:changeNote) for changed entities, enabling audit
trails and ontology evolution management.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ontology import NS, kb_graph_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

SKOS_PREF_LABEL = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEFINITION = "http://www.w3.org/2004/02/skos/core#definition"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

# Properties whose changes constitute a semantic version bump
_TRACKED_PROPERTIES: dict[str, str] = {
    SKOS_PREF_LABEL: "标签",
    SKOS_DEFINITION: "定义",
    f"{NS}formula": "公式",
    f"{NS}caliber": "口径",
    f"{NS}confidence": "置信度",
    f"{NS}approvalStatus": "审批状态",
    f"{NS}dimensionType": "维度类型",
    f"{NS}businessSummary": "业务摘要",
    f"{NS}sensitivityLevel": "敏感等级",
    f"{NS}layer": "数据层级",
    f"{NS}transformLogic": "转换逻辑",
}

# Relationship predicates whose changes we track
_TRACKED_RELATIONSHIPS: dict[str, str] = {
    f"{NS}dependsOn": "依赖关系",
    f"{NS}derivedFrom": "派生来源",
    f"{NS}aggregatesOver": "聚合维度",
    f"{NS}computedFromTable": "计算来源表",
    f"{NS}mapsToColumn": "映射字段",
    f"{NS}belongsToDomain": "归属领域",
    f"{NS}groundedBy": "证据来源",
    "http://www.w3.org/2004/02/skos/core#broader": "上层概念",
    "http://www.w3.org/2004/02/skos/core#related": "关联概念",
}


def _query_existing_entity(
    store: Any,
    kb_id: int,
    entity_iri: str,
) -> dict[str, list[str]]:
    """Query existing property values and relationship targets for an entity.

    Returns {predicate: [object_value, ...]} mapping.
    """
    query = f"""
        SELECT ?p ?o WHERE {{
            GRAPH <{kb_graph_iri(kb_id)}> {{
                <{entity_iri}> ?p ?o .
            }}
        }}
    """
    try:
        rows = store.sparql_query(query)
        result: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            p = str(r.get("p", ""))
            o = str(r.get("o", ""))
            if p and o:
                result[p].append(o)
        return dict(result)
    except Exception:
        _logger.debug("Failed to query existing entity %s", entity_iri, exc_info=True)
        return {}


def _detect_semantic_changes(
    entity_iri: str,
    new_triples: list[RawTriple],
    existing_state: dict[str, list[str]],
) -> list[str]:
    """Compare new triples against existing state and produce change descriptions.

    Returns a list of Chinese change note strings.
    """
    changes: list[str] = []

    # Build new state from triples
    new_state: dict[str, list[str]] = defaultdict(list)
    for t in new_triples:
        if str(t.subject) == entity_iri:
            new_state[str(t.predicate)].append(str(t.object))

    # Check tracked literal properties
    for pred_uri, label_cn in _TRACKED_PROPERTIES.items():
        old_vals = set(existing_state.get(pred_uri, []))
        new_vals = set(new_state.get(pred_uri, []))
        if not old_vals and not new_vals:
            continue
        if old_vals != new_vals:
            if not old_vals:
                changes.append(f"新增{label_cn}: {', '.join(sorted(new_vals)[:3])}")
            elif not new_vals:
                changes.append(f"移除{label_cn}: {', '.join(sorted(old_vals)[:3])}")
            else:
                changes.append(f"更新{label_cn}: {', '.join(sorted(old_vals)[:3])} → {', '.join(sorted(new_vals)[:3])}")

    # Check tracked relationship predicates
    for pred_uri, label_cn in _TRACKED_RELATIONSHIPS.items():
        old_vals = set(existing_state.get(pred_uri, []))
        new_vals = set(new_state.get(pred_uri, []))
        if not old_vals and not new_vals:
            continue
        if old_vals != new_vals:
            added = new_vals - old_vals
            removed = old_vals - new_vals
            if added and not removed:
                changes.append(f"{label_cn}新增 {len(added)} 项")
            elif removed and not added:
                changes.append(f"{label_cn}移除 {len(removed)} 项")
            else:
                changes.append(f"{label_cn}变更 (+{len(added)}/-{len(removed)})")

    return changes


def apply_version_tracking(
    triples: list[RawTriple],
    kb_id: int,
    store: Any,
) -> list[RawTriple]:
    """Detect entity changes and append version/changeNote metadata triples.

    For each entity IRI in the new triples that already exists in the graph,
    compares new vs existing state and appends dl:version + dl:changeNote
    when semantic changes are detected.

    Args:
        triples: All extraction triples for the current run.
        kb_id: The knowledge base being processed.
        store: TripleStore for querying existing state.

    Returns:
        Updated triples list with version metadata appended.
    """
    if not triples or store is None:
        return triples

    graph = kb_graph_iri(kb_id)
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # Group new triples by subject IRI
    new_by_entity: dict[str, list[RawTriple]] = defaultdict(list)
    for t in triples:
        subj = str(t.subject)
        # Only track entities with a namespace IRI (skip literals/blank nodes)
        if subj.startswith("http"):
            new_by_entity[subj].append(t)

    if not new_by_entity:
        return triples

    version_triples: list[RawTriple] = []
    entities_checked = 0
    entities_changed = 0

    for entity_iri, entity_triples in new_by_entity.items():
        existing_state = _query_existing_entity(store, kb_id, entity_iri)
        if not existing_state:
            continue  # New entity, no version tracking needed

        entities_checked += 1
        changes = _detect_semantic_changes(entity_iri, entity_triples, existing_state)

        if changes:
            entities_changed += 1
            version = now_ts
            change_note = "; ".join(changes)
            version_triples.append(RawTriple(
                entity_iri, f"{NS}version", version, False,
                graph=graph, confidence=100.0, source_type="version_tracker",
            ))
            version_triples.append(RawTriple(
                entity_iri, f"{NS}changeNote", change_note, False,
                graph=graph, confidence=100.0, source_type="version_tracker",
            ))
            _logger.info(
                "Entity versioned: %s v%s — %s",
                entity_iri, version, change_note,
            )

    if entities_checked > 0:
        _logger.info(
            "Version tracking for kb=%s: %d existing entities checked, %d changed",
            kb_id, entities_checked, entities_changed,
        )

    return triples + version_triples
