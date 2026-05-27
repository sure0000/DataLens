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
    """TODO(Phase 4): 从 RDF 图重新实现（旧 SemanticRelation 表已移除）。"""
    return []


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
    """沿 data_lineage + semantic_relations 1-hop 扩展候选表。

    TODO(Phase 4): semantic_relations 部分需从 RDF 图重新实现（旧 SemanticRelation 表已移除）。
    """
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
    # Ontology SPARQL join expansion (still functional)
    if settings.ontology_enabled and primary_table_id:
        from services.routing.ontology_router import expand_tables_via_ontology

        top_k = settings.copilot_lineage_expand_top_k
        primary = next((t for t in domain_tables if t.id == primary_table_id), None)
        if primary is not None:
            blocked = blacklist_table_ids(domain_tables, parse_join_blacklist_fq(settings.copilot_join_blacklist))
            allowed = {t.id for t in domain_tables} - blocked - {primary_table_id}

            onto_neighbors = expand_tables_via_ontology(
                db, kb_ids, primary_table_id, allowed | {primary_table_id}, top_k=top_k
            )
            rank = 0
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
