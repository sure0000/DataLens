"""知识库 API：集合管理 + Markdown 条目 + 语义知识库流水线 + 混合检索。"""

import logging
import re
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import Document, KnowledgeBase, KnowledgeEntry
from services.business_domain_scope import resolve_scope_domain
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
from services.document_index_policy import MAX_AUTO_INDEX_ATTEMPTS, can_auto_retry_index, can_manual_index
from services.knowledge_pipeline_service import (
    create_document,
    delete_document,
    get_document_chunks,
    get_document_list,
    manual_index_document,
    retry_document,
    run_pipeline,
)
from services.retrieval_service import search_entries_hybrid

_logger = logging.getLogger(__name__)

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
    category: str = ""


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    category: str | None = None


class EntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = ""
    summary: str = Field(default="", max_length=2000)
    tags: list[str] | None = None


class EntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    summary: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None
    tags: list[str] | None = None


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
        "category": (kb.category or "").strip(),
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
        "tags": e.tags if isinstance(e.tags, list) else [],
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


def _get_scoped_kb(db: Session, kb_id: int, domain_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb or kb.business_domain_id != domain_id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@router.get("/categories")
def list_categories(request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    rows = db.execute(
        select(KnowledgeBase.category)
        .where(
            KnowledgeBase.business_domain_id == scope_domain.id,
            KnowledgeBase.category.isnot(None),
            KnowledgeBase.category != "",
        )
        .distinct()
        .order_by(KnowledgeBase.category)
    ).scalars().all()
    return {"categories": [r for r in rows if r]}


@router.get("")
def list_knowledge_bases(request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    rows = (
        db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.business_domain_id == scope_domain.id)
            .order_by(KnowledgeBase.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {"knowledge_bases": [_kb_row(r) for r in rows]}


@router.post("")
def create_knowledge_base(body: KnowledgeBaseCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    # 同名知识库检测
    existing = db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.name == body.name.strip(),
            KnowledgeBase.business_domain_id == scope_domain.id,
        )
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="同名的知识库已存在")
    kb = KnowledgeBase(
        name=body.name.strip(),
        description=body.description.strip() or None,
        category=body.category.strip() or None,
        business_domain_id=scope_domain.id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {"id": kb.id, **_kb_row(kb)}


@router.get("/{kb_id}")
def get_knowledge_base(kb_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    kb = _get_scoped_kb(db, kb_id, scope_domain.id)
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
def update_knowledge_base(kb_id: int, body: KnowledgeBaseUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    kb = _get_scoped_kb(db, kb_id, scope_domain.id)
    if body.name is not None:
        kb.name = body.name.strip()
    if body.description is not None:
        kb.description = body.description.strip() or None
    if body.category is not None:
        kb.category = body.category.strip() or None
    db.commit()
    db.refresh(kb)
    return {"knowledge_base": _kb_row(kb)}


@router.delete("/{kb_id}")
def delete_knowledge_base(kb_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    kb = _get_scoped_kb(db, kb_id, scope_domain.id)
    entry_ids = list(
        db.execute(select(KnowledgeEntry.id).where(KnowledgeEntry.knowledge_base_id == kb_id)).scalars().all()
    )
    delete_embeddings_for_knowledge_entries(db, entry_ids)
    # 使用 SQL DELETE + DB 级联，避免 ORM 加载 document_chunks（列未迁移时会报错）
    db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    db.commit()
    return {"ok": True}


@router.post("/{kb_id}/entries")
def create_entry(kb_id: int, body: EntryCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
    body_text = body.body or ""
    entry = create_entry_svc(
        db, kb_id, body.title, body_text,
        summary=body.summary,
        source_meta={"kind": "manual"},
    )
    db.flush()
    doc = create_document(
        db,
        kb_id,
        body.title,
        source_type="manual",
        source_meta={"kind": "manual"},
        knowledge_entry_id=entry.id,
    )
    db.commit()
    db.refresh(entry)
    if body_text.strip():
        doc_id = doc.id
        raw_text = body_text

        def _bg() -> None:
            bg_db = SessionLocal()
            try:
                bg_doc = bg_db.get(Document, doc_id)
                if bg_doc:
                    run_pipeline(bg_db, bg_doc, raw_text)
            finally:
                bg_db.close()

        threading.Thread(target=_bg, daemon=True).start()
    return {"entry": _entry_row(entry), "document_id": doc.id}


@router.post("/{kb_id}/entries/import-file")
async def import_entry_from_file(
    kb_id: int,
    request: Request,
    file: UploadFile = File(...),
    tags: str = Form(default=""),
    import_batch: str = Form(default=""),
    db: Session = Depends(get_db),
) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
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
    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags.strip() else []
    meta = {
        "kind": "file", "ref": fname, "label": fname,
        "tags": parsed_tags,
        "import_batch": import_batch.strip() or None,
    }

    # 同时创建 KnowledgeEntry（向后兼容）和 Document（新流水线）
    entry = create_entry_svc(db, kb_id, title, plain, source_meta=meta)
    if parsed_tags:
        entry.tags = parsed_tags
    db.commit()
    db.refresh(entry)

    doc = create_document(db, kb_id, title, source_type="file", source_meta=meta, knowledge_entry_id=entry.id)
    db.commit()

    try:
        from services.ingestion.connectors import register_evidence_from_import

        register_evidence_from_import(
            db,
            kb_id,
            title=title,
            route_key="import-file",
            source_ref={"entry_id": entry.id, "filename": fname, "document_id": doc.id},
            linked_entry_ids=[entry.id],
            linked_document_id=doc.id,
            processing_state="registered",
        )
    except Exception:
        _logger.warning("Evidence package registration failed for file import kb=%s", kb_id, exc_info=True)

    # 在后台线程运行流水线，不阻塞响应
    doc_id = doc.id
    raw_text = plain
    def _bg():
        bg_db = SessionLocal()
        try:
            bg_doc = bg_db.get(Document, doc_id)
            if bg_doc:
                run_pipeline(bg_db, bg_doc, raw_text)
        except Exception:
            _logger.exception("Background pipeline failed for doc=%d kb=%d", doc_id, kb_id)
            try:
                bg_doc = bg_db.get(Document, doc_id)
                if bg_doc and bg_doc.status == "pending":
                    bg_doc.status = "failed"
                    bg_doc.error_message = "后台流水线启动失败"
                    bg_db.commit()
            except Exception:
                _logger.exception("Failed to update doc status after pipeline failure doc=%d", doc_id)
                bg_db.rollback()
        finally:
            bg_db.close()
    threading.Thread(target=_bg, daemon=True).start()

    return {"entry": _entry_row(entry), "document_id": doc.id}


@router.put("/{kb_id}/entries/{entry_id}")
def update_entry(kb_id: int, entry_id: int, body: EntryUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
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
    if body.tags is not None:
        entry.tags = body.tags if isinstance(body.tags, list) else None
    entry.updated_at = datetime.utcnow()
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
    db.commit()
    db.refresh(entry)
    return {"entry": _entry_row(entry)}


@router.delete("/{kb_id}/entries/{entry_id}")
def delete_entry(kb_id: int, entry_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
    entry = db.get(KnowledgeEntry, entry_id)
    if not entry or entry.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="条目不存在")
    delete_embeddings_for_knowledge_entries(db, [entry_id])
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.post("/{kb_id}/entries/batch-delete")
def batch_delete_entries(kb_id: int, body: EntryBatchDeleteBody, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
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
def semantic_search(kb_id: int, body: SearchBody, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
    hits = search_entries_hybrid(db, kb_id, body.query.strip(), top_k=body.top_k)
    return {"hits": hits}


# ---------------------------------------------------------------------------
# 文档流水线 API
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/documents")
def list_documents(kb_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
    return {"documents": get_document_list(db, kb_id)}


class DocumentBatchDeleteBody(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=500)


@router.post("/{kb_id}/documents/batch-delete")
def batch_delete_documents(kb_id: int, body: DocumentBatchDeleteBody, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
    # Only delete documents that belong to this kb
    docs = db.execute(
        select(Document).where(
            Document.id.in_(body.document_ids),
            Document.knowledge_base_id == kb_id,
        )
    ).scalars().all()
    deleted = 0
    for doc in docs:
        delete_document(db, doc.id)
        deleted += 1
    return {"ok": True, "deleted": deleted}


@router.delete("/{kb_id}/documents/{doc_id}")
def remove_document(kb_id: int, doc_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    scope_domain = resolve_scope_domain(db, request)
    _get_scoped_kb(db, kb_id, scope_domain.id)
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    delete_document(db, doc_id)
    return {"ok": True}


def _start_document_pipeline_background(doc_id: int, raw_text: str, *, log_label: str) -> None:
    def _bg():
        bg_db = SessionLocal()
        try:
            bg_doc = bg_db.get(Document, doc_id)
            if bg_doc:
                run_pipeline(bg_db, bg_doc, raw_text)
        except Exception:
            _logger.exception("%s pipeline failed for doc=%d", log_label, doc_id)
        finally:
            bg_db.close()

    threading.Thread(target=_bg, daemon=True, name=f"doc-pipeline-{doc_id}").start()


@router.post("/{kb_id}/documents/{doc_id}/retry")
def retry_doc(kb_id: int, doc_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status not in ("failed", "pending"):
        raise HTTPException(status_code=400, detail="只有失败或等待中的文档可以重试索引")
    if not doc.raw_text:
        raise HTTPException(status_code=400, detail="原始文本已丢失，无法重试")
    if not can_auto_retry_index(doc):
        raise HTTPException(
            status_code=400,
            detail=(
                f"已自动重试 {int(doc.index_attempts or 0)} 次仍未成功，"
                f"请使用「手动索引」（上限 {MAX_AUTO_INDEX_ATTEMPTS} 次自动重试）"
            ),
        )
    updated = retry_document(db, doc_id)
    if not updated:
        raise HTTPException(status_code=400, detail="无法重试该文档")
    _start_document_pipeline_background(doc_id, doc.raw_text, log_label="Document retry")
    return {"ok": True}


@router.post("/{kb_id}/documents/{doc_id}/manual-index")
def manual_index_doc(kb_id: int, doc_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "failed":
        raise HTTPException(status_code=400, detail="只有失败的文档可以手动索引")
    if not doc.raw_text:
        raise HTTPException(status_code=400, detail="原始文本已丢失，无法手动索引")
    if not can_manual_index(doc):
        raise HTTPException(status_code=400, detail="当前状态不允许手动索引")
    updated = manual_index_document(db, doc_id)
    if not updated:
        raise HTTPException(status_code=400, detail="无法手动索引该文档")
    _start_document_pipeline_background(doc_id, doc.raw_text, log_label="Document manual index")
    return {"ok": True, "index_attempts": int(doc.index_attempts or 0)}


@router.get("/{kb_id}/documents/{doc_id}/chunks")
def list_chunks(kb_id: int, doc_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"chunks": get_document_chunks(db, doc_id)}
