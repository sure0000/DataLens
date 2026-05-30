"""Lineage extraction — produces dl:LineageAssertion triples from code files."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri
from services.extraction.code_patterns import (
    GitDiagnostics,
    extract_lineage_from_entry,
)
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_VALID_LAYERS = frozenset({"ODS", "DWD", "DWS", "ADS", "DM"})


def _edges_to_triples(
    kb_id: int,
    edges: list[Any],
    *,
    seen_pairs: set[tuple[str, str]],
    lineage_counter: int,
) -> tuple[list[RawTriple], int]:
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    counter = lineage_counter

    for item in edges:
        if hasattr(item, "source_table"):
            source_table = item.source_table.strip()
            target_table = item.target_table.strip()
            source_field = (item.source_field or "").strip() or source_table
            target_field = (item.target_field or "").strip() or target_table
            layer = (item.layer or "DWD").strip().upper()
            transform_logic = item.transform_logic or ""
        else:
            source_table = (item.get("source_table") or "").strip()
            target_table = (item.get("target_table") or "").strip()
            if not source_table or not target_table:
                continue
            source_field = (item.get("source_field") or "").strip() or source_table
            target_field = (item.get("target_field") or "").strip() or target_table
            layer = (item.get("target_layer") or item.get("source_layer") or "DWD").strip().upper()
            transform_logic = item.get("transform_logic") or ""

        if not source_table or not target_table:
            continue
        pair = (source_table, target_table)
        if pair in seen_pairs:
            continue
        if layer not in _VALID_LAYERS:
            layer = "DWD"

        counter += 1
        lin_iri = f"{graph}/lineage/{counter}"
        triples.extend([
            RawTriple(lin_iri, RDF_TYPE, f"{NS}LineageAssertion", True, graph=graph),
            RawTriple(lin_iri, f"{NS}transformsFrom", source_table, True, graph=graph),
            RawTriple(lin_iri, f"{NS}layer", layer, False, graph=graph),
        ])
        triples.append(RawTriple(lin_iri, f"{NS}sourceField", source_field, False, graph=graph))
        if target_field and target_field != source_field:
            triples.append(RawTriple(lin_iri, f"{NS}targetField", target_field, False, graph=graph))
        if transform_logic:
            triples.append(RawTriple(lin_iri, f"{NS}transformLogic", transform_logic, False, graph=graph))
        seen_pairs.add(pair)

    return triples, counter


async def extract_lineage_triples(
    *,
    kb_id: int,
    entries: list[Any],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
    diagnostics: GitDiagnostics | None = None,
    extraction_config: dict[str, Any] | None = None,
) -> list[RawTriple]:
    """Extract LineageAssertion triples from code entries (SQL, Python, dbt, etc.)."""
    cfg = extraction_config or {}
    min_chars = int(cfg.get("min_body_chars") or 50)
    enable_regex = cfg.get("enable_regex_extractors", True) is not False
    enable_llm = cfg.get("enable_llm_fallback", True) is not False
    regex_threshold = float(cfg.get("regex_confidence_threshold") or 80.0)

    if diagnostics:
        diagnostics.min_body_chars = min_chars

    triples: list[RawTriple] = []
    seen_pairs: set[tuple[str, str]] = set()
    lineage_counter = 0
    llm_entries: list[Any] = []

    for entry in entries:
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < min_chars:
            continue

        regex_edges: list[Any] = []
        if enable_regex:
            regex_edges, hits = extract_lineage_from_entry(entry)
            if diagnostics:
                diagnostics.record_regex_hits(hits)
            if regex_edges and all(e.confidence >= regex_threshold for e in regex_edges):
                batch, lineage_counter = _edges_to_triples(
                    kb_id, regex_edges, seen_pairs=seen_pairs, lineage_counter=lineage_counter,
                )
                triples.extend(batch)
                if diagnostics:
                    diagnostics.record_regex_lineage(len(regex_edges))
                continue
            if regex_edges:
                batch, lineage_counter = _edges_to_triples(
                    kb_id, regex_edges, seen_pairs=seen_pairs, lineage_counter=lineage_counter,
                )
                triples.extend(batch)
                if diagnostics:
                    diagnostics.record_regex_lineage(len(regex_edges))

        if enable_llm:
            llm_entries.append(entry)

    for entry in llm_entries:
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < min_chars:
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

        before = len(seen_pairs)
        batch, lineage_counter = _edges_to_triples(
            kb_id, edges_data, seen_pairs=seen_pairs, lineage_counter=lineage_counter,
        )
        triples.extend(batch)
        if diagnostics:
            diagnostics.record_llm_lineage(len(seen_pairs) - before)

    _logger.info("Lineage extraction for kb=%s: %d edges → %d triples", kb_id, len(seen_pairs), len(triples))
    return triples
