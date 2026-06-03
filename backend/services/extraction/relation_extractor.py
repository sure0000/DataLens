"""Semantic relation extraction — produces dl:dependsOn, skos:related, dl:joinableWith triples."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

SKOS_RELATED = "http://www.w3.org/2004/02/skos/core#related"


async def extract_relation_triples(
    *,
    kb_id: int,
    term_iris: dict[str, str],   # name_lower → IRI
    metric_iris: dict[str, str],  # name_lower → IRI
    chunks: list[Any],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
) -> list[RawTriple]:
    """Extract semantic relations between extracted concepts.

    Uses LLM to identify relationships:
      - dependsOn: term/metric depends on another term
      - related: general conceptual relationship
      - derivedFrom: metric derived from another metric

    Args:
        kb_id: Knowledge base ID.
        term_iris: Map of lowercased term name → IRI.
        metric_iris: Map of lowercased metric name → IRI.
        chunks: Document chunks to analyze.
        llm_client: OpenAI-compatible async client.
        model_name: Model identifier.
        call_llm_json: async (client, model, system_prompt, user_msg) -> dict.
        load_prompt: (name: str) -> str function.

    Returns:
        List of RawTriple objects for the extracted relations.
    """
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    all_concepts = {**term_iris, **metric_iris}
    seen_pairs: set[tuple[str, str, str]] = set()

    for chunk in chunks:
        content = getattr(chunk, "content", "") or ""
        if not content.strip():
            continue

        # Build context with known concept names for the LLM
        concept_names = list(all_concepts.keys())[:50]
        context = f"已知概念: {', '.join(concept_names)}\n\n文档内容:\n{content[:6000]}"

        try:
            result = await call_llm_json(
                llm_client, model_name,
                load_prompt("extraction/relation_extraction_system"),
                context,
            )
            relations = result.get("relations", [])
        except Exception:
            _logger.warning("LLM relation extraction failed for chunk %s", getattr(chunk, "id", "?"), exc_info=True)
            continue

        for rel in relations:
            source_name = (rel.get("source") or "").strip().lower()
            target_name = (rel.get("target") or "").strip().lower()
            rel_type = (rel.get("type") or "").strip()

            if not source_name or not target_name:
                continue
            if rel_type not in ("dependsOn", "related", "relatedTo", "derivedFrom", "aggregatesOver", "mapsToColumn", "computedFromTable", "precedes", "generalizes", "usedBy"):
                continue

            source_iri = all_concepts.get(source_name)
            target_iri = all_concepts.get(target_name)
            if not source_iri or not target_iri:
                continue

            pair_key = (source_iri, rel_type, target_iri)
            if pair_key in seen_pairs:
                continue

            try:
                confidence = float(rel.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            # Map relation type to dl: namespace predicate
            _rel_type_map = {
                "dependsOn": "dependsOn",
                "derivedFrom": "derivedFrom",
                "related": "relatedTo",
                "relatedTo": "relatedTo",
                "aggregatesOver": "aggregatesOver",
                "mapsToColumn": "mapsToColumn",
                "computedFromTable": "computedFromTable",
                "precedes": "precedes",
                "generalizes": "generalizes",
                "usedBy": "usedBy",
            }
            pred = f"{NS}{_rel_type_map.get(rel_type, 'relatedTo')}"
            triples.append(RawTriple(
                source_iri, pred, target_iri, True,
                graph=graph, confidence=confidence,
                source_type="llm_extraction",
            ))
            seen_pairs.add(pair_key)

    _logger.info("Relation extraction for kb=%s: %d relations", kb_id, len(triples))
    return triples
