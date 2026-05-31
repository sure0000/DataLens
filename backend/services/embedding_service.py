import asyncio
import hashlib
from typing import Any

from openai import OpenAI
from pgvector.sqlalchemy import Vector

from services.httpx_env import sync_client as httpx_sync_client
from sqlalchemy import cast, delete, select
from sqlalchemy.orm import Session

from config import get_settings
from models import Embedding, KnowledgeEntry

settings = get_settings()

KNOWLEDGE_EMBEDDING_REF = "knowledge_entry"
TABLE_EMBEDDING_REF = "table"
ONTOLOGY_CONCEPT_EMBEDDING_REF = "ontology_concept"


def _has_embedding_key() -> bool:
    return bool(settings.openai_api_key)


def _embedding_client() -> OpenAI:
    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for remote embeddings")
    return OpenAI(api_key=api_key, http_client=httpx_sync_client(timeout=60.0))


def _local_embed(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values = [((seed[i % len(seed)] / 255.0) * 2.0) - 1.0 for i in range(1536)]
        vectors.append(values)
    return vectors


def _embed(texts: list[str]) -> list[list[float]]:
    if not _has_embedding_key():
        return _local_embed(texts)
    cli = _embedding_client()
    resp = cli.embeddings.create(model="text-embedding-3-small", input=texts)
    return [r.embedding for r in resp.data]


def embed_and_store(
    db: Session, ref_type: str, ref_id: int, content: str, *, commit: bool = True
) -> None:
    vec = _embed([content])[0]
    db.add(Embedding(ref_type=ref_type, ref_id=ref_id, content=content, embedding=vec))
    if commit:
        db.commit()


async def embed_and_store_async(
    db: Session, ref_type: str, ref_id: int, content: str, *, commit: bool = True
) -> None:
    vectors = await asyncio.to_thread(_embed, [content])
    vec = vectors[0]
    db.add(Embedding(ref_type=ref_type, ref_id=ref_id, content=content, embedding=vec))
    if commit:
        db.commit()


def _search_similar_with_vector(
    db: Session,
    qv: list[float],
    top_k: int,
    table_id: int | None,
    ref_type: str | None = "query",
    allowed_table_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    stmt = select(Embedding)
    if ref_type is not None:
        stmt = stmt.where(Embedding.ref_type == ref_type)
    if table_id is not None:
        stmt = stmt.where(Embedding.ref_id == table_id)
    elif allowed_table_ids is not None:
        if not allowed_table_ids:
            return []
        stmt = stmt.where(Embedding.ref_id.in_(allowed_table_ids))
    stmt = stmt.order_by(Embedding.embedding.cosine_distance(cast(qv, Vector(1536)))).limit(top_k)
    rows = db.execute(stmt).scalars().all()
    return [{"ref_type": r.ref_type, "ref_id": r.ref_id, "content": r.content} for r in rows]


def search_similar(
    db: Session,
    query: str,
    top_k: int = 5,
    table_id: int | None = None,
    ref_type: str | None = "query",
    allowed_table_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    qv = _embed([query])[0]
    return _search_similar_with_vector(
        db, qv, top_k, table_id, ref_type=ref_type, allowed_table_ids=allowed_table_ids
    )


async def search_similar_async(
    db: Session,
    query: str,
    top_k: int = 5,
    table_id: int | None = None,
    ref_type: str | None = "query",
    allowed_table_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    qv = (await asyncio.to_thread(_embed, [query]))[0]
    return _search_similar_with_vector(
        db, qv, top_k, table_id, ref_type=ref_type, allowed_table_ids=allowed_table_ids
    )


def search_table_embeddings(
    db: Session,
    query: str,
    allowed_table_ids: set[int] | list[int],
    top_k: int = 15,
    *,
    query_vector: list[float] | None = None,
) -> list[tuple[int, float]]:
    """检索 allowed 范围内表摘要向量，返回 (table_id, cosine_distance) 按距离升序。"""
    q = (query or "").strip()
    if not q:
        return []
    ids = sorted({int(i) for i in allowed_table_ids})
    if not ids:
        return []
    qv = query_vector if query_vector is not None else _embed([q])[0]
    probe = min(len(ids), max(top_k, top_k * 2))
    stmt = (
        select(
            Embedding.ref_id,
            Embedding.embedding.cosine_distance(cast(qv, Vector(1536))).label("dist"),
        )
        .where(
            Embedding.ref_type == TABLE_EMBEDDING_REF,
            Embedding.ref_id.in_(ids),
        )
        .order_by("dist")
        .limit(probe)
    )
    rows = db.execute(stmt).all()
    seen: set[int] = set()
    out: list[tuple[int, float]] = []
    for ref_id, dist in rows:
        tid = int(ref_id)
        if tid in seen:
            continue
        seen.add(tid)
        out.append((tid, float(dist)))
        if len(out) >= top_k:
            break
    return out


COLUMN_EMBEDDING_REF = "column"


def search_column_embeddings(
    db: Session,
    query: str,
    allowed_table_ids: set[int] | list[int],
    top_k: int = 4,
    *,
    query_vector: list[float] | None = None,
) -> list[tuple[int, float]]:
    """域内列语义向量检索，返回 (table_id, cosine_distance)；用于维表/码表扩表。"""
    q = (query or "").strip()
    ids = sorted({int(i) for i in allowed_table_ids})
    if not q or not ids or top_k <= 0:
        return []
    qv = query_vector if query_vector is not None else _embed([q])[0]
    probe = min(len(ids) * 8, max(top_k * 6, top_k))
    stmt = (
        select(
            Embedding.ref_id,
            Embedding.embedding.cosine_distance(cast(qv, Vector(1536))).label("dist"),
        )
        .where(
            Embedding.ref_type == COLUMN_EMBEDDING_REF,
            Embedding.ref_id.in_(ids),
        )
        .order_by("dist")
        .limit(probe)
    )
    rows = db.execute(stmt).all()
    seen: set[int] = set()
    out: list[tuple[int, float]] = []
    for ref_id, dist in rows:
        tid = int(ref_id)
        if tid in seen:
            continue
        seen.add(tid)
        out.append((tid, float(dist)))
        if len(out) >= top_k:
            break
    return out


def search_table_embeddings_global(
    db: Session,
    query: str,
    top_k: int = 20,
    *,
    query_vector: list[float] | None = None,
) -> list[tuple[int, float]]:
    """全库表摘要向量检索（无域场景），返回 (table_id, cosine_distance)。"""
    q = (query or "").strip()
    if not q:
        return []
    qv = query_vector if query_vector is not None else _embed([q])[0]
    probe = max(top_k, top_k * 2)
    stmt = (
        select(
            Embedding.ref_id,
            Embedding.embedding.cosine_distance(cast(qv, Vector(1536))).label("dist"),
        )
        .where(Embedding.ref_type == TABLE_EMBEDDING_REF)
        .order_by("dist")
        .limit(probe)
    )
    rows = db.execute(stmt).all()
    seen: set[int] = set()
    out: list[tuple[int, float]] = []
    for ref_id, dist in rows:
        tid = int(ref_id)
        if tid in seen:
            continue
        seen.add(tid)
        out.append((tid, float(dist)))
        if len(out) >= top_k:
            break
    return out


# 单块不宜过大：嵌入模型上下文与召回粒度；重叠避免句段被硬生生切断。
_EMBED_CHUNK_CHARS = 1700
_EMBED_CHUNK_OVERLAP = 220
_EMBED_BATCH = 36


def _chunk_plain_body(body: str, max_chars: int, overlap: int) -> list[str]:
    b = body.strip()
    if not b:
        return []
    if len(b) <= max_chars:
        return [b]
    chunks: list[str] = []
    stride = max(64, max_chars - overlap)
    i = 0
    while i < len(b):
        end = min(i + max_chars, len(b))
        piece = b[i:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(b):
            break
        i += stride
    return chunks


def _knowledge_embed_chunks(title: str, body: str, summary: str | None = None) -> list[str]:
    """
    将单条条目拆成多块文本入库向量表；条目表 body 仍为完整正文，仅检索层分块。
    每块都带标题/简述前缀，便于嵌入空间对齐与用户问题匹配。
    """
    t = (title or "").strip()
    s = (summary or "").strip()
    b_raw = body or ""

    head_lines = [f"【知识条目】{t}" if t else "【知识条目】"]
    if s:
        head_lines.append(f"简述：{s}")
    head = "\n".join(head_lines).strip()

    body_chunks = _chunk_plain_body(b_raw, _EMBED_CHUNK_CHARS, _EMBED_CHUNK_OVERLAP)

    # 正文为空时也至少索引标题+简述，语义检索仍可命中条目
    if not body_chunks:
        one = head
        return [one] if one.strip() else []

    merged: list[str] = []
    n = len(body_chunks)
    for i, bc in enumerate(body_chunks):
        loc = ""
        if n > 1:
            loc = f"\n【正文分块 {i + 1}/{n}】\n"
        merged.append(head + loc + bc)
    return merged


def replace_knowledge_entry_embedding(db: Session, entry_id: int, title: str, body: str, summary: str | None = None) -> None:
    db.execute(
        delete(Embedding).where(Embedding.ref_type == KNOWLEDGE_EMBEDDING_REF, Embedding.ref_id == entry_id)
    )
    db.flush()
    chunks = _knowledge_embed_chunks(title, body, summary)
    if not chunks:
        return
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start : start + _EMBED_BATCH]
        vecs = _embed(batch)
        for txt, vec in zip(batch, vecs):
            db.add(Embedding(ref_type=KNOWLEDGE_EMBEDDING_REF, ref_id=entry_id, content=txt, embedding=vec))


def delete_embeddings_for_knowledge_entries(db: Session, entry_ids: list[int]) -> None:
    if not entry_ids:
        return
    db.execute(
        delete(Embedding).where(
            Embedding.ref_type == KNOWLEDGE_EMBEDDING_REF,
            Embedding.ref_id.in_(entry_ids),
        )
    )


def search_knowledge_semantic(
    db: Session, knowledge_base_id: int, query: str, top_k: int = 8
) -> list[dict[str, Any]]:
    """按向量相似的「块」检索，但返回时按条目去重，保留每个条目最先命中的那块（得分最高）。"""
    qv = _embed([query])[0]
    # 同一条可有多个向量块；多取候选再按 entry 去冗，避免出现 top_k 全来自同一段话不同切片或重复条目占位。
    probe = min(max(top_k * 40, top_k), 320)
    stmt = (
        select(Embedding, KnowledgeEntry)
        .join(KnowledgeEntry, KnowledgeEntry.id == Embedding.ref_id)
        .where(
            Embedding.ref_type == KNOWLEDGE_EMBEDDING_REF,
            KnowledgeEntry.knowledge_base_id == knowledge_base_id,
        )
        .order_by(Embedding.embedding.cosine_distance(cast(qv, Vector(1536))))
        .limit(probe)
    )
    rows = db.execute(stmt).all()
    out: list[dict[str, Any]] = []
    seen_ent: set[int] = set()
    for emb, entry in rows:
        if entry.id in seen_ent:
            continue
        seen_ent.add(entry.id)
        out.append(
            {
                "entry_id": entry.id,
                "title": entry.title,
                "summary": (entry.summary or "").strip(),
                "snippet": (emb.content or "").strip().replace("\r\n", "\n")[:1200],
                "score_hint": "cosine_distance_ordered",
            }
        )
        if len(out) >= top_k:
            break
    return out
