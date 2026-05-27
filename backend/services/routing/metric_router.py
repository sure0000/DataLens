"""指标 / 术语路由：口语问法 → 标准口径 → 绑定表加权。"""
from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import ColumnMeta, TableKnowledgeEntry, TableMeta
# BusinessTerm, MetricDefinition, SemanticRelation removed in Phase 1
# This module will be deleted in Phase 4
from services.semantic_grounding import table_ids_from_bound_refs


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower()))


def _keyword_score(name: str, question: str) -> float:
    name_l = (name or "").strip().lower()
    q_l = (question or "").strip().lower()
    if not name_l or not q_l:
        return 0.0
    if name_l in q_l:
        return 1.0
    name_tokens = _token_set(name_l)
    if not name_tokens:
        return 0.0
    q_tokens = _token_set(q_l)
    overlap = len(name_tokens & q_tokens) / len(name_tokens)
    return overlap * 0.55


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _table_ids_from_related_fields(
    db: Session,
    related_fields: list[Any] | None,
    domain_tables: list[TableMeta],
) -> set[int]:
    if not related_fields or not domain_tables:
        return set()
    domain_by_id = {t.id: t for t in domain_tables}
    table_ids: set[int] = set()
    col_names: set[str] = set()
    for raw in related_fields:
        field = str(raw or "").strip()
        if not field:
            continue
        if "." in field:
            parts = field.split(".")
            tbl_part = parts[-2] if len(parts) >= 2 else parts[0]
            col_part = parts[-1]
            for t in domain_tables:
                if (t.table_name or "").lower() == tbl_part.lower():
                    table_ids.add(t.id)
            col_names.add(col_part.lower())
        else:
            col_names.add(field.lower())
    if col_names:
        tids = [t.id for t in domain_tables]
        rows = db.execute(
            select(ColumnMeta.table_id).where(
                ColumnMeta.table_id.in_(tids),
                func.lower(ColumnMeta.column_name).in_(list(col_names)),
            )
        ).scalars().all()
        for tid in rows:
            if int(tid) in domain_by_id:
                table_ids.add(int(tid))
    return table_ids


def _table_ids_from_source_entry(db: Session, entry_id: int | None, allowed: set[int]) -> set[int]:
    if not entry_id:
        return set()
    out: set[int] = set()
    for tid in db.execute(
        select(TableKnowledgeEntry.table_id).where(TableKnowledgeEntry.knowledge_entry_id == entry_id)
    ).scalars().all():
        tid = int(tid)
        if tid in allowed:
            out.add(tid)
    return out


def _concept_alias_hits(db: Session, kb_ids: list[int], question: str) -> dict[str, float]:
    """concept_alias 边：问句命中别名 → concept_id → 置信加权。

    TODO(Phase 4): 从 RDF 图重新实现 concept_alias 查询（旧 SemanticRelation 表已移除）。
    """
    return {}


def search_metrics_and_terms(
    db: Session,
    question: str,
    kb_ids: list[int],
    domain_tables: list[TableMeta],
    *,
    query_vector: list[float] | None = None,
    embed_texts: Any | None = None,
    top_k: int = 6,
    min_score: float = 0.35,
) -> tuple[str, set[int], dict[int, float]]:
    """
    在域绑 KB 范围内检索指标与术语。
    返回：(口径上下文文本, 绑定表 id 集合, 表加权 bonus)

    TODO(Phase 4): 从 RDF 图重新实现（旧 MetricDefinition / BusinessTerm 表已移除）。
    """
    return "", set(), {}
