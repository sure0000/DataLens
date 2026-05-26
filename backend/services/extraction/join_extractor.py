"""Join relation extraction — produces dl:JoinRelation triples from code entries."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri, table_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


async def extract_join_triples(
    *,
    kb_id: int,
    entries: list[Any],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
    domain_tables: list | None = None,
) -> list[RawTriple]:
    """Extract dl:JoinRelation triples from code entries (SQL, dbt, Python, etc.).

    Args:
        kb_id: Knowledge base ID.
        entries: List of KnowledgeEntry ORM objects with .body (source code).
        llm_client: OpenAI-compatible async client.
        model_name: Model identifier.
        call_llm_json: async (client, model, system_prompt, user_msg) -> dict.
        load_prompt: (name: str) -> str function.
        domain_tables: Optional list of known table metadata for IRI resolution.

    Returns:
        List of RawTriple objects for join relations.
    """
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    seen_joins: set[tuple[str, str, str]] = set()
    join_counter = 0

    # Build table name → IRI map from domain_tables if available
    table_name_to_iri: dict[str, str] = {}
    if domain_tables:
        for t in domain_tables:
            t_id = getattr(t, "id", None)
            t_name = getattr(t, "table_name", "") or getattr(t, "name", "")
            if t_id and t_name:
                table_name_to_iri[t_name.lower()] = table_iri(int(t_id))

    for entry in entries:
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < 50:
            continue

        text = body[:8000]

        try:
            result = await call_llm_json(
                llm_client, model_name,
                load_prompt("join_extraction_system"),
                text,
            )
            joins_data = result.get("joins", [])
        except Exception:
            _logger.warning("LLM join extraction failed for entry %s", getattr(entry, "id", "?"), exc_info=True)
            continue

        for item in joins_data:
            left_table = (item.get("left_table") or "").strip()
            right_table = (item.get("right_table") or "").strip()
            join_key = (item.get("join_key") or "").strip()
            if not left_table or not right_table:
                continue

            # Deduplicate by (left, right, join_key)
            join_sig = (left_table.lower(), right_table.lower(), join_key)
            if join_sig in seen_joins:
                continue

            join_type = item.get("join_type") or "inner"
            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            join_counter += 1
            join_iri = f"{graph}/join/{join_counter}"

            triples.extend([
                RawTriple(join_iri, RDF_TYPE, f"{NS}JoinRelation", True, graph=graph, confidence=confidence),
                RawTriple(join_iri, f"{NS}joinKey", join_key, False, graph=graph, confidence=confidence),
                RawTriple(join_iri, f"{NS}joinType", join_type, False, graph=graph, confidence=confidence),
                RawTriple(join_iri, f"{NS}confidence", str(confidence), False, graph=graph, confidence=confidence),
            ])

            # Resolve table names to IRIs
            left_iri = table_name_to_iri.get(left_table.lower())
            right_iri = table_name_to_iri.get(right_table.lower())
            if not left_iri:
                left_iri = f"{NS}table/{left_table.lower()}"
            if not right_iri:
                right_iri = f"{NS}table/{right_table.lower()}"

            triples.append(RawTriple(join_iri, f"{NS}leftTable", left_iri, True, graph=graph, confidence=confidence))
            triples.append(RawTriple(join_iri, f"{NS}rightTable", right_iri, True, graph=graph, confidence=confidence))

            seen_joins.add(join_sig)

    _logger.info("Join extraction for kb=%s: %d joins → %d triples", kb_id, len(seen_joins), len(triples))
    return triples
