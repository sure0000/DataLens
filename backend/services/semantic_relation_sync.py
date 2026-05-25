"""语义关系同步：从 chunk / 术语 / 指标 / 血缘写入 semantic_relations。"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    BusinessTerm,
    DataLineage,
    DocumentChunk,
    MetricDefinition,
    SemanticRelation,
)

_logger = logging.getLogger(__name__)

_RELATION_TYPES = frozenset({"term_column", "metric_table", "table_join", "concept_alias"})


def concept_slug(name: str, prefix: str) -> str:
    n = re.sub(r"\s+", "_", (name or "").strip().lower())
    n = re.sub(r"[^\w\u4e00-\u9fff._-]", "", n)
    return f"{prefix}.{n}" if n else ""


def _edge_key(
    relation_type: str,
    source_type: str,
    source_ref: str,
    target_type: str,
    target_ref: str,
) -> tuple[str, str, str, str, str]:
    return (
        relation_type.strip().lower(),
        source_type.strip().lower(),
        source_ref.strip().lower(),
        target_type.strip().lower(),
        target_ref.strip().lower(),
    )


def _existing_edge_keys(db: Session, kb_id: int) -> set[tuple[str, str, str, str, str]]:
    rows = db.execute(
        select(
            SemanticRelation.relation_type,
            SemanticRelation.source_type,
            SemanticRelation.source_ref,
            SemanticRelation.target_type,
            SemanticRelation.target_ref,
        ).where(SemanticRelation.knowledge_base_id == kb_id)
    ).all()
    return {_edge_key(r[0], r[1], r[2], r[3], r[4]) for r in rows}


def _upsert_relation(
    db: Session,
    kb_id: int,
    *,
    relation_type: str,
    source_type: str,
    source_ref: str,
    target_type: str,
    target_ref: str,
    concept_id: str | None = None,
    join_key: str | None = None,
    source_chunk_id: int | None = None,
    source_entry_id: int | None = None,
    confidence: float = 70.0,
    status: str = "approved",
    existing: set[tuple[str, str, str, str, str]],
) -> bool:
    if relation_type not in _RELATION_TYPES:
        return False
    src_ref = (source_ref or "").strip()
    tgt_ref = (target_ref or "").strip()
    if not src_ref or not tgt_ref:
        return False

    key = _edge_key(relation_type, source_type, src_ref, target_type, tgt_ref)
    if key in existing:
        return False

    db.add(
        SemanticRelation(
            knowledge_base_id=kb_id,
            relation_type=relation_type,
            source_type=source_type,
            source_ref=src_ref,
            target_type=target_type,
            target_ref=tgt_ref,
            concept_id=(concept_id or "").strip() or None,
            join_key=(join_key or "").strip() or None,
            source_chunk_id=source_chunk_id,
            source_entry_id=source_entry_id,
            confidence=round(confidence, 1),
            status=status,
        )
    )
    existing.add(key)
    return True


def _table_ref_tail(ref: str) -> str:
    ref = (ref or "").strip()
    if not ref:
        return ""
    if "." in ref:
        return ref.rsplit(".", 1)[-1]
    return ref


def sync_relations_from_document(db: Session, document_id: int, knowledge_base_id: int) -> int:
    """从 DocumentChunk.semantic_meta 同步 table_join / term_column 关系。"""
    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).scalars().all()
    if not chunks:
        return 0

    doc_entry_id = None
    from models import Document

    doc = db.get(Document, document_id)
    if doc:
        doc_entry_id = doc.knowledge_entry_id

    existing = _existing_edge_keys(db, knowledge_base_id)
    created = 0

    for chunk in chunks:
        meta = chunk.semantic_meta if isinstance(chunk.semantic_meta, dict) else {}
        role = meta.get("semantic_role") or ""
        grounding = meta.get("grounding") if isinstance(meta.get("grounding"), dict) else {}

        if role == "join_guide":
            for edge in meta.get("join_edges") or []:
                if not isinstance(edge, dict):
                    continue
                left = _table_ref_tail(str(edge.get("left") or ""))
                right = _table_ref_tail(str(edge.get("right") or ""))
                if not left or not right:
                    continue
                if _upsert_relation(
                    db,
                    knowledge_base_id,
                    relation_type="table_join",
                    source_type="table",
                    source_ref=left,
                    target_type="table",
                    target_ref=right,
                    join_key=str(edge.get("on") or "").strip() or None,
                    source_chunk_id=chunk.id,
                    source_entry_id=doc_entry_id,
                    confidence=float(meta.get("confidence", 75)),
                    existing=existing,
                ):
                    created += 1

        if role == "column_glossary":
            for col_ref in grounding.get("column_refs") or []:
                col = str(col_ref or "").strip()
                if not col:
                    continue
                if _upsert_relation(
                    db,
                    knowledge_base_id,
                    relation_type="term_column",
                    source_type="concept",
                    source_ref=concept_slug(col, "column"),
                    target_type="column",
                    target_ref=col,
                    concept_id=concept_slug(col, "column"),
                    source_chunk_id=chunk.id,
                    source_entry_id=doc_entry_id,
                    confidence=float(meta.get("confidence", 65)),
                    existing=existing,
                ):
                    created += 1

        if role == "business_metric":
            for tbl_ref in grounding.get("table_refs") or []:
                tbl = _table_ref_tail(str(tbl_ref or ""))
                if not tbl:
                    continue
                if _upsert_relation(
                    db,
                    knowledge_base_id,
                    relation_type="metric_table",
                    source_type="metric",
                    source_ref=f"chunk:{chunk.id}",
                    target_type="table",
                    target_ref=tbl,
                    source_chunk_id=chunk.id,
                    source_entry_id=doc_entry_id,
                    confidence=float(meta.get("confidence", 70)),
                    existing=existing,
                ):
                    created += 1

    if created:
        db.flush()
    return created


def _ensure_concept_ids(db: Session, kb_id: int) -> None:
    terms = db.execute(
        select(BusinessTerm).where(BusinessTerm.knowledge_base_id == kb_id)
    ).scalars().all()
    for term in terms:
        if not (term.concept_id or "").strip():
            term.concept_id = concept_slug(term.name, "term")

    metrics = db.execute(
        select(MetricDefinition).where(MetricDefinition.knowledge_base_id == kb_id)
    ).scalars().all()
    for metric in metrics:
        if not (metric.concept_id or "").strip():
            metric.concept_id = concept_slug(metric.name, "metric")

    db.flush()


def sync_relations_from_kb_entities(db: Session, knowledge_base_id: int) -> int:
    """从 BusinessTerm / MetricDefinition / DataLineage 同步关系到 semantic_relations。"""
    _ensure_concept_ids(db, knowledge_base_id)
    existing = _existing_edge_keys(db, knowledge_base_id)
    created = 0

    terms = db.execute(
        select(BusinessTerm).where(
            BusinessTerm.knowledge_base_id == knowledge_base_id,
            BusinessTerm.status == "approved",
        )
    ).scalars().all()
    for term in terms:
        cid = term.concept_id or concept_slug(term.name, "term")
        for raw in term.related_fields or []:
            field = str(raw or "").strip()
            if not field:
                continue
            if _upsert_relation(
                db,
                knowledge_base_id,
                relation_type="term_column",
                source_type="term",
                source_ref=term.name,
                target_type="column",
                target_ref=field,
                concept_id=cid,
                source_entry_id=term.source_entry_id,
                confidence=float(term.confidence or 70),
                existing=existing,
            ):
                created += 1
        if _upsert_relation(
            db,
            knowledge_base_id,
            relation_type="concept_alias",
            source_type="concept",
            source_ref=cid,
            target_type="concept",
            target_ref=term.name,
            concept_id=cid,
            source_entry_id=term.source_entry_id,
            confidence=float(term.confidence or 70),
            existing=existing,
        ):
            created += 1

    metrics = db.execute(
        select(MetricDefinition).where(
            MetricDefinition.knowledge_base_id == knowledge_base_id,
            MetricDefinition.status == "approved",
        )
    ).scalars().all()
    for metric in metrics:
        cid = metric.concept_id or concept_slug(metric.name, "metric")
        for raw in metric.bound_table_refs or []:
            tbl = _table_ref_tail(str(raw or ""))
            if not tbl:
                continue
            if _upsert_relation(
                db,
                knowledge_base_id,
                relation_type="metric_table",
                source_type="metric",
                source_ref=metric.name,
                target_type="table",
                target_ref=tbl,
                concept_id=cid,
                source_entry_id=metric.source_entry_id,
                confidence=float(metric.confidence or 75),
                existing=existing,
            ):
                created += 1
        if _upsert_relation(
            db,
            knowledge_base_id,
            relation_type="concept_alias",
            source_type="concept",
            source_ref=cid,
            target_type="concept",
            target_ref=metric.name,
            concept_id=cid,
            source_entry_id=metric.source_entry_id,
            confidence=float(metric.confidence or 75),
            existing=existing,
        ):
            created += 1

    lineages = db.execute(
        select(DataLineage).where(DataLineage.knowledge_base_id == knowledge_base_id)
    ).scalars().all()
    for lg in lineages:
        src = (lg.source_table or "").strip()
        tgt = (lg.target_table or "").strip()
        if not src or not tgt:
            continue
        if _upsert_relation(
            db,
            knowledge_base_id,
            relation_type="table_join",
            source_type="table",
            source_ref=_table_ref_tail(src),
            target_type="table",
            target_ref=_table_ref_tail(tgt),
            join_key=(lg.transform_logic or "").strip() or None,
            confidence=80.0,
            existing=existing,
        ):
            created += 1

    if created:
        db.flush()
    return created


def sync_semantic_relations_for_kb(db: Session, knowledge_base_id: int) -> dict[str, Any]:
    """全量同步 KB 级语义关系（实体 + 已索引文档 chunk）。"""
    from models import Document

    entity_count = sync_relations_from_kb_entities(db, knowledge_base_id)
    doc_count = 0
    docs = db.execute(
        select(Document).where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.status == "indexed",
        )
    ).scalars().all()
    for doc in docs:
        doc_count += sync_relations_from_document(db, doc.id, knowledge_base_id)

    return {"entity_relations": entity_count, "document_relations": doc_count}
