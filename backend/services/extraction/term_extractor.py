"""Term extraction — produces dl:BusinessTerm triples from document chunks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ontology import NS, chunk_iri, concept_slug, domain_iri, kb_graph_iri, term_iri
from services.extraction.chunk_progress import ChunkProgressCallback, iter_chunks_with_progress
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEF = "http://www.w3.org/2004/02/skos/core#definition"
SKOS_ALT = "http://www.w3.org/2004/02/skos/core#altLabel"
SKOS_BROADER = "http://www.w3.org/2004/02/skos/core#broader"


async def extract_term_triples(
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
) -> list[RawTriple]:
    """Extract BusinessTerm triples from document chunks via LLM.

    Args:
        kb_id: Knowledge base ID for IRI construction.
        chunks: List of DocumentChunk ORM objects with .content and .id.
        llm_client: OpenAI-compatible async client.
        model_name: Model identifier string.
        call_llm_json: async (client, model, system_prompt, user_msg) -> dict.
        load_prompt: (name: str) -> str function.
        auto_approve_confidence: Confidence threshold for auto-approval.

    Returns:
        List of RawTriple objects ready for cleaning and writing.
    """
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    seen_names: set[str] = set()

    async for chunk in iter_chunks_with_progress(chunks, on_chunk_progress):
        content = getattr(chunk, "content", "") or ""

        try:
            result = await call_llm_json(
                llm_client, model_name,
                load_prompt("term_extraction_system"),
                content,
            )
            terms_data = result.get("terms", [])
        except Exception:
            _logger.warning("LLM term extraction failed for chunk %s", getattr(chunk, "id", "?"), exc_info=True)
            continue

        for item in terms_data:
            name = (item.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue

            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            slug = concept_slug(name, "term")
            iri = term_iri(kb_id, slug)
            term_type = item.get("type") or "other"
            definition = (item.get("definition") or "").strip() or name
            status = "approved" if confidence >= auto_approve_confidence else "draft"
            related_fields = item.get("related_fields") or []

            triples.extend([
                RawTriple(iri, RDF_TYPE, f"{NS}BusinessTerm", True, graph=graph, confidence=confidence),
                RawTriple(iri, SKOS_PREF, name, False, "zh", graph, confidence),
                RawTriple(iri, SKOS_DEF, definition, False, "zh", graph, confidence),
                RawTriple(iri, f"{NS}termType", term_type, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}approvalStatus", status, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}confidence", str(confidence), False, graph=graph, confidence=confidence),
            ])

            effective_domain_id = domain_id if domain_id is not None else kb_id
            triples.append(
                RawTriple(
                    iri,
                    f"{NS}belongsToDomain",
                    domain_iri(effective_domain_id),
                    True,
                    graph=graph,
                    confidence=confidence,
                )
            )

            # Synonyms → skos:altLabel
            for syn in (item.get("synonyms") or []):
                syn_str = str(syn).strip()
                if syn_str and syn_str.lower() != name.lower():
                    triples.append(RawTriple(iri, SKOS_ALT, syn_str, False, "zh", graph, confidence))

            # Parent concept → skos:broader
            parent = (item.get("parent_concept") or "").strip()
            if parent:
                parent_slug = concept_slug(parent, "term")
                parent_iri = term_iri(kb_id, parent_slug)
                triples.append(RawTriple(iri, SKOS_BROADER, parent_iri, True, graph=graph, confidence=confidence))

            for col in related_fields:
                triples.append(RawTriple(iri, f"{NS}mapsToColumn", str(col), True, graph=graph, confidence=confidence))

            chunk_id = getattr(chunk, "id", None)
            if chunk_id:
                triples.append(RawTriple(iri, f"{NS}groundedBy", chunk_iri(chunk_id), True, graph=graph, confidence=confidence))

            seen_names.add(name.lower())

    _logger.info("Term extraction for kb=%s: %d terms → %d triples", kb_id, len(seen_names), len(triples))
    return triples
