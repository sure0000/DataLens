"""混合检索服务：向量检索 + BM25 关键词检索 + Reciprocal Rank Fusion。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select, text
from sqlalchemy.orm import Session

from models import DocumentChunk, Embedding, KnowledgeEntry
from services.embedding_service import KNOWLEDGE_EMBEDDING_REF, _embed

_logger = logging.getLogger(__name__)

# RRF 常数 k=60 是标准值，平衡高排名和低排名文档的权重
_RRF_K = 60
_VECTOR_PROBE = 80   # 向量检索候选数
_BM25_PROBE = 80     # 关键词检索候选数


# ---------------------------------------------------------------------------
# 新文档（DocumentChunk 表）检索
# ---------------------------------------------------------------------------

def _vector_search_chunks(
    db: Session, qv: list[float], kb_id: int, top_k: int
) -> list[tuple[int, float]]:
    """向量检索 DocumentChunk，返回 (chunk_id, cosine_distance) 列表。"""
    stmt = (
        select(DocumentChunk.id, DocumentChunk.embedding.cosine_distance(cast(qv, Vector(1536))).label("dist"))
        .where(DocumentChunk.knowledge_base_id == kb_id)
        .order_by("dist")
        .limit(top_k)
    )
    rows = db.execute(stmt).all()
    return [(r.id, float(r.dist)) for r in rows]


def _bm25_search_chunks(
    db: Session, query: str, kb_id: int, top_k: int
) -> list[tuple[int, float]]:
    """BM25 关键词检索 DocumentChunk（PostgreSQL tsvector），返回 (chunk_id, rank) 列表。"""
    stmt = text("""
        SELECT id, ts_rank(tsv, plainto_tsquery('simple', :q)) AS rank
        FROM document_chunks
        WHERE knowledge_base_id = :kb_id
          AND tsv @@ plainto_tsquery('simple', :q)
        ORDER BY rank DESC
        LIMIT :top_k
    """)
    rows = db.execute(stmt, {"q": query, "kb_id": kb_id, "top_k": top_k}).all()
    return [(r.id, float(r.rank)) for r in rows]


def _rrf_merge(*rankings: dict[int, int], top_k: int) -> list[int]:
    """Reciprocal Rank Fusion：合并多路排名，返回 ID 列表（按 RRF 分降序）。"""
    scores: dict[int, float] = {}
    for rank_map in rankings:
        for eid, rank in rank_map.items():
            scores[eid] = scores.get(eid, 0.0) + 1.0 / (_RRF_K + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)[:top_k]


def _results_to_rank_map(results: list[tuple[int, float]]) -> dict[int, int]:
    return {cid: i for i, (cid, _) in enumerate(results)}


def search_chunks_hybrid(
    db: Session,
    kb_id: int,
    query: str,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """混合检索 DocumentChunk，返回去重后的 top_k 结果，含向量分和关键词分。"""
    qv = _embed([query])[0]
    vec_results = _vector_search_chunks(db, qv, kb_id, _VECTOR_PROBE)
    bm25_results = _bm25_search_chunks(db, query, kb_id, _BM25_PROBE)

    # 构建分数映射（用于返回调试信息）
    vec_score_map = {cid: dist for cid, dist in vec_results}
    bm25_score_map = {cid: rank for cid, rank in bm25_results}

    merged_ids = _rrf_merge(
        _results_to_rank_map(vec_results),
        _results_to_rank_map(bm25_results),
        top_k=top_k * 4,
    )

    if not merged_ids:
        return []

    # 批量加载 chunks
    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.id.in_(merged_ids))
    ).scalars().all()
    chunk_map = {c.id: c for c in chunks}

    # 按 document 去重，每个 document 只保留最高分 chunk
    seen_docs: set[int] = set()
    results: list[dict[str, Any]] = []
    for cid in merged_ids:
        chunk = chunk_map.get(cid)
        if chunk is None:
            continue
        if chunk.document_id in seen_docs:
            continue
        seen_docs.add(chunk.document_id)
        results.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "content": chunk.content[:1200],
            "quality_score": chunk.quality_score,
            "vector_dist": round(vec_score_map.get(cid, 1.0), 4),
            "bm25_rank": round(bm25_score_map.get(cid, 0.0), 4),
        })
        if len(results) >= top_k:
            break
    return results


async def search_chunks_hybrid_async(
    db: Session, kb_id: int, query: str, top_k: int = 8
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(search_chunks_hybrid, db, kb_id, query, top_k)


# ---------------------------------------------------------------------------
# 旧 KnowledgeEntry（Embedding 表）检索 — 向后兼容
# ---------------------------------------------------------------------------

def search_entries_hybrid(
    db: Session,
    kb_id: int,
    query: str,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """对旧 KnowledgeEntry 做混合检索（向量 + PostgreSQL tsvector）。"""
    qv = _embed([query])[0]

    # 向量检索
    probe = min(top_k * 40, 320)
    vec_stmt = (
        select(Embedding, KnowledgeEntry)
        .join(KnowledgeEntry, KnowledgeEntry.id == Embedding.ref_id)
        .where(
            Embedding.ref_type == KNOWLEDGE_EMBEDDING_REF,
            KnowledgeEntry.knowledge_base_id == kb_id,
        )
        .order_by(Embedding.embedding.cosine_distance(cast(qv, Vector(1536))))
        .limit(probe)
    )
    vec_rows = db.execute(vec_stmt).all()

    # BM25 关键词检索（knowledge_entries 表）
    bm25_stmt = text("""
        SELECT id, ts_rank(
            to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,'')),
            plainto_tsquery('simple', :q)
        ) AS rank
        FROM knowledge_entries
        WHERE knowledge_base_id = :kb_id
          AND to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,''))
              @@ plainto_tsquery('simple', :q)
        ORDER BY rank DESC
        LIMIT :top_k
    """)
    bm25_rows = db.execute(bm25_stmt, {"q": query, "kb_id": kb_id, "top_k": probe}).all()

    # 构建向量排名
    vec_rank: dict[int, int] = {}
    vec_snippet: dict[int, str] = {}
    seen: set[int] = set()
    rank = 0
    for emb, entry in vec_rows:
        if entry.id not in seen:
            seen.add(entry.id)
            vec_rank[entry.id] = rank
            vec_snippet[entry.id] = (emb.content or "").strip()[:1200]
            rank += 1

    # 构建 BM25 排名
    bm25_rank: dict[int, int] = {r.id: i for i, r in enumerate(bm25_rows)}

    # RRF 合并
    sorted_ids = _rrf_merge(vec_rank, bm25_rank, top_k=top_k)

    # 加载 entry 详情
    entries = db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id.in_(sorted_ids))
    ).scalars().all()
    entry_map = {e.id: e for e in entries}

    results: list[dict[str, Any]] = []
    for eid in sorted_ids:
        entry = entry_map.get(eid)
        if entry is None:
            continue
        results.append({
            "entry_id": entry.id,
            "title": entry.title,
            "summary": (entry.summary or "").strip(),
            "snippet": vec_snippet.get(eid, (entry.body or "")[:1200]),
            "vector_rank": vec_rank.get(eid),
            "bm25_rank": bm25_rank.get(eid),
            "rrf_score": round(
                (1.0 / (_RRF_K + vec_rank[eid] + 1) if eid in vec_rank else 0.0)
                + (1.0 / (_RRF_K + bm25_rank[eid] + 1) if eid in bm25_rank else 0.0),
                5,
            ),
        })
    return results


async def search_entries_hybrid_async(
    db: Session, kb_id: int, query: str, top_k: int = 8
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(search_entries_hybrid, db, kb_id, query, top_k)
