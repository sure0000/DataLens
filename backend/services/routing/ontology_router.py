"""SPARQL-based Copilot routing; supplements legacy RRF when ontology enabled."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from config import get_settings
from ontology import platform_id_from_table_iri, table_iri
from services.ontology_entity_linker import platform_ids_from_table_iris
from services.ontology_store import is_fuseki_enabled, sparql_query
from services.sparql_queries import (
    expand_join_neighbors,
    graph_for_kb,
    search_metrics_by_keyword,
    search_terms_by_keyword,
)


def _keywords_from_question(question: str, max_tokens: int = 8) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", (question or "").lower())
    return list(dict.fromkeys(tokens))[:max_tokens]


def search_ontology_metrics_and_terms(
    db: Session,
    question: str,
    kb_ids: list[int],
) -> tuple[str, set[int], dict[int, float]]:
    """Return (context_text, bound_table_ids, table_bonuses)."""
    settings = get_settings()
    if not settings.ontology_enabled:
        return "", set(), {}

    context_parts: list[str] = []
    table_ids: set[int] = set()
    bonuses: dict[int, float] = {}

    for kb_id in kb_ids:
        graph = graph_for_kb(kb_id)
        for kw in _keywords_from_question(question):
            try:
                for row in sparql_query(search_metrics_by_keyword(kw, graph)):
                    label = row.get("label", "")
                    formula = row.get("formula", "")
                    if label:
                        context_parts.append(f"【指标·本体】{label}：{formula}")
                    tbl = row.get("table")
                    if tbl:
                        tid = platform_id_from_table_iri(tbl)
                        if tid:
                            table_ids.add(tid)
                            bonuses[tid] = bonuses.get(tid, 0) + 0.02
                for row in sparql_query(search_terms_by_keyword(kw, graph)):
                    label = row.get("label", "")
                    definition = row.get("definition", "")
                    if label:
                        context_parts.append(f"【术语·本体】{label}：{definition or ''}")
            except Exception:
                continue

    text = "\n".join(dict.fromkeys(context_parts))[:12000]
    return text, table_ids, bonuses


def expand_tables_via_ontology(
    db: Session,
    kb_ids: list[int],
    primary_table_id: int,
    allowed: set[int],
    *,
    top_k: int = 4,
) -> list[int]:
    settings = get_settings()
    if not settings.ontology_enabled or not kb_ids:
        return []

    primary_iri = table_iri(primary_table_id)
    neighbors: list[int] = []
    for kb_id in kb_ids:
        graph = graph_for_kb(kb_id)
        try:
            for row in sparql_query(expand_join_neighbors(primary_iri, graph, limit=top_k)):
                niri = row.get("neighbor")
                if not niri:
                    continue
                tid = platform_id_from_table_iri(niri)
                if tid and tid in allowed and tid not in neighbors and tid != primary_table_id:
                    neighbors.append(tid)
        except Exception:
            continue
        if len(neighbors) >= top_k:
            break
    return neighbors[:top_k]


def build_ontology_context_snippet(
    db: Session,
    table_ids: list[int],
    kb_ids: list[int],
) -> str:
    if not table_ids or not kb_ids:
        return ""
    from services.sparql_queries import build_context_for_tables

    iris = [table_iri(tid) for tid in table_ids[:10]]
    parts: list[str] = []
    for kb_id in kb_ids:
        graph = graph_for_kb(kb_id)
        try:
            rows = sparql_query(build_context_for_tables(iris, graph))
            for row in rows:
                parts.append(str(row))
        except Exception:
            continue
    return "\n".join(parts)[:8000]
