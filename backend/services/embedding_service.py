import asyncio
import hashlib
from typing import Any

from openai import OpenAI
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, delete, select
from sqlalchemy.orm import Session

from config import get_settings
from models import Embedding, KnowledgeEntry

settings = get_settings()

KNOWLEDGE_EMBEDDING_REF = "knowledge_entry"


def _has_embedding_key() -> bool:
    return bool(settings.openai_api_key)


def _embedding_client() -> OpenAI:
    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for remote embeddings")
    return OpenAI(api_key=api_key)


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
    db: Session, qv: list[float], top_k: int, table_id: int | None, ref_type: str | None = "query"
) -> list[dict[str, Any]]:
    stmt = select(Embedding)
    if ref_type is not None:
        stmt = stmt.where(Embedding.ref_type == ref_type)
    if table_id is not None:
        stmt = stmt.where(Embedding.ref_id == table_id)
    stmt = stmt.order_by(Embedding.embedding.cosine_distance(cast(qv, Vector(1536)))).limit(top_k)
    rows = db.execute(stmt).scalars().all()
    return [{"ref_type": r.ref_type, "ref_id": r.ref_id, "content": r.content} for r in rows]


def search_similar(
    db: Session, query: str, top_k: int = 5, table_id: int | None = None, ref_type: str | None = "query"
) -> list[dict[str, Any]]:
    qv = _embed([query])[0]
    return _search_similar_with_vector(db, qv, top_k, table_id, ref_type=ref_type)


async def search_similar_async(
    db: Session, query: str, top_k: int = 5, table_id: int | None = None, ref_type: str | None = "query"
) -> list[dict[str, Any]]:
    qv = (await asyncio.to_thread(_embed, [query]))[0]
    return _search_similar_with_vector(db, qv, top_k, table_id, ref_type=ref_type)


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
