from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.llm_connections import connection_to_public_dict, create_connection, delete_connection, get_connection, list_connections
from services.llm_models import catalog_models, is_allowed_semantic_value, resolve_auto_model, resolve_effective_model
from services.runtime_llm_config import (
    apply_llm_credential_updates,
    get_llm_credentials_for_config_api,
    get_semantic_llm_model_stored,
    set_semantic_llm_model,
)

router = APIRouter(prefix="/api", tags=["llm-settings"])


class LlmConfigBody(BaseModel):
    """字段为 None 表示不修改；空字符串表示清除库内覆盖（URL/Key 回退默认或环境变量）。"""

    semantic_llm_model: str | None = Field(default=None, description="auto 或 provider:model")
    deepseek_base_url: str | None = None
    deepseek_api_key: str | None = None
    deepseek_connection_name: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_connection_name: str | None = None


class LlmConnectionCreateBody(BaseModel):
    vendor_id: str = Field(..., min_length=1)
    vendor_label: str = Field(default="", description="厂商展示名，可空则使用 vendor_id")
    custom_name: str = Field(default="", description="自定义接入名称")
    base_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    provider: str = Field(..., description="deepseek 或 openai（兼容通道）")
    model_id: str = Field(..., min_length=1)


@router.get("/llm/connections")
def llm_connections_list(db: Session = Depends(get_db)) -> dict:
    return {"connections": [connection_to_public_dict(r) for r in list_connections(db)]}


@router.post("/llm/connections")
def llm_connections_create(body: LlmConnectionCreateBody, db: Session = Depends(get_db)) -> dict:
    try:
        row = create_connection(
            db,
            vendor_id=body.vendor_id,
            vendor_label=body.vendor_label or body.vendor_id,
            custom_name=body.custom_name,
            base_url=body.base_url,
            api_key=body.api_key,
            provider=body.provider,
            model_id=body.model_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return connection_to_public_dict(row)


@router.get("/llm/connections/{conn_id}")
def llm_connections_get(
    conn_id: str,
    db: Session = Depends(get_db),
) -> dict:
    row = get_connection(db, conn_id)
    if not row:
        raise HTTPException(status_code=404, detail="接入不存在")
    out: dict = {
        **connection_to_public_dict(row),
        "api_key_configured": bool((row.api_key or "").strip()),
    }
    return out


@router.delete("/llm/connections/{conn_id}")
def llm_connections_delete(conn_id: str, db: Session = Depends(get_db)) -> dict:
    if not delete_connection(db, conn_id):
        raise HTTPException(status_code=404, detail="接入不存在")
    cat = catalog_models(db)
    stored = get_semantic_llm_model_stored(db)
    display = stored if stored else "auto"
    resolved = resolve_effective_model(stored, db) if cat["has_llm"] else ""
    return {"ok": True, "semantic_llm_model": display, "semantic_llm_model_resolved": resolved, "catalog": cat}


@router.get("/llm/catalog")
def llm_catalog(db: Session = Depends(get_db)) -> dict:
    return catalog_models(db)


@router.get("/llm/config")
def get_llm_config(db: Session = Depends(get_db)) -> dict:
    stored = get_semantic_llm_model_stored(db)
    display = stored if stored else "auto"
    cat = catalog_models(db)
    resolved = resolve_effective_model(stored, db) if cat["has_llm"] else ""
    return {
        "semantic_llm_model": display,
        "semantic_llm_model_resolved": resolved,
        **get_llm_credentials_for_config_api(db),
    }


@router.put("/llm/config")
def put_llm_config(body: LlmConfigBody, db: Session = Depends(get_db)) -> dict:
    cred_updates: dict[str, str | None] = {}
    if body.deepseek_base_url is not None:
        cred_updates["deepseek_base_url"] = body.deepseek_base_url
    if body.deepseek_api_key is not None:
        cred_updates["deepseek_api_key"] = body.deepseek_api_key
    if body.openai_base_url is not None:
        cred_updates["openai_base_url"] = body.openai_base_url
    if body.openai_api_key is not None:
        cred_updates["openai_api_key"] = body.openai_api_key
    if body.deepseek_connection_name is not None:
        cred_updates["deepseek_connection_name"] = body.deepseek_connection_name
    if body.openai_connection_name is not None:
        cred_updates["openai_connection_name"] = body.openai_connection_name
    if cred_updates:
        apply_llm_credential_updates(db, cred_updates)

    if body.semantic_llm_model is not None:
        raw = (body.semantic_llm_model or "").strip() or "auto"
        if not is_allowed_semantic_value(raw, db):
            raise HTTPException(
                status_code=400,
                detail="无效的 semantic_llm_model：请选择 catalog 中已启用 Key 的模型，或使用 auto",
            )
        set_semantic_llm_model(db, raw)

    cat = catalog_models(db)
    stored = get_semantic_llm_model_stored(db)
    display = stored if stored else "auto"
    resolved = resolve_effective_model(stored, db) if cat["has_llm"] else ""
    return {
        "semantic_llm_model": display,
        "semantic_llm_model_resolved": resolved,
        "auto_default": resolve_auto_model(db),
        **get_llm_credentials_for_config_api(db),
    }
