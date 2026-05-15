"""语义知识库流水线：编排 extract → clean → chunk → embed → index 各阶段。"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Document, DocumentChunk, KnowledgeBase, KnowledgeEntry, PipelineConfig
from services.document_cleaner import clean_text, filter_chunks
from services.document_chunker import chunk_text
from services.embedding_service import _embed

_logger = logging.getLogger(__name__)

_DEFAULT_PIPELINE_CONFIG = {
    "chunk_strategy": "heading",
    "chunk_size": 1500,
    "chunk_overlap": 200,
    "min_chunk_chars": 20,
    "dedup_threshold": 0.97,
}


def _get_pipeline_config(db: Session, kb_id: int) -> dict:
    cfg = db.execute(
        select(PipelineConfig).where(PipelineConfig.knowledge_base_id == kb_id)
    ).scalars().first()
    if cfg is None:
        return _DEFAULT_PIPELINE_CONFIG.copy()
    return {
        "chunk_strategy": cfg.chunk_strategy,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.chunk_overlap,
        "min_chunk_chars": cfg.min_chunk_chars,
        "dedup_threshold": cfg.dedup_threshold,
    }


def _set_document_status(db: Session, doc: Document, status: str, error: str | None = None) -> None:
    doc.status = status
    doc.error_message = error
    doc.updated_at = datetime.utcnow()
    db.flush()


def create_document(
    db: Session,
    kb_id: int,
    title: str,
    source_type: str = "file",
    source_meta: dict | None = None,
    knowledge_entry_id: int | None = None,
) -> Document:
    """创建 Document 记录（pending 状态），不触发流水线。"""
    doc = Document(
        knowledge_base_id=kb_id,
        title=title,
        source_type=source_type,
        source_meta=source_meta or {},
        status="pending",
        knowledge_entry_id=knowledge_entry_id,
    )
    db.add(doc)
    db.flush()
    return doc


def run_pipeline(db: Session, doc: Document, raw_text: str) -> None:
    """同步执行完整流水线。在后台线程中调用。"""
    timings: dict[str, int] = {}
    cfg = _get_pipeline_config(db, doc.knowledge_base_id)

    try:
        # Stage 1: store raw text
        t0 = time.monotonic()
        _set_document_status(db, doc, "cleaning")
        doc.raw_text = raw_text
        doc.char_count = len(raw_text)
        timings["extract_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 2: clean
        t0 = time.monotonic()
        cleaned = clean_text(raw_text)
        timings["clean_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 3: chunk
        t0 = time.monotonic()
        _set_document_status(db, doc, "chunking")
        raw_chunks = chunk_text(
            cleaned,
            strategy=cfg["chunk_strategy"],
            chunk_size=cfg["chunk_size"],
            chunk_overlap=cfg["chunk_overlap"],
        )
        filtered = filter_chunks(raw_chunks, min_chars=cfg["min_chunk_chars"])
        timings["chunk_ms"] = int((time.monotonic() - t0) * 1000)

        if not filtered:
            _set_document_status(db, doc, "failed", "清洗后无有效分块")
            doc.stage_timings = timings
            db.commit()
            return

        # Stage 4: embed + index
        t0 = time.monotonic()
        _set_document_status(db, doc, "embedding")

        # Delete old chunks for this document
        db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
        db.flush()

        texts = [content for content, _ in filtered]
        # Batch embed
        _BATCH = 36
        all_vecs: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            batch = texts[start: start + _BATCH]
            all_vecs.extend(_embed(batch))

        # Build tsvector content (Chinese + English)
        for idx, ((content, quality_score), vec) in enumerate(zip(filtered, all_vecs)):
            chunk = DocumentChunk(
                document_id=doc.id,
                knowledge_base_id=doc.knowledge_base_id,
                chunk_index=idx,
                content=content,
                quality_score=quality_score,
                embedding=vec,
            )
            db.add(chunk)

        db.flush()

        timings["embed_ms"] = int((time.monotonic() - t0) * 1000)

        doc.stage_timings = timings
        _set_document_status(db, doc, "indexed")
        db.commit()
        _logger.info("Pipeline done: doc=%d chunks=%d", doc.id, len(filtered))

    except Exception as exc:
        _logger.exception("Pipeline failed for doc=%d", doc.id)
        try:
            doc.stage_timings = timings
            _set_document_status(db, doc, "failed", str(exc)[:500])
            db.commit()
        except Exception:
            db.rollback()


async def run_pipeline_async(db: Session, doc: Document, raw_text: str) -> None:
    """异步包装，在线程池中执行流水线。"""
    await asyncio.to_thread(run_pipeline, db, doc, raw_text)


def get_document_list(db: Session, kb_id: int) -> list[dict[str, Any]]:
    docs = db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
    ).scalars().all()
    return [_doc_row(d) for d in docs]


def get_document_chunks(db: Session, doc_id: int) -> list[dict[str, Any]]:
    chunks = db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
    ).scalars().all()
    return [
        {
            "id": c.id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "quality_score": c.quality_score,
        }
        for c in chunks
    ]


def delete_document(db: Session, doc_id: int) -> None:
    doc = db.get(Document, doc_id)
    if doc:
        db.delete(doc)
        db.commit()


def retry_document(db: Session, doc_id: int) -> Document | None:
    """重置失败文档状态为 pending，触发重新处理。"""
    doc = db.get(Document, doc_id)
    if doc and doc.status == "failed" and doc.raw_text:
        _set_document_status(db, doc, "pending")
        db.commit()
    return doc


def _doc_row(d: Document) -> dict[str, Any]:
    return {
        "id": d.id,
        "knowledge_base_id": d.knowledge_base_id,
        "title": d.title,
        "source_type": d.source_type,
        "source_meta": d.source_meta or {},
        "char_count": d.char_count,
        "status": d.status,
        "error_message": d.error_message,
        "stage_timings": d.stage_timings or {},
        "knowledge_entry_id": d.knowledge_entry_id,
        "created_at": d.created_at.isoformat() if d.created_at else "",
        "updated_at": d.updated_at.isoformat() if d.updated_at else "",
    }
