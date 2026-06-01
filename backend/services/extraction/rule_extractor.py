"""Business rule extraction — produces dl:BusinessRule triples from document chunks."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, chunk_iri, concept_slug, domain_iri, kb_graph_iri, rule_iri
from services.extraction.chunk_progress import ChunkProgressCallback, iter_chunks_with_progress
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEF = "http://www.w3.org/2004/02/skos/core#definition"


async def extract_rule_triples(
    *,
    kb_id: int,
    chunks: list[Any],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
    auto_approve_confidence: float = 80.0,
    domain_id: int | None = None,
    on_chunk_progress: ChunkProgressCallback | None = None,
    ontology_context: str = "",
) -> list[RawTriple]:
    """Extract dl:BusinessRule triples from document chunks via LLM.

    Returns:
        List of RawTriple objects ready for cleaning and writing.
    """
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    seen_names: set[str] = set()

    async for chunk in iter_chunks_with_progress(chunks, on_chunk_progress):
        content = getattr(chunk, "content", "") or ""

        user_msg = f"{ontology_context}\n\n{content}" if ontology_context else content
        try:
            result = await call_llm_json(
                llm_client, model_name,
                load_prompt("rule_extraction_system"),
                user_msg,
            )
            rules_data = result.get("rules", [])
        except Exception:
            _logger.warning("LLM rule extraction failed for chunk %s", getattr(chunk, "id", "?"), exc_info=True)
            continue

        for item in rules_data:
            name = (item.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue

            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            slug = concept_slug(name, "rule")
            iri = rule_iri(kb_id, slug)
            rule_type = item.get("rule_type") or "constraint"
            expression = item.get("expression") or ""
            status = "approved" if confidence >= auto_approve_confidence else "draft"

            triples.extend([
                RawTriple(iri, RDF_TYPE, f"{NS}BusinessRule", True, graph=graph, confidence=confidence),
                RawTriple(iri, SKOS_PREF, name, False, "zh", graph, confidence),
                RawTriple(iri, SKOS_DEF, expression, False, "zh", graph, confidence),
                RawTriple(iri, f"{NS}ruleExpression", expression, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}ruleType", rule_type, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}confidence", str(confidence), False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}approvalStatus", status, False, graph=graph, confidence=confidence),
            ])

            if domain_id is not None:
                triples.append(RawTriple(iri, f"{NS}belongsToDomain", domain_iri(domain_id), True, graph=graph, confidence=confidence))

            # applies_to → dl:appliesTo (object reference)
            applies_to = (item.get("applies_to") or "").strip()
            if applies_to:
                target_slug = concept_slug(applies_to, "term")
                target_iri = rule_iri(kb_id, target_slug)  # rule target as IRI reference
                triples.append(RawTriple(iri, f"{NS}appliesTo", target_iri, True, graph=graph, confidence=confidence))

            chunk_id = getattr(chunk, "id", None)
            if chunk_id:
                triples.append(RawTriple(iri, f"{NS}groundedBy", chunk_iri(chunk_id), True, graph=graph, confidence=confidence))

            seen_names.add(name.lower())

    _logger.info("Rule extraction for kb=%s: %d rules → %d triples", kb_id, len(seen_names), len(triples))
    return triples
