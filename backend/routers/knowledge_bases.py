"""知识库 API：集合管理 + Markdown 条目 + 语义知识库流水线 + 混合检索。"""

import re
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import Document, KnowledgeBase, KnowledgeEntry
from services.embedding_service import (
    KNOWLEDGE_EMBEDDING_REF,
    delete_embeddings_for_knowledge_entries,
)
from services.entry_service import create_entry as create_entry_svc
from services.knowledge_ingest import (
    MAX_INGEST_BYTES,
    file_to_plain,
    normalize_filename,
    title_from_filename,
)
from services.knowledge_pipeline_service import (
    create_document,
    delete_document,
    get_document_chunks,
    get_document_list,
    retry_document,
    run_pipeline,
)
from services.retrieval_service import search_entries_hybrid

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


def _plain_excerpt(body: str, max_len: int = 420) -> str:
    s = (body or "").strip()
    if not s:
        return ""
    s = re.sub(r"[\n\r\t]+", " ", s)
    s = re.sub(r" +", " ", s).strip()
    if len(s) <= max_len:
        return s
    return f"{s[: max_len - 1].rstrip()}…"


def _resolved_summary(explicit_summary: str, body: str) -> str:
    t = (explicit_summary or "").strip()
    if t:
        return t
    return _plain_excerpt(body)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str = ""


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None


class EntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = ""
    summary: str = Field(default="", max_length=2000)


class EntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    summary: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None


class EntryBatchDeleteBody(BaseModel):
    entry_ids: list[int] = Field(min_length=1, max_length=500)


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=30)


def _kb_row(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description or "",
        "created_at": kb.created_at.isoformat() if kb.created_at else "",
    }


def _entry_row(e: KnowledgeEntry) -> dict:
    sm = e.source_meta if isinstance(e.source_meta, dict) else {}
    return {
        "id": e.id,
        "knowledge_base_id": e.knowledge_base_id,
        "title": e.title,
        "summary": e.summary if (e.summary is not None) else "",
        "body": e.body or "",
        "sort_order": e.sort_order,
        "source_url": (e.source_url or "").strip() or None,
        "source_meta": sm,
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


@router.get("")
def list_knowledge_bases(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())).scalars().all()
    return {"knowledge_bases": [_kb_row(r) for r in rows]}


@router.post("")
def create_knowledge_base(body: KnowledgeBaseCreate, db: Session = Depends(get_db)) -> dict:
    kb = KnowledgeBase(name=body.name.strip(), description=body.description.strip() or None)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {"id": kb.id, **_kb_row(kb)}


@router.get("/{kb_id}")
def get_knowledge_base(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    entries = (
        db.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.knowledge_base_id == kb_id)
            .order_by(KnowledgeEntry.sort_order.asc(), KnowledgeEntry.id.asc())
        )
        .scalars()
        .all()
    )
    return {"knowledge_base": _kb_row(kb), "entries": [_entry_row(e) for e in entries]}


