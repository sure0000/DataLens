from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
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
