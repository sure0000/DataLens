import asyncio
import hashlib
from typing import Any

from openai import OpenAI
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.orm import Session

from config import get_settings
from models import Embedding

settings = get_settings()


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
    db: Session, qv: list[float], top_k: int, table_id: int | None
) -> list[dict[str, Any]]:
    stmt = select(Embedding)
    if table_id is not None:
        stmt = stmt.where(Embedding.ref_id == table_id)
    stmt = stmt.order_by(Embedding.embedding.cosine_distance(cast(qv, Vector(1536)))).limit(top_k)
    rows = db.execute(stmt).scalars().all()
    return [{"ref_type": r.ref_type, "ref_id": r.ref_id, "content": r.content} for r in rows]


def search_similar(db: Session, query: str, top_k: int = 5, table_id: int | None = None) -> list[dict[str, Any]]:
    qv = _embed([query])[0]
    return _search_similar_with_vector(db, qv, top_k, table_id)


async def search_similar_async(
    db: Session, query: str, top_k: int = 5, table_id: int | None = None
) -> list[dict[str, Any]]:
    qv = (await asyncio.to_thread(_embed, [query]))[0]
    return _search_similar_with_vector(db, qv, top_k, table_id)
