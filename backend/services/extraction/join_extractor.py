"""Join relation extraction — produces dl:JoinRelation triples from code entries."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from ontology import NS, kb_graph_iri
from services.extraction.code_patterns import GitDiagnostics, extract_joins_from_entry
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _code_table_iri(kb_id: int, table_name: str) -> str:
    slug = quote(table_name.strip().lower(), safe="")
    return f"{kb_graph_iri(kb_id)}/code-table/{slug or 'unknown'}"


def _code_datasource_iri(kb_id: int) -> str:
    return f"{kb_graph_iri(kb_id)}/code-datasource"


def _code_table_triples(kb_id: int, table_name: str) -> list[RawTriple]:
    """Minimal PhysicalTable assertions for code-inferred tables (same-batch SHACL)."""
    iri = _code_table_iri(kb_id, table_name)
    graph = kb_graph_iri(kb_id)
    slug = table_name.strip().lower() or "unknown"
    return [
        RawTriple(iri, RDF_TYPE, f"{NS}PhysicalTable", True, graph=graph),
        RawTriple(iri, f"{NS}platformId", slug, False, graph=graph),
        RawTriple(iri, f"{NS}belongsToDataSource", _code_datasource_iri(kb_id), True, graph=graph),
        RawTriple(iri, f"{NS}sensitivityLevel", "internal", False, graph=graph),
    ]


def _joins_to_triples(
    kb_id: int,
    joins_data: list[Any],
    *,
    seen_joins: set[tuple[str, str, str]],
    emitted_tables: set[str],
    join_counter: int,
) -> tuple[list[RawTriple], int]:
    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    counter = join_counter

    for item in joins_data:
        if hasattr(item, "left_table"):
            left_table = item.left_table.strip()
            right_table = item.right_table.strip()
            join_key = item.join_key.strip()
            join_type = item.join_type or "inner"
            confidence = float(item.confidence)
        else:
            left_table = (item.get("left_table") or "").strip()
            right_table = (item.get("right_table") or "").strip()
            join_key = (item.get("join_key") or "").strip()
            if not left_table or not right_table or not join_key:
                continue
            join_type = item.get("join_type") or "inner"
            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

        if not left_table or not right_table or not join_key:
            continue
        join_sig = (left_table.lower(), right_table.lower(), join_key)
        if join_sig in seen_joins:
            continue

        left_iri = _code_table_iri(kb_id, left_table)
        right_iri = _code_table_iri(kb_id, right_table)
        counter += 1
        join_iri = f"{graph}/join/{counter}"

        for table_name, table_iri in ((left_table, left_iri), (right_table, right_iri)):
            key = table_name.lower()
            if key not in emitted_tables:
                triples.extend(_code_table_triples(kb_id, table_name))
                emitted_tables.add(key)

        triples.extend([
            RawTriple(join_iri, RDF_TYPE, f"{NS}JoinRelation", True, graph=graph, confidence=confidence),
            RawTriple(join_iri, f"{NS}joinKey", join_key, False, graph=graph, confidence=confidence),
            RawTriple(join_iri, f"{NS}joinType", join_type, False, graph=graph, confidence=confidence),
            RawTriple(join_iri, f"{NS}confidence", str(confidence), False, graph=graph, confidence=confidence),
            RawTriple(join_iri, f"{NS}leftTable", left_iri, True, graph=graph, confidence=confidence),
            RawTriple(join_iri, f"{NS}rightTable", right_iri, True, graph=graph, confidence=confidence),
        ])
        seen_joins.add(join_sig)

    return triples, counter


async def extract_join_triples(
    *,
    kb_id: int,
    entries: list[Any],
    llm_client: Any,
    model_name: str,
    call_llm_json: Any,
    load_prompt: Any,
    domain_tables: list | None = None,
    diagnostics: GitDiagnostics | None = None,
    extraction_config: dict[str, Any] | None = None,
) -> list[RawTriple]:
    """Extract dl:JoinRelation triples from code entries (SQL, dbt, Python, etc.)."""
    _ = domain_tables
    cfg = extraction_config or {}
    min_chars = int(cfg.get("min_body_chars") or 50)
    enable_regex = cfg.get("enable_regex_extractors", True) is not False
    enable_llm = cfg.get("enable_llm_fallback", True) is not False
    regex_threshold = float(cfg.get("regex_confidence_threshold") or 80.0)

    if diagnostics:
        diagnostics.min_body_chars = min_chars

    triples: list[RawTriple] = []
    seen_joins: set[tuple[str, str, str]] = set()
    emitted_tables: set[str] = set()
    join_counter = 0
    llm_entries: list[Any] = []

    for entry in entries:
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < min_chars:
            continue

        regex_joins: list[Any] = []
        if enable_regex:
            regex_joins, hits = extract_joins_from_entry(entry)
            if diagnostics:
                diagnostics.record_regex_hits(hits)
            if regex_joins and all(j.confidence >= regex_threshold for j in regex_joins):
                batch, join_counter = _joins_to_triples(
                    kb_id, regex_joins,
                    seen_joins=seen_joins, emitted_tables=emitted_tables, join_counter=join_counter,
                )
                triples.extend(batch)
                if diagnostics:
                    diagnostics.record_regex_join(len(regex_joins))
                continue
            if regex_joins:
                batch, join_counter = _joins_to_triples(
                    kb_id, regex_joins,
                    seen_joins=seen_joins, emitted_tables=emitted_tables, join_counter=join_counter,
                )
                triples.extend(batch)
                if diagnostics:
                    diagnostics.record_regex_join(len(regex_joins))

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
                load_prompt("join_extraction_system"),
                text,
            )
            joins_data = result.get("joins", [])
        except Exception:
            _logger.warning("LLM join extraction failed for entry %s", getattr(entry, "id", "?"), exc_info=True)
            continue

        before = len(seen_joins)
        batch, join_counter = _joins_to_triples(
            kb_id, joins_data,
            seen_joins=seen_joins, emitted_tables=emitted_tables, join_counter=join_counter,
        )
        triples.extend(batch)
        if diagnostics:
            diagnostics.record_llm_join(len(seen_joins) - before)

    _logger.info("Join extraction for kb=%s: %d joins → %d triples", kb_id, len(seen_joins), len(triples))
    return triples
