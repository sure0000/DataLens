"""模型 ID 解析、可用性校验与「自动」解析（与具体 HTTP 调用解耦）。"""

from sqlalchemy.orm import Session

from services.llm_connections import (
    connection_catalog_id,
    get_connection,
    is_connection_ref,
    list_connections,
    parse_connection_id,
)
from services.runtime_llm_config import (
    get_effective_deepseek_api_key,
    get_effective_openai_api_key,
    get_stored_deepseek_connection_name,
    get_stored_openai_connection_name,
)

# 与 https://api-docs.deepseek.com/ 所列 model 名一致
DEEPSEEK_CATALOG_ROWS: tuple[tuple[str, str, str], ...] = (
    ("deepseek-v4-flash", "V4 Flash", "v4"),
    ("deepseek-v4-pro", "V4 Pro", "v4"),
    ("deepseek-chat", "Chat（兼容别名）", "chat"),
    ("deepseek-reasoner", "Reasoner（兼容别名）", "chat"),
)


def _deepseek_catalog_tail(api_id: str) -> str:
    for mid, short, _fam in DEEPSEEK_CATALOG_ROWS:
        if mid == api_id:
            return f"{short} · {mid}"
    return api_id


def parse_model_ref(ref: str) -> tuple[str, str]:
    ref = (ref or "").strip()
    if ":" not in ref:
        raise ValueError(f"无效的模型引用: {ref!r}，应为 provider:model")
    provider, model = ref.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        raise ValueError(f"无效的模型引用: {ref!r}")
    if provider not in ("deepseek", "openai"):
        raise ValueError(f"不支持的 provider: {provider}")
    return provider, model


def provider_has_key(provider: str, db: Session | None = None) -> bool:
    if provider == "deepseek":
        return bool(get_effective_deepseek_api_key(db))
    if provider == "openai":
        return bool(get_effective_openai_api_key(db))
    return False


def _has_legacy_llm_key(db: Session | None = None) -> bool:
    return provider_has_key("deepseek", db) or provider_has_key("openai", db)


def has_any_llm_key(db: Session | None = None) -> bool:
    if db is not None and list_connections(db):
        return True
    return _has_legacy_llm_key(db)


def connection_row_has_credentials(db: Session, ref: str) -> bool:
    if not is_connection_ref(ref):
        return False
    row = get_connection(db, parse_connection_id(ref))
    return bool(row and (row.api_key or "").strip())


def resolve_auto_model(db: Session | None = None) -> str:
    """自动策略：优先最早添加的自定义接入，否则旧版 DeepSeek / OpenAI 槽位。"""
    if db is not None:
        rows = list_connections(db)
        if rows:
            return connection_catalog_id(rows[0].id)
    if provider_has_key("deepseek", db):
        return "deepseek:deepseek-v4-flash"
    if provider_has_key("openai", db):
        return "openai:gpt-4o-mini"
    return ""


def resolve_effective_model(requested: str | None, db: Session | None = None) -> str:
    """
    将前端传入的 chat_model / 存库的 semantic 配置解析为具体 provider:model 或 conn:uuid。
    """
    r = (requested or "").strip()
    if not r or r == "auto":
        return resolve_auto_model(db)
    if is_connection_ref(r):
        if db is not None and connection_row_has_credentials(db, r):
            return r
        return resolve_auto_model(db)
    try:
        provider, _ = parse_model_ref(r)
    except ValueError:
        return resolve_auto_model(db)
    if provider_has_key(provider, db):
        return r
    return resolve_auto_model(db)


def _fmt_catalog_label(kind_label: str, connection_name: str, model_tail: str) -> str:
    cn = (connection_name or "").strip()
    if cn:
        return f"{kind_label}「{cn}」· {model_tail}"
    return f"{kind_label} · {model_tail}"


