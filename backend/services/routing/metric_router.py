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
    """concept_alias 边：问句命中别名 → concept_id → 置信加权。"""
    q_l = (question or "").strip().lower()
    if not q_l or not kb_ids:
        return {}

    aliases = db.execute(
        select(SemanticRelation).where(
            SemanticRelation.knowledge_base_id.in_(kb_ids),
            SemanticRelation.relation_type == "concept_alias",
            SemanticRelation.status == "approved",
        )
    ).scalars().all()

    hits: dict[str, float] = {}
    for rel in aliases:
        alias = (rel.target_ref or "").strip().lower()
        cid = (rel.concept_id or rel.source_ref or "").strip()
        if not alias or not cid:
            continue
        if alias in q_l or _keyword_score(alias, q_l) >= 0.55:
            hits[cid] = max(hits.get(cid, 0.0), float(rel.confidence or 70) / 100.0)
    return hits


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
    """
    q = (question or "").strip()
    if not q or not kb_ids:
        return "", set(), {}

    allowed = {t.id for t in domain_tables}
    candidates: list[tuple[str, float, dict[str, Any]]] = []
    concept_hits = _concept_alias_hits(db, kb_ids, q)

    metrics = db.execute(
        select(MetricDefinition).where(
            MetricDefinition.knowledge_base_id.in_(kb_ids),
            MetricDefinition.status == "approved",
        )
    ).scalars().all()
    for m in metrics:
        kw = _keyword_score(m.name, q)
        cid = (getattr(m, "concept_id", None) or "").strip()
        if cid and cid in concept_hits:
            kw = max(kw, concept_hits[cid] * 0.95)
        if kw <= 0:
            continue
        candidates.append(("metric", kw, {"row": m}))

    terms = db.execute(
        select(BusinessTerm).where(
            BusinessTerm.knowledge_base_id.in_(kb_ids),
            BusinessTerm.status == "approved",
        )
    ).scalars().all()
    for t in terms:
        kw = _keyword_score(t.name, q)
        cid = (getattr(t, "concept_id", None) or "").strip()
        if cid and cid in concept_hits:
            kw = max(kw, concept_hits[cid] * 0.95)
        if kw <= 0:
            continue
        candidates.append(("term", kw, {"row": t}))

    if not candidates:
        return "", set(), {}

    # 向量精排：对关键词命中的候选做 embed 相似度（复用 bundle 传入的 embed 函数）
    if query_vector is not None and embed_texts is not None:
        scored: list[tuple[float, str, dict[str, Any]]] = []
        texts: list[str] = []
        meta: list[tuple[str, dict[str, Any]]] = []
        for kind, kw, payload in candidates:
            row = payload["row"]
            if kind == "metric":
                txt = f"{row.name} {row.formula} {row.caliber or ''}"
            else:
                txt = f"{row.name} {row.definition}"
            texts.append(txt)
            meta.append((kind, payload))
        try:
            vecs = embed_texts(texts)
            for (kind, payload), vec in zip(meta, vecs):
                row = payload["row"]
                kw = _keyword_score(row.name, q)
                sim = _cosine_similarity(query_vector, vec)
                final = max(kw, sim * 0.85)
                scored.append((final, kind, payload))
            candidates = [(k, s, p) for s, k, p in sorted(scored, key=lambda x: -x[0])]
        except Exception:
            candidates.sort(key=lambda x: -x[1])

    else:
        candidates.sort(key=lambda x: -x[1])

    bound_table_ids: set[int] = set()
    table_bonuses: dict[int, float] = {}
    lines: list[str] = ["[指标与术语口径 — 路由命中]"]

    for kind, score, payload in candidates[:top_k]:
        if score < min_score:
            continue
        row = payload["row"]
        item_table_ids: set[int] = set()
        if kind == "term":
            item_table_ids |= _table_ids_from_related_fields(db, row.related_fields, domain_tables)
            item_table_ids |= _table_ids_from_source_entry(db, row.source_entry_id, allowed)
            block = (
                f"## 术语：{row.name}（type={row.type}，score={score:.2f}）\n"
                f"定义：{row.definition}"
            )
        else:
            item_table_ids |= _table_ids_from_source_entry(db, row.source_entry_id, allowed)
            item_table_ids |= table_ids_from_bound_refs(
                domain_tables, getattr(row, "bound_table_refs", None), allowed=allowed
            )
            block = (
                f"## 指标：{row.name}（score={score:.2f}）\n"
                f"公式：{row.formula}\n"
                f"口径：{(row.caliber or '').strip() or '（未填写）'}"
            )
        bound_table_ids |= item_table_ids
        bonus = score * 0.04
        for tid in item_table_ids:
            table_bonuses[tid] = max(table_bonuses.get(tid, 0.0), bonus)
        if item_table_ids:
            block += f"\n关联表 table_id：{', '.join(str(i) for i in sorted(item_table_ids))}"
        lines.append(block)

    if len(lines) <= 1:
        return "", set(), {}
    return "\n\n".join(lines), bound_table_ids, table_bonuses
