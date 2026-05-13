"""MCP 导入源：全局 CRUD、测试连接、市场模板、按 KB 导入。"""

from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import cast, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeBase, KnowledgeEntry, KnowledgeMcpSource
from services.embedding_service import delete_embeddings_for_knowledge_entries
from services.mcp_import import _trigger_background_import, test_mcp_connection_async

router = APIRouter(prefix="/api", tags=["knowledge-mcp-sources"])

_MARKETPLACE_PATH = os.path.join(os.path.dirname(__file__), "..", "services", "mcp_marketplace.json")


class McpSourceCreate(BaseModel):
    name: str
    mcp_transport: str = "stdio"
    mcp_command: str | None = None
    mcp_args: list[str] | None = None
    mcp_url: str | None = None
    mcp_env: dict[str, str] | None = None
    mcp_tool_name: str | None = None
    mcp_tool_args: dict | None = None
    content_mode: str = "markdown"
    max_entry_chars: int = 50000


class McpSourceUpdate(BaseModel):
    name: str | None = None
    mcp_transport: str | None = None
    mcp_command: str | None = None
    mcp_args: list[str] | None = None
    mcp_url: str | None = None
    mcp_env: dict[str, str] | None = None
    mcp_tool_name: str | None = None
    mcp_tool_args: dict | None = None
    content_mode: str | None = None
    max_entry_chars: int | None = None


class ImportFromMcpRequest(BaseModel):
    prompt: str | None = Field(default=None, max_length=2000)


def _get_kb(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


def _mcp_source_to_dict(r: KnowledgeMcpSource) -> dict:
    return {
        "id": r.id,
        "knowledge_base_id": r.knowledge_base_id,
        "name": r.name,
        "mcp_transport": r.mcp_transport,
        "mcp_command": r.mcp_command,
        "mcp_args": r.mcp_args,
        "mcp_url": r.mcp_url,
        "mcp_env": r.mcp_env,
        "mcp_tool_name": r.mcp_tool_name,
        "mcp_tool_args": r.mcp_tool_args,
        "content_mode": r.content_mode,
        "max_entry_chars": r.max_entry_chars,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_import_status": r.last_import_status,
        "last_import_error": r.last_import_error,
        "last_import_entries": r.last_import_entries,
        "last_import_at": r.last_import_at.isoformat() if r.last_import_at else None,
        "last_import_kb_id": r.last_import_kb_id,
    }


# ── 全局 CRUD ─────────────────────────────────────────────────────────────────

@router.get("/mcp-sources")
def list_mcp_sources(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(KnowledgeMcpSource).order_by(KnowledgeMcpSource.created_at.desc())
    ).scalars().all()
    return [_mcp_source_to_dict(r) for r in rows]


@router.post("/mcp-sources")
def create_mcp_source(body: McpSourceCreate, db: Session = Depends(get_db)) -> dict:
    if body.mcp_transport not in ("stdio", "http"):
        raise HTTPException(status_code=400, detail="mcp_transport 必须为 stdio 或 http")
    if body.mcp_transport == "stdio" and not (body.mcp_command or "").strip():
        raise HTTPException(status_code=400, detail="stdio 模式下 mcp_command 不能为空")
    if body.mcp_transport == "http" and not (body.mcp_url or "").strip():
        raise HTTPException(status_code=400, detail="http 模式下 mcp_url 不能为空")
    if body.content_mode not in ("markdown", "json_to_md"):
        raise HTTPException(status_code=400, detail="content_mode 必须为 markdown 或 json_to_md")

    src = KnowledgeMcpSource(
        name=body.name,
        mcp_transport=body.mcp_transport,
        mcp_command=body.mcp_command,
        mcp_args=body.mcp_args,
        mcp_url=body.mcp_url,
        mcp_env=body.mcp_env,
        mcp_tool_name=body.mcp_tool_name or None,
        mcp_tool_args=body.mcp_tool_args,
        content_mode=body.content_mode,
        max_entry_chars=body.max_entry_chars,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return {"id": src.id, "name": src.name}


@router.put("/mcp-sources/{source_id}")
def update_mcp_source(source_id: int, body: McpSourceUpdate, db: Session = Depends(get_db)) -> dict:
    src = db.get(KnowledgeMcpSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="MCP 源不存在")

    updates = body.model_dump(exclude_unset=True)
    if "mcp_transport" in updates and updates["mcp_transport"] not in ("stdio", "http"):
        raise HTTPException(status_code=400, detail="mcp_transport 必须为 stdio 或 http")
    if "content_mode" in updates and updates["content_mode"] not in ("markdown", "json_to_md"):
        raise HTTPException(status_code=400, detail="content_mode 必须为 markdown 或 json_to_md")

    for k, v in updates.items():
        setattr(src, k, v)
    src.updated_at = datetime.utcnow()
    db.commit()
    return {"id": src.id, "name": src.name}


@router.delete("/mcp-sources/{source_id}")
def delete_mcp_source(source_id: int, db: Session = Depends(get_db)) -> dict:
    src = db.get(KnowledgeMcpSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="MCP 源不存在")

    # 删除该源在所有 KB 中导入的条目
    old_ids = list(
        db.scalars(
            select(KnowledgeEntry.id).where(
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "mcp_import",
                cast(KnowledgeEntry.source_meta, JSONB)["mcp_source_id"].astext == str(source_id),
            )
        ).all()
    )
    delete_embeddings_for_knowledge_entries(db, old_ids)
    if old_ids:
        db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(old_ids)))

    db.delete(src)
    db.commit()
    return {"ok": True}


# ── 测试连接 ──────────────────────────────────────────────────────────────────

@router.post("/mcp-sources/{source_id}/test")
async def test_mcp_source(source_id: int, db: Session = Depends(get_db)) -> dict:
    src = db.get(KnowledgeMcpSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="MCP 源不存在")
    return await test_mcp_connection_async(src)


# ── 从 MCP 源导入到指定知识库 ─────────────────────────────────────────────────

@router.post("/knowledge-bases/{kb_id}/import-from-mcp/{source_id}")
def import_from_mcp(kb_id: int, source_id: int, body: ImportFromMcpRequest, db: Session = Depends(get_db)) -> dict:
    _get_kb(db, kb_id)
    src = db.get(KnowledgeMcpSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail="MCP 源不存在")

    _trigger_background_import(source_id, kb_id, prompt=body.prompt)
    return {"ok": True, "message": "MCP 导入已在后台启动，完成后条目会自动出现在知识库中"}


# ── 模板市场 ──────────────────────────────────────────────────────────────────

@router.get("/mcp-marketplace")
def get_mcp_marketplace() -> list[dict]:
    try:
        with open(_MARKETPLACE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
