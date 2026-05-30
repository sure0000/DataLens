"""Metric extraction — produces dl:Metric triples from document chunks."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, chunk_iri, concept_slug, domain_iri, kb_graph_iri, metric_iri, table_iri, term_iri
from services.extraction.chunk_progress import ChunkProgressCallback, iter_chunks_with_progress
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEF = "http://www.w3.org/2004/02/skos/core#definition"


def _bound_table_refs_from_chunk(chunk: Any) -> list[str]:
    meta = getattr(chunk, "semantic_meta", None)
    if isinstance(meta, dict):
        grounding = meta.get("grounding")
        if isinstance(grounding, dict):
            return [str(x).strip() for x in (grounding.get("table_refs") or []) if str(x or "").strip()]
    return []


async def extract_metric_triples(
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
    """Extract Metric triples from document chunks via LLM.

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
                load_prompt("metric_extraction_system"),
                content,
            )
            metrics_data = result.get("metrics", [])
        except Exception:
            _logger.warning("LLM metric extraction failed for chunk %s", getattr(chunk, "id", "?"), exc_info=True)
            continue

        bound_refs = _bound_table_refs_from_chunk(chunk)

        for item in metrics_data:
            name = (item.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue

            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            slug = concept_slug(name, "metric")
            iri = metric_iri(kb_id, slug)
            formula = (item.get("formula") or "").strip() or (item.get("caliber") or "").strip() or f"待补充：{name}"
            caliber = item.get("caliber") or ""
            definition = item.get("definition") or ""
            status = "approved" if confidence >= auto_approve_confidence else "draft"

            triples.extend([
                RawTriple(iri, RDF_TYPE, f"{NS}Metric", True, graph=graph, confidence=confidence),
                RawTriple(iri, SKOS_PREF, name, False, "zh", graph, confidence),
                RawTriple(iri, SKOS_DEF, definition or f"{name}: {formula}", False, "zh", graph, confidence),
                RawTriple(iri, f"{NS}formula", formula, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}approvalStatus", status, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}confidence", str(confidence), False, graph=graph, confidence=confidence),
            ])

            if domain_id is not None:
                triples.append(RawTriple(iri, f"{NS}belongsToDomain", domain_iri(domain_id), True, graph=graph, confidence=confidence))

            # Related terms → dl:dependsOn
            for term_name in (item.get("related_terms") or []):
                term_slug = concept_slug(str(term_name), "term")
                term_iri_str = term_iri(kb_id, term_slug)
                triples.append(RawTriple(iri, f"{NS}dependsOn", term_iri_str, True, graph=graph, confidence=confidence))

            if caliber:
                triples.append(RawTriple(iri, f"{NS}caliber", caliber, False, graph=graph, confidence=confidence))

            for ref in bound_refs:
                try:
                    table_id = int(ref)
                    triples.append(RawTriple(iri, f"{NS}computedFromTable", table_iri(table_id), True, graph=graph, confidence=confidence))
                except (ValueError, TypeError):
                    pass

            # derivedFrom chain: if LLM identifies a parent metric
            derived_from = item.get("derived_from")
            if derived_from:
                parent_slug = concept_slug(str(derived_from), "metric")
                parent_iri = metric_iri(kb_id, parent_slug)
                triples.append(RawTriple(iri, f"{NS}derivedFrom", parent_iri, True, graph=graph, confidence=confidence))

            # aggregatesOver: if LLM identifies aggregation dimensions
            for dim_name in (item.get("aggregates_over") or []):
                dim_slug = concept_slug(str(dim_name), "dim")
                dim_iri_str = f"{NS}domain/{kb_id}/dimension/{dim_slug}"
                triples.append(RawTriple(iri, f"{NS}aggregatesOver", dim_iri_str, True, graph=graph, confidence=confidence))

            chunk_id = getattr(chunk, "id", None)
            if chunk_id:
                triples.append(RawTriple(iri, f"{NS}groundedBy", chunk_iri(chunk_id), True, graph=graph, confidence=confidence))

            seen_names.add(name.lower())

    _logger.info("Metric extraction for kb=%s: %d metrics → %d triples", kb_id, len(seen_names), len(triples))
    return triples
