"""统一的知识条目创建与管理服务。"""

import hashlib
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import KnowledgeEntry
from services.embedding_service import replace_knowledge_entry_embedding


def _content_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()


def _plain_excerpt(body: str, max_len: int = 420) -> str:
    s = (body or "").strip()
    if not s:
        return ""
    s = re.sub(r"[\n\r\t]+", " ", s)
    s = re.sub(r" +", " ", s).strip()
    if len(s) <= max_len:
        return s
    return f"{s[: max_len - 1].rstrip()}…"


def _next_sort_order(db: Session, kb_id: int) -> int:
    max_order = db.execute(
        select(KnowledgeEntry.sort_order)
        .where(KnowledgeEntry.knowledge_base_id == kb_id)
        .order_by(KnowledgeEntry.sort_order.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (max_order or 0) + 1


def create_entry(
    db: Session,
    kb_id: int,
    title: str,
    body: str,
    *,
    summary: str = "",
    source_meta: dict[str, Any] | None = None,
    source_url: str | None = None,
    sort_order: int | None = None,
) -> KnowledgeEntry:
    """创建单条知识条目，自动写入向量索引。"""
    resolved_summary = (summary or "").strip()
    if not resolved_summary:
        resolved_summary = _plain_excerpt(body)

    entry = KnowledgeEntry(
        knowledge_base_id=kb_id,
        title=title.strip()[:500],
        summary=resolved_summary,
        body=body or "",
        sort_order=sort_order if sort_order is not None else _next_sort_order(db, kb_id),
        source_url=(source_url or "").strip() or None,
        source_meta=source_meta or {},
        updated_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
    return entry


def create_entries_batch(
    db: Session,
    kb_id: int,
    items: list[dict[str, Any]],
    *,
    base_sort_order: int | None = None,
) -> list[KnowledgeEntry]:
    """批量创建知识条目（同一来源），按顺序分配 sort_order。"""
    if not items:
        return []

    next_order = base_sort_order if base_sort_order is not None else _next_sort_order(db, kb_id)
    entries: list[KnowledgeEntry] = []

    for item in items:
        title = str(item.get("title", "未命名")).strip()[:500]
        body = str(item.get("body", ""))
        summary = str(item.get("summary", "")).strip()
        if not summary:
            summary = _plain_excerpt(body)

        entry = KnowledgeEntry(
            knowledge_base_id=kb_id,
            title=title,
            summary=summary,
            body=body,
            sort_order=next_order,
            source_url=(str(item.get("source_url", ""))).strip() or None,
            source_meta=item.get("source_meta") or {},
            updated_at=datetime.utcnow(),
        )
        db.add(entry)
        db.flush()
        replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
        entries.append(entry)
        next_order += 1

    return entries