@router.put("/{kb_id}")
def update_knowledge_base(kb_id: int, body: KnowledgeBaseUpdate, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if body.name is not None:
        kb.name = body.name.strip()
    if body.description is not None:
        kb.description = body.description.strip() or None
    db.commit()
    db.refresh(kb)
    return {"knowledge_base": _kb_row(kb)}


@router.delete("/{kb_id}")
def delete_knowledge_base(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    entry_ids = list(
        db.execute(select(KnowledgeEntry.id).where(KnowledgeEntry.knowledge_base_id == kb_id)).scalars().all()
    )
    delete_embeddings_for_knowledge_entries(db, entry_ids)
    db.delete(kb)
    db.commit()
    return {"ok": True}


@router.post("/{kb_id}/entries")
def create_entry(kb_id: int, body: EntryCreate, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    entry = create_entry_svc(
        db, kb_id, body.title, body.body or "",
        summary=body.summary,
        source_meta={"kind": "manual"},
    )
    db.commit()
    db.refresh(entry)
    return {"entry": _entry_row(entry)}


@router.post("/{kb_id}/entries/import-file")
async def import_entry_from_file(kb_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    fname = normalize_filename(file.filename or "upload.bin")
    raw = await file.read()
    if len(raw) > MAX_INGEST_BYTES:
        raise HTTPException(status_code=400, detail=f"文件超过 {MAX_INGEST_BYTES // (1024 * 1024)}MB 上限")
    try:
        plain = file_to_plain(fname, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not plain.strip():
        raise HTTPException(status_code=400, detail="文件解析结果为空")
    title = title_from_filename(fname)
    meta = {"kind": "file", "ref": fname, "label": "上传文件"}

    # 同时创建 KnowledgeEntry（向后兼容）和 Document（新流水线）
    entry = create_entry_svc(db, kb_id, title, plain, source_meta=meta)
    db.commit()
    db.refresh(entry)

    doc = create_document(db, kb_id, title, source_type="file", source_meta=meta, knowledge_entry_id=entry.id)
    db.commit()

    # 在后台线程运行流水线，不阻塞响应
    doc_id = doc.id
    raw_text = plain
    def _bg():
        bg_db = SessionLocal()
        try:
            bg_doc = bg_db.get(Document, doc_id)
            if bg_doc:
                run_pipeline(bg_db, bg_doc, raw_text)
        finally:
            bg_db.close()
    threading.Thread(target=_bg, daemon=True).start()

    return {"entry": _entry_row(entry), "document_id": doc.id}


@router.put("/{kb_id}/entries/{entry_id}")
def update_entry(kb_id: int, entry_id: int, body: EntryUpdate, db: Session = Depends(get_db)) -> dict:
    entry = db.get(KnowledgeEntry, entry_id)
    if not entry or entry.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="条目不存在")
    if body.title is not None:
        entry.title = body.title.strip()
    if body.body is not None:
        entry.body = body.body
    if body.summary is not None:
        entry.summary = _resolved_summary(body.summary, entry.body or "")
    if body.sort_order is not None:
        entry.sort_order = body.sort_order
    entry.updated_at = datetime.utcnow()
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
    db.commit()
    db.refresh(entry)
    return {"entry": _entry_row(entry)}


@router.delete("/{kb_id}/entries/{entry_id}")
def delete_entry(kb_id: int, entry_id: int, db: Session = Depends(get_db)) -> dict:
    entry = db.get(KnowledgeEntry, entry_id)
    if not entry or entry.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="条目不存在")
    delete_embeddings_for_knowledge_entries(db, [entry_id])
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.post("/{kb_id}/entries/batch-delete")
def batch_delete_entries(kb_id: int, body: EntryBatchDeleteBody, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    # Only delete entries that belong to this kb
    valid_ids = list(
        db.scalars(
            select(KnowledgeEntry.id).where(
                KnowledgeEntry.id.in_(body.entry_ids),
                KnowledgeEntry.knowledge_base_id == kb_id,
            )
        ).all()
    )
    if not valid_ids:
        return {"ok": True, "deleted": 0}
    delete_embeddings_for_knowledge_entries(db, valid_ids)
    db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(valid_ids)))
    db.commit()
    return {"ok": True, "deleted": len(valid_ids)}


@router.post("/{kb_id}/search")
def semantic_search(kb_id: int, body: SearchBody, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    hits = search_entries_hybrid(db, kb_id, body.query.strip(), top_k=body.top_k)
    return {"hits": hits}


# ---------------------------------------------------------------------------
# 文档流水线 API
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/documents")
def list_documents(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"documents": get_document_list(db, kb_id)}


@router.delete("/{kb_id}/documents/{doc_id}")
def remove_document(kb_id: int, doc_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    delete_document(db, doc_id)
    return {"ok": True}


@router.post("/{kb_id}/documents/{doc_id}/retry")
def retry_doc(kb_id: int, doc_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "failed":
        raise HTTPException(status_code=400, detail="只有失败的文档可以重试")
    if not doc.raw_text:
        raise HTTPException(status_code=400, detail="原始文本已丢失，无法重试")
    retry_document(db, doc_id)
    raw_text = doc.raw_text
    def _bg():
        bg_db = SessionLocal()
        try:
            bg_doc = bg_db.get(Document, doc_id)
            if bg_doc:
                run_pipeline(bg_db, bg_doc, raw_text)
        finally:
            bg_db.close()
    threading.Thread(target=_bg, daemon=True).start()
    return {"ok": True}


@router.get("/{kb_id}/documents/{doc_id}/chunks")
def list_chunks(kb_id: int, doc_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"chunks": get_document_chunks(db, doc_id)}
