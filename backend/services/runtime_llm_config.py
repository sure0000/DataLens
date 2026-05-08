"""服务端可配置项：LLM 模型、API Base URL 与 Key（存 PostgreSQL，可覆盖环境变量）。"""

from sqlalchemy.orm import Session

from config import get_settings
from models import RuntimeSetting

SEMANTIC_MODEL_KEY = "semantic_llm_model"
KEY_DEEPSEEK_URL = "llm_deepseek_base_url"
KEY_DEEPSEEK_KEY = "llm_deepseek_api_key"
KEY_OPENAI_URL = "llm_openai_base_url"
KEY_OPENAI_KEY = "llm_openai_api_key"
KEY_DEEPSEEK_NAME = "llm_deepseek_connection_name"
KEY_OPENAI_NAME = "llm_openai_connection_name"

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _get_raw(db: Session | None, key: str) -> str | None:
    if db is None:
        return None
    row = db.get(RuntimeSetting, key)
    if not row:
        return None
    v = row.value
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _set_raw(db: Session, key: str, value: str | None) -> None:
    """value 为 None 表示不修改；空字符串表示删除覆盖。"""
    if value is None:
        return
    row = db.get(RuntimeSetting, key)
    if value.strip() == "":
        if row:
            db.delete(row)
        return
    v = value.strip()
    if row:
        row.value = v
    else:
        db.add(RuntimeSetting(key=key, value=v))


def get_effective_deepseek_api_key(db: Session | None) -> str | None:
    override = _get_raw(db, KEY_DEEPSEEK_KEY)
    if override:
        return override
    s = get_settings()
    k = (s.deepseek_api_key or "").strip()
    return k or None


def get_effective_deepseek_base_url(db: Session | None) -> str:
    override = _get_raw(db, KEY_DEEPSEEK_URL)
    if override:
        return override.rstrip("/")
    return DEFAULT_DEEPSEEK_BASE_URL.rstrip("/")


def get_effective_openai_api_key(db: Session | None) -> str | None:
    override = _get_raw(db, KEY_OPENAI_KEY)
    if override:
        return override
    s = get_settings()
    k = (s.openai_api_key or "").strip()
    return k or None


def get_stored_deepseek_connection_name(db: Session | None) -> str | None:
    return _get_raw(db, KEY_DEEPSEEK_NAME)


def get_stored_openai_connection_name(db: Session | None) -> str | None:
    return _get_raw(db, KEY_OPENAI_NAME)


def get_effective_openai_base_url(db: Session | None) -> str | None:
    """返回 None 时使用 OpenAI 官方 SDK 默认地址。"""
    override = _get_raw(db, KEY_OPENAI_URL)
    if override:
        return override.rstrip("/")
    s = get_settings()
    env_url = (s.openai_base_url or "").strip()
    return env_url.rstrip("/") if env_url else None


def get_semantic_llm_model_stored(db: Session) -> str | None:
    row = db.get(RuntimeSetting, SEMANTIC_MODEL_KEY)
    if not row or not (row.value or "").strip():
        return None
    return row.value.strip()


def set_semantic_llm_model(db: Session, value: str) -> None:
    v = (value or "").strip() or "auto"
    row = db.get(RuntimeSetting, SEMANTIC_MODEL_KEY)
    if row:
        row.value = v
    else:
        db.add(RuntimeSetting(key=SEMANTIC_MODEL_KEY, value=v))
    db.commit()


def get_llm_credentials_for_config_api(db: Session) -> dict:
    """GET /api/llm/config：可展示的 URL 与密钥是否已配置（不回传明文 Key）。"""
    ds_url = _get_raw(db, KEY_DEEPSEEK_URL) or ""
    oa_url = _get_raw(db, KEY_OPENAI_URL) or ""
    return {
        "deepseek_base_url": ds_url,
        "openai_base_url": oa_url,
        "deepseek_connection_name": _get_raw(db, KEY_DEEPSEEK_NAME) or "",
        "openai_connection_name": _get_raw(db, KEY_OPENAI_NAME) or "",
        "deepseek_api_key_configured": bool(_get_raw(db, KEY_DEEPSEEK_KEY) or (get_settings().deepseek_api_key or "").strip()),
        "openai_api_key_configured": bool(_get_raw(db, KEY_OPENAI_KEY) or (get_settings().openai_api_key or "").strip()),
        "deepseek_base_url_effective": get_effective_deepseek_base_url(db),
        "openai_base_url_effective": get_effective_openai_base_url(db) or "",
    }


def apply_llm_credential_updates(db: Session, updates: dict[str, str | None]) -> None:
    """
    updates 仅包含调用方显式传入的字段。
    - base_url / api_key 传空字符串：删除库内覆盖，回退环境变量或默认值。
    - api_key 不传（None）：不修改库内密钥项。
    """
    if "deepseek_base_url" in updates and updates["deepseek_base_url"] is not None:
        _set_raw(db, KEY_DEEPSEEK_URL, updates["deepseek_base_url"])
    if "openai_base_url" in updates and updates["openai_base_url"] is not None:
        _set_raw(db, KEY_OPENAI_URL, updates["openai_base_url"])
    if "deepseek_api_key" in updates and updates["deepseek_api_key"] is not None:
        _set_raw(db, KEY_DEEPSEEK_KEY, updates["deepseek_api_key"])
    if "openai_api_key" in updates and updates["openai_api_key"] is not None:
        _set_raw(db, KEY_OPENAI_KEY, updates["openai_api_key"])
    if "deepseek_connection_name" in updates and updates["deepseek_connection_name"] is not None:
        _set_raw(db, KEY_DEEPSEEK_NAME, updates["deepseek_connection_name"])
    if "openai_connection_name" in updates and updates["openai_connection_name"] is not None:
        _set_raw(db, KEY_OPENAI_NAME, updates["openai_connection_name"])
    db.commit()
