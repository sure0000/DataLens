"""多接入大模型连接：CRUD 与 catalog / 调用侧解析。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import LlmConnection
from services.runtime_llm_config import get_semantic_llm_model_stored, set_semantic_llm_model


def connection_catalog_id(conn_id: str) -> str:
    return f"conn:{(conn_id or '').strip()}"


def is_connection_ref(ref: str) -> bool:
    s = (ref or "").strip().lower()
    return s.startswith("conn:") and len(s) > 5


def parse_connection_id(ref: str) -> str:
    return ref.split(":", 1)[1].strip()


def list_connections(db: Session) -> list[LlmConnection]:
    return list(db.scalars(select(LlmConnection).order_by(LlmConnection.created_at.asc())))


def get_connection(db: Session, conn_id: str) -> LlmConnection | None:
    return db.get(LlmConnection, (conn_id or "").strip())


def connection_to_public_dict(row: LlmConnection) -> dict[str, Any]:
    return {
        "id": row.id,
        "catalog_id": connection_catalog_id(row.id),
        "vendor_id": row.vendor_id,
        "vendor_label": row.vendor_label,
        "custom_name": row.custom_name,
        "base_url": (row.base_url or "").rstrip("/"),
        "provider": row.provider,
        "model_id": row.model_id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def create_connection(
    db: Session,
    *,
    vendor_id: str,
    vendor_label: str,
    custom_name: str,
    base_url: str,
    api_key: str,
    provider: str,
    model_id: str,
) -> LlmConnection:
    cid = uuid.uuid4().hex
    row = LlmConnection(
        id=cid,
        vendor_id=(vendor_id or "").strip(),
        vendor_label=(vendor_label or "").strip() or vendor_id,
        custom_name=(custom_name or "").strip() or "未命名",
        base_url=(base_url or "").strip().rstrip("/"),
        api_key=(api_key or "").strip(),
        provider=(provider or "").strip().lower(),
        model_id=(model_id or "").strip(),
    )
    if row.provider not in ("deepseek", "openai"):
        raise ValueError("provider 必须是 deepseek 或 openai")
    if not row.base_url or not row.api_key or not row.model_id:
        raise ValueError("base_url、api_key、model_id 不能为空")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_connection(db: Session, conn_id: str) -> bool:
    cid = (conn_id or "").strip()
    row = db.get(LlmConnection, cid)
    if not row:
        return False
    cat = connection_catalog_id(cid)
    stored = (get_semantic_llm_model_stored(db) or "").strip()
    db.delete(row)
    db.commit()
    if stored == cat:
        set_semantic_llm_model(db, "auto")
    return True
