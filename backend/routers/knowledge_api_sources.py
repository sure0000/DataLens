"""知识库官方 API 导入源：配置与导入分离。"""

import logging
import threading
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Document, KnowledgeApiSource, KnowledgeBase, KnowledgeEntry
from services.entry_service import create_entry as create_entry_svc
from services.import_log_service import complete_import, start_import
from services.knowledge_ingest import (
    fetch_official_confluence_page,
    fetch_official_feishu_doc,
    fetch_official_notion_database,
    fetch_official_notion_page,
)
from services.source_cascade_cleanup import cleanup_api_source_in_kb

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-bases/{kb_id}/api-sources", tags=["knowledge-api-sources"])


class ApiSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    integration: str = Field(..., description="notion | confluence | feishu")
    api_key: str = Field(default="", max_length=4000)
    object_id: str = Field(default="", max_length=2000)
    extra: dict[str, str] | None = None

    @field_validator("integration")
    @classmethod
    def _validate_integration(cls, v: str) -> str:
        key = (v or "").strip().lower()
        if key not in {"notion", "confluence", "feishu"}:
            raise ValueError("integration 目前支持：notion, confluence, feishu")
        return key


class ApiSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=4000)
    object_id: str | None = Field(default=None, max_length=2000)
    extra: dict[str, str] | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


def _integration_kind(integration: str) -> str:
    return f"{(integration or '').strip().lower()}_api"


def _entry_meta_for_source(
    src: KnowledgeApiSource,
    ref: str,
    *,
    label: str | None = None,
    tags: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "kind": _integration_kind(src.integration),
        "ref": ref,
        "api_source_id": str(src.id),
        "label": label or f"{src.integration} 官方 API",
    }
    if tags:
        meta["tags"] = tags
    meta.update(extra)
    return meta


def _document_meta_for_source(src: KnowledgeApiSource, ref: str) -> dict[str, Any]:
    return {
        "kind": _integration_kind(src.integration),
        "ref": ref,
        "api_source_id": str(src.id),
        "label": "API 导入",
    }


def _entries_for_api_source(db: Session, kb_id: int, src: KnowledgeApiSource) -> list[KnowledgeEntry]:
    kind = _integration_kind(src.integration)
    oid = (src.object_id or "").strip()
    rows = db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.knowledge_base_id == kb_id)
    ).scalars().all()
    matched: list[KnowledgeEntry] = []
    for entry in rows:
        meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
        if meta.get("kind") != kind:
            continue
        if str(meta.get("api_source_id") or "") == str(src.id):
            matched.append(entry)
            continue
        if oid and str(meta.get("ref") or "") == oid:
            matched.append(entry)
            continue
        if not oid and not meta.get("api_source_id"):
            matched.append(entry)
    return matched


def _resolve_object_id(db: Session, kb_id: int, src: KnowledgeApiSource, requested: str) -> str:
    oid = (requested or "").strip() or (src.object_id or "").strip()
    if oid:
        return oid
    for entry in _entries_for_api_source(db, kb_id, src):
        meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
        ref = str(meta.get("ref") or "").strip()
        if ref:
            return ref
    return ""


def _spawn_document_pipelines(
    kb_id: int,
    src: KnowledgeApiSource,
    object_id: str,
    items: list[dict[str, Any]],
    *,
    integration: str,
) -> None:
    if not items:
        return

    def _bg() -> None:
        from database import SessionLocal
        from services.knowledge_pipeline_service import create_document, run_pipeline

        bg_db = SessionLocal()
        try:
            for item in items:
                doc = create_document(
                    bg_db,
                    kb_id,
                    item["title"],
                    source_type="api",
                    source_meta=_document_meta_for_source(src, object_id),
                    knowledge_entry_id=item["entry_id"],
                )
                bg_db.commit()
                bg_doc = bg_db.get(Document, doc.id)
                if bg_doc:
                    run_pipeline(bg_db, bg_doc, item["text"])
        except Exception:
            _logger.exception("Background API-import pipeline failed for kb=%d", kb_id)
        finally:
            bg_db.close()

    threading.Thread(target=_bg, daemon=True).start()


def _source_row(s: KnowledgeApiSource) -> dict:
    return {
        "id": s.id,
        "knowledge_base_id": s.knowledge_base_id,
        "name": s.name,
        "integration": s.integration,
        "object_id": s.object_id,
        "extra": s.extra if isinstance(s.extra, dict) else {},
        "has_key": bool((s.api_key or "").strip()),
        "enabled": s.enabled,
        "tags": s.tags if isinstance(s.tags, list) else [],
        "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
        "last_sync_status": s.last_sync_status,
        "last_error": s.last_error,
        "created_at": s.created_at.isoformat() if s.created_at else "",
        "updated_at": s.updated_at.isoformat() if s.updated_at else "",
    }


