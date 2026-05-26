"""Lineage extraction — produces dl:LineageAssertion triples from code files."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri, table_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


async def extract_lineage_triples(
    *,
    kb_id: int,
    entries: list[Any],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
) -> list[RawTriple]:
    """Extract LineageAssertion triples from code entries (SQL, Python, dbt, etc.).

    Args:
        kb_id: Knowledge base ID.
        entries: List of KnowledgeEntry ORM objects with .body (source code).
        llm_client: OpenAI-compatible async client.
        model_name: Model identifier.
        call_llm_json: async (client, model, system_prompt, user_msg) -> dict.
        load_prompt: (name: str) -> str function.

    Returns:
        List of RawTriple objects for lineage assertions.
    """
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    seen_pairs: set[tuple[str, str]] = set()
    lineage_counter = 0

    for entry in entries:
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < 50:
            continue

        text = body[:8000]

        try:
            result = await call_llm_json(
                llm_client, model_name,
                load_prompt("lineage_extraction_system"),
                text,
            )
            edges_data = result.get("edges", [])
        except Exception:
            _logger.warning("LLM lineage extraction failed for entry %s", getattr(entry, "id", "?"), exc_info=True)
            continue

        for item in edges_data:
            source_table = (item.get("source_table") or "").strip()
            target_table = (item.get("target_table") or "").strip()
            if not source_table or not target_table:
                continue

            pair = (source_table, target_table)
            if pair in seen_pairs:
                continue

            source_field = item.get("source_field") or ""
            target_field = item.get("target_field") or ""
            layer = item.get("target_layer") or item.get("source_layer") or "DWD"
            transform_logic = item.get("transform_logic") or ""

            # LineageAssertion IRI
            lineage_counter += 1
            lin_iri = f"{graph}/lineage/{lineage_counter}"

            triples.extend([
                RawTriple(lin_iri, RDF_TYPE, f"{NS}LineageAssertion", True, graph=graph),
                RawTriple(lin_iri, f"{NS}transformsFrom", source_table, True, graph=graph),
                RawTriple(lin_iri, f"{NS}layer", layer, False, graph=graph),
            ])

            if source_field:
                triples.append(RawTriple(lin_iri, f"{NS}sourceField", source_field, False, graph=graph))
            if target_field:
                triples.append(RawTriple(lin_iri, f"{NS}targetField", target_field, False, graph=graph))
            if transform_logic:
                triples.append(RawTriple(lin_iri, f"{NS}transformLogic", transform_logic, False, graph=graph))

            seen_pairs.add(pair)

    _logger.info("Lineage extraction for kb=%s: %d edges → %d triples", kb_id, len(seen_pairs), len(triples))
    return triples
