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


def _knowledge_embed_text(title: str, body: str) -> str:
    raw = f"{title.strip()}\n\n{body.strip()}".strip()
    return raw[:12000] if len(raw) > 12000 else raw


def replace_knowledge_entry_embedding(db: Session, entry_id: int, title: str, body: str) -> None:
    db.execute(
        delete(Embedding).where(Embedding.ref_type == KNOWLEDGE_EMBEDDING_REF, Embedding.ref_id == entry_id)
    )
    db.flush()
    content = _knowledge_embed_text(title, body)
    if not content:
        return
    vec = _embed([content])[0]
    db.add(Embedding(ref_type=KNOWLEDGE_EMBEDDING_REF, ref_id=entry_id, content=content, embedding=vec))


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
    qv = _embed([query])[0]
    stmt = (
        select(Embedding, KnowledgeEntry)
        .join(KnowledgeEntry, KnowledgeEntry.id == Embedding.ref_id)
        .where(
            Embedding.ref_type == KNOWLEDGE_EMBEDDING_REF,
            KnowledgeEntry.knowledge_base_id == knowledge_base_id,
        )
        .order_by(Embedding.embedding.cosine_distance(cast(qv, Vector(1536))))
        .limit(top_k)
    )
    rows = db.execute(stmt).all()
    out: list[dict[str, Any]] = []
    for emb, entry in rows:
        out.append(
            {
                "entry_id": entry.id,
                "title": entry.title,
                "snippet": (emb.content or "")[:500],
                "score_hint": "cosine_distance_ordered",
            }
        )
    return out
