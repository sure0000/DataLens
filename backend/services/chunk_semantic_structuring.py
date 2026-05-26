"""文档分块语义结构化：为 DocumentChunk 写入 semantic_meta，并回写 KnowledgeEntry.semantic_role。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Document, DocumentChunk, KnowledgeEntry
# DataLineage removed in Phase 1 ontology refactoring
from prompts import load_prompt
from services.semantic_extraction import _call_llm_json, _get_llm_client
from services.semantic_grounding import dominant_semantic_role
from services.semantic_relation_sync import sync_relations_from_document

_logger = logging.getLogger(__name__)

_VALID_ROLES = frozenset({
    "table_overview",
    "column_glossary",
    "business_metric",
    "query_pattern",
    "join_guide",
    "data_quality",
    "general_reference",
})

_DEFAULT_MAX_CHUNKS = 40
_MIN_QUALITY = 0.3


def _normalize_semantic_meta(raw: dict[str, Any]) -> dict[str, Any]:
    role = (raw.get("semantic_role") or "general_reference").strip()
    if role not in _VALID_ROLES:
        role = "general_reference"

    grounding_raw = raw.get("grounding") if isinstance(raw.get("grounding"), dict) else {}
    table_refs = [
        str(x).strip()
        for x in (grounding_raw.get("table_refs") or [])
        if str(x or "").strip()
    ]
    column_refs = [
        str(x).strip()
        for x in (grounding_raw.get("column_refs") or [])
        if str(x or "").strip()
    ]

    join_edges: list[dict[str, str]] = []
    for edge in raw.get("join_edges") or []:
        if not isinstance(edge, dict):
            continue
        left = str(edge.get("left") or "").strip()
        right = str(edge.get("right") or "").strip()
        on = str(edge.get("on") or "").strip()
        if left and right:
            join_edges.append({"left": left, "right": right, "on": on})

    try:
        confidence = float(raw.get("confidence", 50))
    except (TypeError, ValueError):
        confidence = 50.0
    confidence = max(0.0, min(100.0, confidence))

    return {
        "semantic_role": role,
        "grounding": {
            "table_refs": table_refs,
            "column_refs": column_refs,
        },
        "join_edges": join_edges,
        "confidence": round(confidence, 1),
    }


async def _structure_chunk(client: Any, model_name: str, content: str) -> dict[str, Any]:
    result = await _call_llm_json(
        client,
        model_name,
        load_prompt("chunk_semantic_structuring_system"),
        content[:6000],
        temperature=0.1,
        timeout_seconds=90.0,
    )
    return _normalize_semantic_meta(result if isinstance(result, dict) else {})


async def structure_document_chunks_async(
    db: Session,
    document_id: int,
    *,
    max_chunks: int = _DEFAULT_MAX_CHUNKS,
    min_quality: float = _MIN_QUALITY,
) -> int:
    """为文档分块写入 semantic_meta；返回成功结构化块数。"""
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.info("No LLM available for chunk structuring, doc=%s", document_id)
        return 0

    client, model_name = client_info
    chunks = db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).scalars().all()

    eligible = [
        c for c in chunks
        if (c.quality_score or 0.0) >= min_quality and (c.content or "").strip()
    ][:max_chunks]

    structured = 0
    for chunk in eligible:
        try:
            meta = await _structure_chunk(client, model_name, chunk.content)
            chunk.semantic_meta = meta
            structured += 1
        except Exception:
            _logger.warning("Chunk structuring failed chunk=%s doc=%s", chunk.id, document_id, exc_info=True)

    if structured:
        db.flush()
    return structured


def apply_entry_semantic_role_from_document(db: Session, document_id: int) -> str | None:
    """按 chunk 聚合 semantic_role 回写关联 KnowledgeEntry。"""
    doc = db.get(Document, document_id)
    if doc is None or not doc.knowledge_entry_id:
        return None

    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).scalars().all()
    role = dominant_semantic_role([c.semantic_meta for c in chunks])
    if not role:
        return None

    entry = db.get(KnowledgeEntry, doc.knowledge_entry_id)
    if entry is None:
        return None
    entry.semantic_role = role
    db.flush()
    return role


def _table_ref_tail(ref: str) -> str:
    ref = (ref or "").strip()
    if not ref:
        return ""
    if "." in ref:
        return ref.rsplit(".", 1)[-1]
    return ref


def sync_join_edges_from_document(db: Session, document_id: int, knowledge_base_id: int) -> int:
    """将 join_guide 分块的 join_edges 同步到 data_lineage（按表名去重）。"""
    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).scalars().all()

    existing_pairs: set[tuple[str, str]] = {
        (
            (lg.source_table or "").strip().lower(),
            (lg.target_table or "").strip().lower(),
        )
        for lg in db.execute(
            select(DataLineage).where(DataLineage.knowledge_base_id == knowledge_base_id)
        ).scalars().all()
    }

    created = 0
    for chunk in chunks:
        meta = chunk.semantic_meta if isinstance(chunk.semantic_meta, dict) else {}
        if meta.get("semantic_role") != "join_guide":
            continue
        for edge in meta.get("join_edges") or []:
            if not isinstance(edge, dict):
                continue
            src = _table_ref_tail(str(edge.get("left") or ""))
            tgt = _table_ref_tail(str(edge.get("right") or ""))
            if not src or not tgt:
                continue
            pair = (src.lower(), tgt.lower())
            if pair in existing_pairs:
                continue
            db.add(
                DataLineage(
                    knowledge_base_id=knowledge_base_id,
                    source_table=src,
                    target_table=tgt,
                    transform_logic=str(edge.get("on") or "").strip() or None,
                    layer="DWD",
                    status="done",
                )
            )
            existing_pairs.add(pair)
            created += 1

    if created:
        db.flush()
    return created


def apply_metric_bound_table_refs_from_document(db: Session, document_id: int, knowledge_base_id: int) -> int:
    """从 business_metric 分块的 grounding 回填 MetricDefinition.bound_table_refs。"""
    from models import MetricDefinition

    doc = db.get(Document, document_id)
    if doc is None or not doc.knowledge_entry_id:
        return 0

    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).scalars().all()

    refs: list[str] = []
    for chunk in chunks:
        meta = chunk.semantic_meta if isinstance(chunk.semantic_meta, dict) else {}
        if meta.get("semantic_role") != "business_metric":
            continue
        grounding = meta.get("grounding") if isinstance(meta.get("grounding"), dict) else {}
        refs.extend(str(x).strip() for x in (grounding.get("table_refs") or []) if str(x or "").strip())

    if not refs:
        return 0

    unique_refs = list(dict.fromkeys(refs))
    metrics = db.execute(
        select(MetricDefinition).where(
            MetricDefinition.knowledge_base_id == knowledge_base_id,
            MetricDefinition.source_entry_id == doc.knowledge_entry_id,
        )
    ).scalars().all()
    updated = 0
    for metric in metrics:
        merged = list(dict.fromkeys((metric.bound_table_refs or []) + unique_refs))
        if merged != (metric.bound_table_refs or []):
            metric.bound_table_refs = merged
            updated += 1
    if updated:
        db.flush()
    return updated


def structure_document_chunks(
    db: Session,
    document_id: int,
    *,
    max_chunks: int = _DEFAULT_MAX_CHUNKS,
) -> dict[str, Any]:
    """同步入口：结构化分块、回写 entry.semantic_role，并断言本体三元组。"""
    structured = asyncio.run(
        structure_document_chunks_async(db, document_id, max_chunks=max_chunks)
    )
    role = apply_entry_semantic_role_from_document(db, document_id)
    doc = db.get(Document, document_id)
    kb_id = doc.knowledge_base_id if doc else None
    join_edges = 0
    metric_refs = 0
    graph_relations = 0
    ontology_result: dict[str, Any] = {}
    if kb_id is not None:
        join_edges = sync_join_edges_from_document(db, document_id, kb_id)
        metric_refs = apply_metric_bound_table_refs_from_document(db, document_id, kb_id)
        graph_relations = sync_relations_from_document(db, document_id, kb_id)
        # Ontology assertion (Formal OWL path)
        try:
            from config import get_settings
            if get_settings().ontology_enabled:
                from services.context_builder import kb_ids_for_business_domain, tables_from_business_domain
                from models import BusinessDomainKnowledgeBase
                from services.ontology_population import populate_from_document

                domain_row = db.execute(
                    select(BusinessDomainKnowledgeBase.domain_id).where(
                        BusinessDomainKnowledgeBase.knowledge_base_id == kb_id
                    )
                ).first()
                domain_id = int(domain_row[0]) if domain_row else None
                domain_tables = tables_from_business_domain(db, domain_id) if domain_id else []
                ontology_result = populate_from_document(
                    db, document_id, kb_id=kb_id, domain_tables=domain_tables, domain_id=domain_id
                )
        except Exception:
            _logger.warning("Ontology assertion failed doc=%s", document_id, exc_info=True)
    return {
        "structured_chunks": structured,
        "entry_semantic_role": role,
        "join_edges_synced": join_edges,
        "metrics_bound_refs": metric_refs,
        "semantic_relations_synced": graph_relations,
        "ontology": ontology_result,
    }
