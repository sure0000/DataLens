"""知识库 API：集合管理 + Markdown 条目 + 向量语义检索（复用 embeddings 表）。"""

import re
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeBase, KnowledgeEntry
from services.embedding_service import (
    KNOWLEDGE_EMBEDDING_REF,
    delete_embeddings_for_knowledge_entries,
    replace_knowledge_entry_embedding,
    search_knowledge_semantic,
)
from services.knowledge_ingest import (
    MAX_INGEST_BYTES,
    fetch_official_confluence_page,
    fetch_official_feishu_doc,
    fetch_official_notion_database,
    fetch_official_notion_page,
    fetch_official_obsidian_publish_page,
    fetch_url_body,
    file_to_plain,
    normalize_filename,
    title_from_filename,
)

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


class ImportUrlBody(BaseModel):
    """从可匿名访问的 **普通网页**（http(s)）抓取正文，剥离 HTML 为纯文本。"""

    url: str = Field(..., min_length=4, max_length=2000)
    title: str | None = Field(default=None, max_length=500)


class ImportOfficialBody(BaseModel):
    """使用各平台官方（或标准开放）接口导入内容。"""

    integration: str = Field(..., description="notion | confluence | obsidian | feishu")
    api_key: str = Field(default="", max_length=4000, description="Token / Secret；Obsidian Publish 可留空")
    object_id: str = Field(..., min_length=1, max_length=2000, description="页面/文档 ID 或 Obsidian Publish 完整 URL")
    title: str | None = Field(default=None, max_length=500)
    extra: dict[str, str] | None = Field(
        default=None,
        description="Confluence: email, domain；飞书: app_id（app_secret 填在 api_key）",
    )

    @field_validator("integration")
    @classmethod
    def _validate_official_integration(cls, v: str) -> str:
        key = (v or "").strip().lower()
        if key not in {"notion", "confluence", "obsidian", "feishu"}:
            raise ValueError("integration 目前支持：notion, confluence, obsidian, feishu")
        return key


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


