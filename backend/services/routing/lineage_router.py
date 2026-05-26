"""P2-2 血缘 / JOIN 指南 1-hop 扩表 + JOIN 黑名单。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import KnowledgeEntry, TableMeta
# DataLineage removed in Phase 1 - this module will be deleted in Phase 4

if TYPE_CHECKING:
    from services.routing_types import RoutingSearchBundle


def parse_join_blacklist_fq(raw: str) -> set[str]:
    out: set[str] = set()
    for part in (raw or "").split(","):
        fq = part.strip().lower()
        if fq:
            out.add(fq)
    return out


def blacklist_table_ids(domain_tables: list[TableMeta], blacklist_fq: set[str]) -> set[int]:
    if not blacklist_fq:
        return set()
    blocked: set[int] = set()
    for t in domain_tables:
        fq = f"{t.database_name}.{t.table_name}".lower()
        tn = (t.table_name or "").lower()
        if fq in blacklist_fq or tn in blacklist_fq:
            blocked.add(t.id)
    return blocked


def _resolve_table_ref(ref: str, domain_tables: list[TableMeta]) -> int | None:
    ref_l = (ref or "").strip().lower()
    if not ref_l:
        return None
    for t in domain_tables:
        fq = f"{t.database_name}.{t.table_name}".lower()
        tn = (t.table_name or "").lower()
        if ref_l == fq or ref_l == tn:
            return t.id
    return None


def _lineage_neighbor_refs(primary: TableMeta, lineage: DataLineage) -> str | None:
    primary_fq = f"{primary.database_name}.{primary.table_name}".lower()
    primary_tn = (primary.table_name or "").lower()
    src = (lineage.source_table or "").strip().lower()
    tgt = (lineage.target_table or "").strip().lower()
    if src in (primary_fq, primary_tn):
        return tgt
    if tgt in (primary_fq, primary_tn):
        return src
    return None


def apply_lineage_expansion(
    db: Session,
    kb_ids: list[int],
    domain_tables: list[TableMeta],
    primary_table_id: int | None,
    scores: dict[int, float],
    sources: dict[int, set[str]],
    *,
    routing_bundle: RoutingSearchBundle | None = None,
) -> tuple[dict[int, float], dict[int, set[str]]]:
    """沿 data_lineage / join_guide 1-hop 扩展候选表（权重低于主表）。"""
    settings = get_settings()
    top_k = settings.copilot_lineage_expand_top_k
    if top_k <= 0 or not primary_table_id or not domain_tables:
        return scores, sources

    primary = next((t for t in domain_tables if t.id == primary_table_id), None)
    if primary is None:
        return scores, sources

    blocked = blacklist_table_ids(domain_tables, parse_join_blacklist_fq(settings.copilot_join_blacklist))
    allowed = {t.id for t in domain_tables} - blocked - {primary_table_id}
    expanded: list[int] = []

    if kb_ids:
        lineages = db.execute(
            select(DataLineage).where(DataLineage.knowledge_base_id.in_(kb_ids))
        ).scalars().all()
        for lg in lineages:
            neighbor_ref = _lineage_neighbor_refs(primary, lg)
            if not neighbor_ref:
                continue
            tid = _resolve_table_ref(neighbor_ref, domain_tables)
            if tid is not None and tid in allowed and tid not in expanded:
                expanded.append(tid)

        guides = db.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.knowledge_base_id.in_(kb_ids),
                KnowledgeEntry.semantic_role == "join_guide",
            )
        ).scalars().all()
        for entry in guides:
            blob = f"{entry.title or ''} {entry.summary or ''} {entry.body or ''}"
            from services.context_builder import match_tables_by_name_in_blob

            for tid in match_tables_by_name_in_blob(
                domain_tables,
                blob,
                already_matched={primary_table_id},
                allowed=allowed,
            ):
                if tid not in expanded:
                    expanded.append(tid)

    if routing_bundle and routing_bundle.merged_hits:
        from services.context_builder import match_tables_by_name_in_blob
        from services.semantic_grounding import match_tables_from_grounding

        for hit in routing_bundle.merged_hits.values():
            if hit.get("source_type") == "entry":
                eid = hit.get("entry_id")
                if eid is None:
                    continue
                entry = db.get(KnowledgeEntry, int(eid))
                if entry is None or (entry.semantic_role or "") != "join_guide":
                    continue
                blob = f"{entry.title or ''} {entry.summary or ''} {entry.body or ''}"
                for tid in match_tables_by_name_in_blob(
                    domain_tables,
                    blob,
                    already_matched={primary_table_id},
                    allowed=allowed,
                ):
                    if tid not in expanded:
                        expanded.append(tid)
                continue

            if hit.get("source_type") != "chunk":
                continue
            meta = hit.get("semantic_meta") if isinstance(hit.get("semantic_meta"), dict) else None
            role = (meta or {}).get("semantic_role") or ""
            if role != "join_guide":
                continue
            grounding = (meta or {}).get("grounding")
            if isinstance(grounding, dict):
                for tid in match_tables_from_grounding(
                    domain_tables,
                    grounding,
                    already_matched={primary_table_id},
                    allowed=allowed,
                ):
                    if tid not in expanded:
                        expanded.append(tid)
            blob = f"{hit.get('title') or ''} {hit.get('snippet') or ''}"
            for tid in match_tables_by_name_in_blob(
                domain_tables,
                blob,
                already_matched={primary_table_id},
                allowed=allowed,
            ):
                if tid not in expanded:
                    expanded.append(tid)

    rank = 0
    for tid in expanded:
        if tid in scores:
            sources.setdefault(tid, set()).add("lineage")
            continue
        scores[tid] = scores.get(tid, 0.0) + settings.copilot_routing_weight_lineage / (
            settings.rrf_k + rank + 1
        )
        sources.setdefault(tid, set()).add("lineage")
        rank += 1
        if rank >= top_k:
            break
    return scores, sources
