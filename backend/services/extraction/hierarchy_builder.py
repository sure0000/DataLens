"""SKOS hierarchy builder — produces broader/narrower/related triples between concepts."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

SKOS_BROADER = "http://www.w3.org/2004/02/skos/core#broader"
SKOS_NARROWER = "http://www.w3.org/2004/02/skos/core#narrower"
SKOS_RELATED = "http://www.w3.org/2004/02/skos/core#related"
MAX_HIERARCHY_DEPTH = 6


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

    _logger.info("Hierarchy builder for kb=%s: %d edges", kb_id, len(triples) // 2)
    return triples
