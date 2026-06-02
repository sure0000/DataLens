"""SKOS hierarchy builder — produces broader/narrower/related triples between concepts.

Includes post-processing safety checks:
  - DFS cycle detection and quarantine of cyclic edges
  - Depth enforcement (max 6 levels per SHACL hierarchy.shacl.ttl)
  - Self-loop prevention
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from ontology import NS, kb_graph_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

SKOS_BROADER = "http://www.w3.org/2004/02/skos/core#broader"
SKOS_NARROWER = "http://www.w3.org/2004/02/skos/core#narrower"
SKOS_RELATED = "http://www.w3.org/2004/02/skos/core#related"
MAX_HIERARCHY_DEPTH = 6


def _detect_cycles(
    parent_map: dict[str, str],
) -> list[tuple[str, str]]:
    """Detect cycles in parent→child hierarchy using DFS.

    Returns a list of (child, parent) edges that create cycles.
    """
    children: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_map.items():
        children[parent].append(child)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in set(parent_map) | set(children)}
    cyclic_edges: list[tuple[str, str]] = []

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for child in children.get(node, []):
            if child not in color:
                color[child] = WHITE
            if color[child] == GRAY:
                # Found a back edge — the edge from node→child creates a cycle
                cyclic_edges.append((child, node))
            elif color[child] == WHITE:
                dfs(child, path)
        path.pop()
        color[node] = BLACK

    for node in list(color):
        if color[node] == WHITE:
            dfs(node, [])

    return cyclic_edges


def _compute_depths(
    parent_map: dict[str, str],
) -> dict[str, int]:
    """Compute the depth of each node from root nodes (nodes with no parent).

    Root nodes have depth 0. Returns {iri: depth}.
    """
    children: dict[str, list[str]] = defaultdict(list)
    all_nodes = set(parent_map.keys()) | set(parent_map.values())
    for child, parent in parent_map.items():
        children[parent].append(child)

    # Find roots (nodes with no parent in the map)
    roots = [n for n in all_nodes if n not in parent_map]

    depths: dict[str, int] = {}
    queue = deque((root, 0) for root in roots)
    while queue:
        node, depth = queue.popleft()
        depths[node] = depth
        for child in children.get(node, []):
            if child not in depths:
                queue.append((child, depth + 1))

    # Handle disconnected components: assign depth 0 to unvisited nodes
    for node in all_nodes:
        if node not in depths:
            depths[node] = 0

    return depths


def _quarantine_cycles_and_deep_paths(
    triples: list[RawTriple],
) -> tuple[list[RawTriple], list[dict[str, Any]]]:
    """Remove cyclic edges and warn on deep paths.

    Returns (clean_triples, warnings).
    """
    warnings: list[dict[str, Any]] = []

    # Build parent_map from broader triples: child → parent
    parent_map: dict[str, str] = {}
    for t in triples:
        if t.predicate == SKOS_BROADER:
            parent_map[str(t.subject)] = str(t.object)

    if not parent_map:
        return triples, warnings

    # Cycle detection
    cycles = _detect_cycles(parent_map)
    cycle_edges: set[tuple[str, str]] = set()
    for child, parent in cycles:
        cycle_edges.add((child, parent))
        _logger.warning(
            "Hierarchy cycle detected: %s → broader → %s (quarantined)",
            child, parent,
        )
        warnings.append({
            "type": "cycle_detected",
            "child": child,
            "parent": parent,
            "message": f"循环引用已隔离: {child} → broader → {parent}",
        })

    # Depth check (after removing cycles)
    clean_parent_map = {
        c: p for c, p in parent_map.items()
        if (c, p) not in cycle_edges
    }
    if clean_parent_map:
        depths = _compute_depths(clean_parent_map)
        deep_nodes = [(iri, d) for iri, d in depths.items() if d > MAX_HIERARCHY_DEPTH]
        for iri, depth in deep_nodes:
            _logger.warning("Hierarchy depth %d exceeds max %d for node %s", depth, MAX_HIERARCHY_DEPTH, iri)
            warnings.append({
                "type": "depth_exceeded",
                "node": iri,
                "depth": depth,
                "max_depth": MAX_HIERARCHY_DEPTH,
                "message": f"层级深度 {depth} 超过上限 {MAX_HIERARCHY_DEPTH}",
            })

    # Filter out cyclic edges
    clean: list[RawTriple] = []
    for t in triples:
        if t.predicate == SKOS_BROADER:
            edge = (str(t.subject), str(t.object))
            if edge in cycle_edges:
                continue
        if t.predicate == SKOS_NARROWER:
            # Also remove the reverse edge of a cycle
            reverse = (str(t.object), str(t.subject))
            if reverse in cycle_edges:
                continue
        clean.append(t)

    return clean, warnings


async def build_hierarchy_triples(
    *,
    kb_id: int,
    term_iris: dict[str, str],
    metric_iris: dict[str, str],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
) -> list[RawTriple]:
    """Build SKOS concept hierarchy from extracted terms and metrics.

    Uses LLM to identify:
      - broader/narrower: parent-child concept relationships
      - related: cross-cutting concept associations

    Includes safety checks:
      - No self-loops (broader/narrower to self)
      - Maximum depth of 6 levels
      - All referenced concepts must exist in the IRI maps

    Args:
        kb_id: Knowledge base ID.
        term_iris: Map of lowercased term name → IRI.
        metric_iris: Map of lowercased metric name → IRI.
        llm_client: OpenAI-compatible async client.
        model_name: Model identifier.
        call_llm_json: async (client, model, system_prompt, user_msg) -> dict.
        load_prompt: (name: str) -> str function.

    Returns:
        List of RawTriple objects for hierarchy edges.
    """
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    all_concepts = {**term_iris, **metric_iris}

    if len(all_concepts) < 3:
        _logger.info("Too few concepts for hierarchy building in kb=%s (%d)", kb_id, len(all_concepts))
        return triples

    # Build input for LLM: list of concept names
    concept_list = "\n".join(f"- {name}" for name in sorted(all_concepts.keys()))
    user_msg = f"已知概念列表:\n{concept_list}"

    try:
        result = await call_llm_json(
            llm_client, model_name,
            load_prompt("hierarchy_extraction_system"),
            user_msg,
        )
        hierarchy = result.get("hierarchy", [])
    except Exception:
        _logger.warning("LLM hierarchy extraction failed for kb=%s", kb_id, exc_info=True)
        return triples

    seen_pairs: set[tuple[str, str, str]] = set()

    for edge in hierarchy:
        parent_name = (edge.get("parent") or "").strip().lower()
        child_name = (edge.get("child") or "").strip().lower()
        rel_type = (edge.get("type") or "broader").strip()

        if not parent_name or not child_name:
            continue
        if parent_name == child_name:
            continue  # no self-loops

        parent_iri = all_concepts.get(parent_name)
        child_iri = all_concepts.get(child_name)
        if not parent_iri or not child_iri:
            continue

        try:
            confidence = float(edge.get("confidence", 50))
        except (ValueError, TypeError):
            confidence = 50.0

        if rel_type == "related":
            pair_key = (parent_iri, "related", child_iri)
            if pair_key in seen_pairs:
                continue
            triples.append(RawTriple(
                parent_iri, SKOS_RELATED, child_iri, True,
                graph=graph, confidence=confidence, source_type="llm_hierarchy",
            ))
            seen_pairs.add(pair_key)
        else:
            # broader/narrower pair
            pair_key = (parent_iri, "broader", child_iri)
            if pair_key in seen_pairs:
                continue
            triples.append(RawTriple(
                parent_iri, SKOS_BROADER, child_iri, True,
                graph=graph, confidence=confidence, source_type="llm_hierarchy",
            ))
            triples.append(RawTriple(
                child_iri, SKOS_NARROWER, parent_iri, True,
                graph=graph, confidence=confidence, source_type="llm_hierarchy",
            ))
            seen_pairs.add(pair_key)

    # Post-processing: cycle detection and depth enforcement
    clean_triples, warnings = _quarantine_cycles_and_deep_paths(triples)
    if warnings:
        _logger.info(
            "Hierarchy builder for kb=%s: %d edges, %d warnings (cycles=%d, deep=%d)",
            kb_id,
            len(clean_triples) // 2,
            len(warnings),
            sum(1 for w in warnings if w["type"] == "cycle_detected"),
            sum(1 for w in warnings if w["type"] == "depth_exceeded"),
        )
    else:
        _logger.info("Hierarchy builder for kb=%s: %d edges (clean)", kb_id, len(clean_triples) // 2)
    return clean_triples