@router.get("")
def list_api_sources(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    rows = db.execute(
        select(KnowledgeApiSource)
        .where(KnowledgeApiSource.knowledge_base_id == kb_id)
        .order_by(KnowledgeApiSource.created_at.desc())
    ).scalars().all()
    return {"api_sources": [_source_row(r) for r in rows]}


@router.post("")
def create_api_source(kb_id: int, body: ApiSourceCreate, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    src = KnowledgeApiSource(
        knowledge_base_id=kb_id,
        name=body.name.strip(),
        integration=body.integration,
        api_key=body.api_key.strip(),
        object_id=body.object_id.strip() if body.object_id else "",
        extra=body.extra or {},
        updated_at=datetime.utcnow(),
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return {"api_source": _source_row(src)}


@router.get("/{source_id}")
def get_api_source(kb_id: int, source_id: int, db: Session = Depends(get_db)) -> dict:
    src = db.get(KnowledgeApiSource, source_id)
    if not src or src.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="API 源不存在")
    return {"api_source": _source_row(src)}


@router.put("/{source_id}")
def update_api_source(kb_id: int, source_id: int, body: ApiSourceUpdate, db: Session = Depends(get_db)) -> dict:
    src = db.get(KnowledgeApiSource, source_id)
    if not src or src.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="API 源不存在")
    if body.name is not None:
        src.name = body.name.strip()
    if body.api_key is not None:
        src.api_key = body.api_key.strip()
    if body.object_id is not None:
        src.object_id = body.object_id.strip()
    if body.extra is not None:
        src.extra = body.extra
    if body.enabled is not None:
        src.enabled = body.enabled
    if body.tags is not None:
        src.tags = body.tags if isinstance(body.tags, list) else None
    src.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(src)
    return {"api_source": _source_row(src)}


@router.delete("/{source_id}")
def delete_api_source(
    kb_id: int,
    source_id: int,
    hard_delete: bool = Query(default=True, description="true=硬删导入源；false=软删（仅禁用）"),
    db: Session = Depends(get_db),
) -> dict:
    src = db.get(KnowledgeApiSource, source_id)
    if not src or src.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="API 源不存在")
    stats = cleanup_api_source_in_kb(db, kb_id=kb_id, source_id=source_id)
    if hard_delete:
        db.delete(src)
    else:
        src.enabled = False
        src.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "hard_delete": bool(hard_delete), **stats.to_dict()}


class ImportRequest(BaseModel):
    object_id: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list)