def _import_append_entry(
    db: Session,
    kb_id: int,
    title: str,
    body: str,
    source_meta: dict[str, str],
    source_url: str | None = None,
) -> dict:
    max_order = db.execute(
        select(KnowledgeEntry.sort_order)
        .where(KnowledgeEntry.knowledge_base_id == kb_id)
        .order_by(KnowledgeEntry.sort_order.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1
    excerpt = _plain_excerpt(body)
    entry = KnowledgeEntry(
        knowledge_base_id=kb_id,
        title=(title or "未命名").strip()[:500],
        summary=excerpt,
        body=body,
        sort_order=next_order,
        source_url=(source_url or "").strip() or None,
        source_meta=source_meta,
        updated_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
    db.commit()
    db.refresh(entry)
    return _entry_row(entry)


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
    max_order = db.execute(
        select(KnowledgeEntry.sort_order).where(KnowledgeEntry.knowledge_base_id == kb_id).order_by(KnowledgeEntry.sort_order.desc()).limit(1)
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1
    summarised = _resolved_summary(body.summary, body.body or "")
    entry = KnowledgeEntry(
        knowledge_base_id=kb_id,
        title=body.title.strip(),
        summary=summarised,
        body=body.body or "",
        sort_order=next_order,
        source_meta={"kind": "manual"},
        updated_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
    db.commit()
    db.refresh(entry)
    return {"entry": _entry_row(entry)}


@router.post("/{kb_id}/entries/import-url")
def import_entry_from_url(kb_id: int, body: ImportUrlBody, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    try:
        title_hint, text = fetch_url_body(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"链接抓取失败：{exc}") from exc
    title = (body.title or title_hint or "").strip() or body.url.strip()[:200]
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="未能提取正文。若页面需登录或非公开分享，请先导出后用「上传文件」或手动条目粘贴。",
        )
    meta: dict[str, str] = {
        "kind": "web",
        "ref": body.url.strip(),
        "label": "网页链接",
    }
    max_order = db.execute(
        select(KnowledgeEntry.sort_order).where(KnowledgeEntry.knowledge_base_id == kb_id).order_by(KnowledgeEntry.sort_order.desc()).limit(1)
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1
    excerpt = _plain_excerpt(text)
    entry = KnowledgeEntry(
        knowledge_base_id=kb_id,
        title=title,
        summary=excerpt,
        body=text,
        sort_order=next_order,
        source_url=body.url.strip(),
        source_meta=meta,
        updated_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
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
        text = file_to_plain(fname, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail="文件解析结果为空")
    title = title_from_filename(fname)
    meta = {"kind": "file", "ref": fname, "label": "上传文件"}
    max_order = db.execute(
        select(KnowledgeEntry.sort_order).where(KnowledgeEntry.knowledge_base_id == kb_id).order_by(KnowledgeEntry.sort_order.desc()).limit(1)
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1
    excerpt = _plain_excerpt(text)
    entry = KnowledgeEntry(
        knowledge_base_id=kb_id,
        title=title,
        summary=excerpt,
        body=text,
        sort_order=next_order,
        source_meta=meta,
        updated_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
    db.commit()
    db.refresh(entry)
    return {"entry": _entry_row(entry)}


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
    hits = search_knowledge_semantic(db, kb_id, body.query.strip(), top_k=body.top_k)
    return {"hits": hits, "ref_type": KNOWLEDGE_EMBEDDING_REF}


@router.post("/{kb_id}/entries/import-official")
def import_entry_from_official_api(kb_id: int, body: ImportOfficialBody, db: Session = Depends(get_db)) -> dict:
    """
    官方 / 标准开放接口导入：Notion、Confluence Cloud、飞书云文档、Obsidian Publish。
    """
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    integration = body.integration
    api_key = (body.api_key or "").strip()
    object_id = body.object_id.strip()
    extra = body.extra or {}

    entries_created: list[dict] = []

    try:
        if integration == "notion":
            if len(api_key) < 10:
                raise ValueError("请填写有效的 Notion Integration Token（api_key）")
            try:
                title_hint, text = fetch_official_notion_page(api_key, object_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    pages = fetch_official_notion_database(api_key, object_id)
                    if not pages:
                        raise ValueError("该对象既不是可访问的 Page，也不是可查询的 Database")
                    for idx, (t, txt) in enumerate(pages):
                        row = _import_append_entry(
                            db,
                            kb_id,
                            (body.title or t or f"Notion Database 页面 {idx + 1}").strip()[:500],
                            txt,
                            {
                                "kind": "notion_api",
                                "ref": object_id,
                                "label": "Notion 官方 API（Database）",
                            },
                        )
                        entries_created.append(row)
                    return {"entries": entries_created, "mode": "database"}
                raise
            row = _import_append_entry(
                db,
                kb_id,
                (body.title or title_hint or object_id[:80]).strip()[:500],
                text,
                {"kind": "notion_api", "ref": object_id, "label": "Notion 官方 API"},
            )
            return {"entry": row, "mode": "page"}

        if integration == "confluence":
            email = (extra.get("email") or "").strip()
            domain = (extra.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
            if not email or not domain:
                raise ValueError(
                    "Confluence 请在请求体 extra 中填写 email（Atlassian 账号邮箱）与 domain（如 yourcompany.atlassian.net）"
                )
            if not api_key:
                raise ValueError("请填写 Confluence API Token（填入 api_key 字段）")
            title_hint, text = fetch_official_confluence_page(domain, email, api_key, object_id)
            src_url = f"https://{domain}/wiki/pages/viewpage.action?pageId={object_id.strip()}"
            row = _import_append_entry(
                db,
                kb_id,
                (body.title or title_hint).strip()[:500],
                text,
                {"kind": "confluence_api", "ref": object_id, "label": "Confluence 官方 API"},
                source_url=src_url,
            )
            return {"entry": row, "mode": "page"}

        if integration == "feishu":
            app_id = (extra.get("app_id") or "").strip()
            if not app_id:
                raise ValueError("飞书请在 extra 中填写 app_id；应用密钥 app_secret 请填入 api_key 字段")
            if not api_key:
                raise ValueError("请填写飞书应用 app_secret（api_key）")
            title_hint, text = fetch_official_feishu_doc(app_id, api_key, object_id)
            row = _import_append_entry(
                db,
                kb_id,
                (body.title or title_hint).strip()[:500],
                text,
                {"kind": "feishu_api", "ref": object_id[:500], "label": "飞书官方 API"},
            )
            return {"entry": row, "mode": "doc"}

        if integration == "obsidian":
            title_hint, text = fetch_official_obsidian_publish_page(object_id)
            row = _import_append_entry(
                db,
                kb_id,
                (body.title or title_hint or "Obsidian Publish").strip()[:500],
                text,
                {"kind": "obsidian_publish", "ref": object_id[:2000], "label": "Obsidian Publish"},
                source_url=object_id.strip(),
            )
            return {"entry": row, "mode": "publish"}

        raise HTTPException(status_code=400, detail=f"不支持的 integration：{integration}")

    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"官方 API 调用失败：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
