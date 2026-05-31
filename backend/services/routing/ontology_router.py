"""SPARQL-based Copilot routing — delegates to services.copilot.OntologyRouter.

Kept as a backward-compatible adapter. New code should use
services.copilot.OntologyRouter and ContextAssembler directly.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from config import get_settings
from ontology import platform_id_from_table_iri, table_iri


def _get_store():
    from services.triple_store import get_triple_store
    return get_triple_store()


def search_ontology_metrics_and_terms(
    db: Session,
    question: str,
    kb_ids: list[int],
    *,
    query_vector: list[float] | None = None,
) -> tuple[str, set[int], dict[int, float]]:
    """Return (context_text, bound_table_ids, table_bonuses)."""
    settings = get_settings()
    if not settings.ontology_enabled:
        return "", set(), {}

    try:
        from services.copilot.router import OntologyRouter
        router = OntologyRouter(_get_store())
        concepts = router.route_concepts(
            kb_ids, question, top_k=15, db=db, query_vector=query_vector
        )
    except Exception:
        return "", set(), {}

    context_parts: list[str] = []
    table_ids: set[int] = set()
    bonuses: dict[int, float] = {}

    for c in concepts:
        label = c.get("label", "")
        ctype = c.get("type", "")
        if not label:
            continue
        if "Metric" in ctype:
            formula = c.get("definition", "")
            context_parts.append(f"【指标·本体】{label}：{formula}" if formula else f"【指标·本体】{label}")
        elif "BusinessTerm" in ctype:
            definition = c.get("definition", "")
            context_parts.append(f"【术语·本体】{label}：{definition}" if definition else f"【术语·本体】{label}")

    # Resolve tables from matched concepts
    concept_iris = [c["iri"] for c in concepts if c.get("iri")]
    if concept_iris:
        try:
            from services.copilot.router import OntologyRouter
            router = OntologyRouter(_get_store())
            tables = router.route_tables(kb_ids, concept_iris, top_k=15)
            for t in tables:
                pid = t.get("platform_id")
                if pid:
                    try:
                        tid = int(pid)
                        table_ids.add(tid)
                        bonuses[tid] = bonuses.get(tid, 0) + 0.10
                    except (ValueError, TypeError):
                        pass
                # Fallback: extract from IRI
                iri = t.get("iri", "")
                tid = platform_id_from_table_iri(iri)
                if tid:
                    table_ids.add(tid)
                    bonuses[tid] = bonuses.get(tid, 0) + 0.10
        except Exception:
            pass

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
    try:
        from services.copilot.router import OntologyRouter
        router = OntologyRouter(_get_store())
        neighbors = router.expand_lineage(kb_ids, [primary_iri])
    except Exception:
        return []

    result: list[int] = []
    for n in neighbors:
        iri = n.get("iri", "")
        tid = platform_id_from_table_iri(iri)
        if tid and tid in allowed and tid not in result and tid != primary_table_id:
            result.append(tid)
        if len(result) >= top_k:
            break
    return result[:top_k]


def build_ontology_context_snippet(
    db: Session,
    table_ids: list[int],
    kb_ids: list[int],
) -> str:
    if not table_ids or not kb_ids:
        return ""

    try:
        from services.copilot.context import ContextAssembler
        assembler = ContextAssembler(_get_store())
        iris = [table_iri(tid) for tid in table_ids[:10]]
        details = assembler._fetch_table_details(kb_ids, iris)
        parts: list[str] = []
        for t in details:
            name = t.get("name") or t.get("platform_id", "?")
            summary = t.get("summary", "")
            if summary:
                parts.append(f"{name}: {summary}")
            else:
                parts.append(name)
        return "\n".join(parts)[:8000]
    except Exception:
        return ""
