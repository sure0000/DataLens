"""P3 语义图 1-hop 扩表：data_lineage + semantic_relations 合并。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import TableMeta
# SemanticRelation removed in Phase 1 - this module will be deleted in Phase 4
from services.routing.lineage_router import (
    _resolve_table_ref,
    apply_lineage_expansion,
    blacklist_table_ids,
    parse_join_blacklist_fq,
)

if TYPE_CHECKING:
    from services.routing_types import RoutingSearchBundle


def _table_ref_variants(table: TableMeta) -> set[str]:
    fq = f"{(table.database_name or '').strip()}.{(table.table_name or '').strip()}".lower()
    tn = (table.table_name or "").strip().lower()
    out: set[str] = set()
    if fq and fq != ".":
        out.add(fq)
    if tn:
        out.add(tn)
    return out


def _neighbor_ref_from_relation(primary: TableMeta, relation: SemanticRelation) -> str | None:
    variants = _table_ref_variants(primary)
    src = (relation.source_ref or "").strip().lower()
    tgt = (relation.target_ref or "").strip().lower()
    if relation.relation_type != "table_join":
        return None
    if src in variants:
        return tgt
    if tgt in variants:
        return src
    return None


def _semantic_graph_neighbor_ids(
    db: Session,
    kb_ids: list[int],
    primary: TableMeta,
    domain_tables: list[TableMeta],
    allowed: set[int],
    *,
    skip_ids: set[int],
    top_k: int,
) -> list[int]:
    if not kb_ids or top_k <= 0:
        return []

    relations = db.execute(
        select(SemanticRelation).where(
            SemanticRelation.knowledge_base_id.in_(kb_ids),
            SemanticRelation.relation_type == "table_join",
            SemanticRelation.status == "approved",
        )
    ).scalars().all()

    out: list[int] = []
    for rel in relations:
        if len(out) >= top_k:
            break
        neighbor_ref = _neighbor_ref_from_relation(primary, rel)
        if not neighbor_ref:
            continue
        tid = _resolve_table_ref(neighbor_ref, domain_tables)
        if tid is None or tid not in allowed or tid in skip_ids or tid in out:
            continue
        out.append(tid)
    return out


def apply_graph_expansion(
    db: Session,
    kb_ids: list[int],
    domain_tables: list[TableMeta],
    primary_table_id: int | None,
    scores: dict[int, float],
    sources: dict[int, set[str]],
    *,
    routing_bundle: RoutingSearchBundle | None = None,
) -> tuple[dict[int, float], dict[int, set[str]]]:
    """沿 data_lineage + semantic_relations 1-hop 扩展候选表。"""
    scores, sources = apply_lineage_expansion(
        db,
        kb_ids,
        domain_tables,
        primary_table_id,
        scores,
        sources,
        routing_bundle=routing_bundle,
    )

    settings = get_settings()
    top_k = settings.copilot_lineage_expand_top_k
    if top_k <= 0 or not primary_table_id or not domain_tables or not kb_ids:
        return scores, sources

    primary = next((t for t in domain_tables if t.id == primary_table_id), None)
    if primary is None:
        return scores, sources

    blocked = blacklist_table_ids(domain_tables, parse_join_blacklist_fq(settings.copilot_join_blacklist))
    allowed = {t.id for t in domain_tables} - blocked - {primary_table_id}
    skip_ids = {tid for tid, src in sources.items() if "lineage" in src}

    neighbor_ids = _semantic_graph_neighbor_ids(
        db,
        kb_ids,
        primary,
        domain_tables,
        allowed,
        skip_ids=skip_ids,
        top_k=top_k,
    )

    rank = 0
    for tid in neighbor_ids:
        if tid in scores:
            sources.setdefault(tid, set()).add("semantic_graph")
            continue
        scores[tid] = scores.get(tid, 0.0) + settings.copilot_routing_weight_lineage / (
            settings.rrf_k + rank + 1
        )
        sources.setdefault(tid, set()).add("semantic_graph")
        rank += 1

    # Ontology SPARQL join expansion
    if settings.ontology_enabled and primary_table_id:
        from services.routing.ontology_router import expand_tables_via_ontology

        onto_neighbors = expand_tables_via_ontology(
            db, kb_ids, primary_table_id, allowed | {primary_table_id}, top_k=top_k
        )
        for tid in onto_neighbors:
            if tid in scores:
                sources.setdefault(tid, set()).add("ontology_graph")
                continue
            scores[tid] = scores.get(tid, 0.0) + settings.copilot_routing_weight_lineage / (
                settings.rrf_k + rank + 1
            )
            sources.setdefault(tid, set()).add("ontology_graph")
            rank += 1

    return scores, sources