def _label_for_ref(ref: str, db: Session | None) -> str:
    if is_connection_ref(ref):
        if db is None:
            return ref
        row = get_connection(db, parse_connection_id(ref))
        if not row:
            return ref
        return f"{row.vendor_label}「{row.custom_name}」· {row.model_id}"
    provider, mid = parse_model_ref(ref)
    oa_nm = (get_stored_openai_connection_name(db) or "").strip()
    ds_nm = (get_stored_deepseek_connection_name(db) or "").strip()
    if provider == "deepseek":
        return _fmt_catalog_label("DeepSeek", ds_nm, _deepseek_catalog_tail(mid))
    return _fmt_catalog_label("OpenAI 兼容", oa_nm, mid)


def _custom_connection_catalog_entries(db: Session) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in list_connections(db):
        if not (row.api_key or "").strip():
            continue
        cid = connection_catalog_id(row.id)
        label = f"{row.vendor_label} · {row.custom_name} · {row.model_id}"
        out.append(
            {
                "id": cid,
                "label": label,
                "provider": row.provider,
                "kind_label": row.vendor_label,
                "connection_name": row.custom_name,
                "model_id": row.model_id,
                "model_short_label": row.model_id,
                "model_family": "custom",
                "vendor_id": row.vendor_id,
            }
        )
    return out


def catalog_models(db: Session | None = None) -> dict:
    """供 GET /api/llm/catalog：可选模型列表与自动解析结果。"""
    chat_models: list[dict[str, str]] = []
    if db is not None:
        chat_models.extend(_custom_connection_catalog_entries(db))

    oa_nm = (get_stored_openai_connection_name(db) or "").strip() if db is not None else ""
    ds_nm = (get_stored_deepseek_connection_name(db) or "").strip() if db is not None else ""

    if provider_has_key("deepseek", db):
        for mid, short_label, family in DEEPSEEK_CATALOG_ROWS:
            tail = f"{short_label} · {mid}"
            chat_models.append(
                {
                    "id": f"deepseek:{mid}",
                    "label": _fmt_catalog_label("DeepSeek", ds_nm, tail),
                    "provider": "deepseek",
                    "kind_label": "DeepSeek",
                    "connection_name": ds_nm,
                    "model_id": mid,
                    "model_short_label": short_label,
                    "model_family": family,
                }
            )
    if provider_has_key("openai", db):
        for mid in ("gpt-4o-mini", "gpt-4o", "gpt-4-turbo"):
            chat_models.append(
                {
                    "id": f"openai:{mid}",
                    "label": _fmt_catalog_label("OpenAI 兼容", oa_nm, mid),
                    "provider": "openai",
                    "kind_label": "OpenAI 兼容",
                    "connection_name": oa_nm,
                    "model_id": mid,
                    "model_short_label": mid,
                    "model_family": "openai",
                }
            )
    auto = resolve_auto_model(db)
    auto_label = "自动"
    if auto.startswith("conn:"):
        auto_label = "自动（优先首个自定义接入）"
    elif auto.startswith("deepseek:"):
        auto_label = "自动（优先 DeepSeek）"
    elif auto.startswith("openai:"):
        auto_label = "自动（优先 OpenAI 兼容）"
    auto_resolved_label = ""
    if auto:
        try:
            auto_resolved_label = _label_for_ref(auto, db)
        except ValueError:
            auto_resolved_label = auto
    return {
        "auto_id": "auto",
        "auto_label": auto_label,
        "auto_resolved": auto,
        "auto_resolved_label": auto_resolved_label,
        "models": chat_models,
        "has_llm": has_any_llm_key(db),
    }


def is_allowed_semantic_value(value: str, db: Session | None = None) -> bool:
    v = (value or "").strip()
    if not v or v == "auto":
        return True
    if is_connection_ref(v):
        return connection_row_has_credentials(db, v) if db is not None else False
    try:
        provider, _ = parse_model_ref(v)
    except ValueError:
        return False
    if not provider_has_key(provider, db):
        return False
    allowed_ids = {m["id"] for m in catalog_models(db)["models"]}
    return v in allowed_ids