@router.post("/{source_id}/import")
def import_from_api_source(kb_id: int, source_id: int, body: ImportRequest = ImportRequest(), db: Session = Depends(get_db)) -> dict:
    """从已配置的 API 源触发一次导入（支持全局源和 KB 绑定源）。可传入 object_id 覆盖源配置。"""
    src = db.get(KnowledgeApiSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="API 源不存在")
    if src.knowledge_base_id is not None and src.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="API 源不属于该知识库")

    object_id = _resolve_object_id(db, kb_id, src, body.object_id or "")
    if not object_id:
        raise HTTPException(
            status_code=400,
            detail="请提供要导入的对象 ID（页面、文档或数据库），或在设置中填写 object_id",
        )

    log = start_import(db, kb_id, src.integration + "_api", source_id=src.id, source_name=src.name)

    _created: list[dict] = []

    def _add_entry(kb_id: int, title: str, text: str, **kw: Any) -> None:
        sm = kw.pop("source_meta", None)
        if sm is None:
            sm = _entry_meta_for_source(src, object_id, tags=body.tags)
        elif isinstance(sm, dict):
            sm = {**sm, "api_source_id": str(src.id)}
        entry = create_entry_svc(db, kb_id, title, text, source_meta=sm, **kw)
        _created.append({"entry_id": entry.id, "title": title, "text": text})

    try:
        entries_created = 0
        integration = src.integration
        api_key = src.api_key
        extra = src.extra if isinstance(src.extra, dict) else {}

        if integration == "notion":
            if len(api_key) < 10:
                raise ValueError("请填写有效的 Notion Integration Token")
            try:
                title_hint, text = fetch_official_notion_page(api_key, object_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 404):
                    pages = fetch_official_notion_database(api_key, object_id)
                    if not pages:
                        raise ValueError("该对象既不是可访问的 Page，也不是可查询的 Database")
                    for idx, (t, txt) in enumerate(pages):
                        _add_entry(
                            kb_id,
                            t or f"Notion Database 页面 {idx + 1}",
                            txt,
                            source_meta=_entry_meta_for_source(
                                src, object_id, label="Notion 官方 API（Database）", tags=body.tags
                            ),
                        )
                        entries_created += 1
                    db.commit()
                    complete_import(db, log, entries_created=entries_created)
                    try:
                        from services.ingestion.connectors import register_evidence_from_import

                        register_evidence_from_import(
                            db,
                            kb_id,
                            title=f"Notion Database · {src.name}",
                            route_key="api-sources/import",
                            source_kind="notion",
                            source_ref={"source_id": src.id, "object_id": object_id},
                            linked_entry_ids=[item["entry_id"] for item in _created],
                            processing_state="registered",
                        )
                    except Exception:
                        pass
                    db.commit()
                    _spawn_document_pipelines(kb_id, src, object_id, _created, integration=integration)
                    return {"ok": True, "entries_created": entries_created, "mode": "database"}
                raise
            _add_entry(
                kb_id,
                title_hint or object_id[:80],
                text,
                source_meta=_entry_meta_for_source(src, object_id, tags=body.tags),
            )
            entries_created = 1

        elif integration == "confluence":
            email = (extra.get("email") or "").strip()
            domain = (extra.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
            if not email or not domain:
                raise ValueError("Confluence 请在 extra 中填写 email 与 domain")
            if not api_key:
                raise ValueError("请填写 Confluence API Token")
            title_hint, text = fetch_official_confluence_page(domain, email, api_key, object_id)
            src_url = f"https://{domain}/wiki/pages/viewpage.action?pageId={object_id.strip()}"
            _add_entry(
                kb_id,
                title_hint,
                text,
                source_meta=_entry_meta_for_source(src, object_id, label="Confluence 官方 API", tags=body.tags),
                source_url=src_url,
            )
            entries_created = 1

        elif integration == "feishu":
            app_id = (extra.get("app_id") or "").strip()
            if not app_id:
                raise ValueError("飞书请在 extra 中填写 app_id；app_secret 填入 api_key")
            if not api_key:
                raise ValueError("请填写飞书应用 app_secret")
            title_hint, text = fetch_official_feishu_doc(app_id, api_key, object_id)
            _add_entry(
                kb_id,
                title_hint,
                text,
                source_meta=_entry_meta_for_source(
                    src, object_id[:500], label="飞书官方 API", tags=body.tags
                ),
            )
            entries_created = 1

        else:
            raise ValueError(f"不支持的 integration：{integration}")

        db.commit()
        src.last_sync_at = datetime.utcnow()
        src.last_sync_status = "success"
        src.last_error = None
        src.updated_at = datetime.utcnow()
        db.commit()

        complete_import(db, log, entries_created=entries_created)
        db.commit()

        try:
            from services.ingestion.connectors import register_evidence_from_import

            register_evidence_from_import(
                db,
                kb_id,
                title=f"API 导入 · {src.name}",
                route_key="api-sources/import",
                source_kind=integration,
                source_ref={"source_id": src.id, "object_id": object_id, "entries": entries_created},
                linked_entry_ids=[item["entry_id"] for item in _created],
                processing_state="registered",
            )
        except Exception:
            pass

        _spawn_document_pipelines(kb_id, src, object_id, _created, integration=integration)

        return {"ok": True, "entries_created": entries_created}

    except httpx.HTTPStatusError as exc:
        db.rollback()
        complete_import(db, log, error_message=f"官方 API 调用失败：{exc}")
        db.commit()
        raise HTTPException(status_code=502, detail=f"官方 API 调用失败：{exc}") from exc
    except httpx.RequestError as exc:
        from services.httpx_env import format_http_request_error

        db.rollback()
        msg = format_http_request_error(exc)
        complete_import(db, log, error_message=msg)
        db.commit()
        raise HTTPException(status_code=502, detail=msg) from exc
    except Exception as exc:
        db.rollback()
        complete_import(db, log, error_message=str(exc))
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{source_id}/reindex-entries")
def reindex_api_source_entries(kb_id: int, source_id: int, db: Session = Depends(get_db)) -> dict:
    """为已导入但缺少 Document/分块的条目重建文档索引（不重新拉取 Notion 等 API）。"""
    src = db.get(KnowledgeApiSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="API 源不存在")
    if src.knowledge_base_id is not None and src.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="API 源不属于该知识库")

    entries = _entries_for_api_source(db, kb_id, src)
    if not entries:
        raise HTTPException(status_code=404, detail="未找到与该 API 源关联的知识条目")

    ref = _resolve_object_id(db, kb_id, src, "")
    items: list[dict[str, Any]] = []
    skipped = 0
    for entry in entries:
        body = (entry.body or "").strip()
        if not body:
            skipped += 1
            continue
        existing = db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id == entry.id,
                Document.status.in_(("pending", "extracting", "cleaning", "chunking", "embedding", "ontology_assertion", "indexed")),
            )
        ).scalars().first()
        if existing:
            skipped += 1
            continue
        items.append({"entry_id": entry.id, "title": entry.title or "导入条目", "text": body})

    if not items:
        return {
            "ok": True,
            "queued": 0,
            "skipped": skipped,
            "message": "关联条目均已存在进行中的文档，或正文为空",
        }

    object_id = ref or (src.object_id or "").strip() or "reindex"
    _spawn_document_pipelines(kb_id, src, object_id, items, integration=src.integration)
    return {"ok": True, "queued": len(items), "skipped": skipped}
