"""全局 API 导入源：配置与导入分离，可在不同知识库间复用。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeApiSource
from services.source_cascade_cleanup import cleanup_api_source_in_kb, collect_api_source_kb_ids

router = APIRouter(prefix="/api/api-sources", tags=["api-sources"])


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
        "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
        "last_sync_status": s.last_sync_status,
        "last_error": s.last_error,
        "created_at": s.created_at.isoformat() if s.created_at else "",
        "updated_at": s.updated_at.isoformat() if s.updated_at else "",
    }


@router.get("")
def list_api_sources(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(KnowledgeApiSource)
        .where(KnowledgeApiSource.knowledge_base_id.is_(None))
        .order_by(KnowledgeApiSource.created_at.desc())
    ).scalars().all()
    return {"api_sources": [_source_row(r) for r in rows]}


@router.post("")
def create_api_source(body: ApiSourceCreate, db: Session = Depends(get_db)) -> dict:
    src = KnowledgeApiSource(
        knowledge_base_id=None,
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
def get_api_source(
    source_id: int,
    db: Session = Depends(get_db),
) -> dict:
    src = db.get(KnowledgeApiSource, source_id)
    if not src or src.knowledge_base_id is not None:
        raise HTTPException(status_code=404, detail="API 源不存在")
    return {"api_source": _source_row(src)}


@router.put("/{source_id}")
def update_api_source(source_id: int, body: ApiSourceUpdate, db: Session = Depends(get_db)) -> dict:
    src = db.get(KnowledgeApiSource, source_id)
    if not src or src.knowledge_base_id is not None:
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
    src.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(src)
    return {"api_source": _source_row(src)}


@router.delete("/{source_id}")
def delete_api_source(
    source_id: int,
    hard_delete: bool = Query(default=True, description="true=硬删导入源；false=软删（仅禁用）"),
    db: Session = Depends(get_db),
) -> dict:
    src = db.get(KnowledgeApiSource, source_id)
    if not src or src.knowledge_base_id is not None:
        raise HTTPException(status_code=404, detail="API 源不存在")
    kb_ids = collect_api_source_kb_ids(db, source_id, src)
    agg = {
        "entries_deleted": 0,
        "documents_deleted": 0,
        "evidence_packages_deleted": 0,
        "assertions_deleted": 0,
    }
    for kb_id in kb_ids:
        stats = cleanup_api_source_in_kb(db, kb_id=kb_id, source_id=source_id).to_dict()
        for key, val in stats.items():
            agg[key] += int(val)
    if hard_delete:
        db.delete(src)
    else:
        src.enabled = False
        src.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "hard_delete": bool(hard_delete), **agg}
