from __future__ import annotations

from fastapi import HTTPException, Request

from config import get_settings


def _extract_bearer_token(header: str) -> str:
    raw = (header or "").strip()
    if not raw:
        return ""
    if not raw.lower().startswith("bearer "):
        return ""
    return raw[7:].strip()


def enforce_request_auth(request: Request) -> None:
    """全局 API 鉴权：除健康检查外，默认要求 Authorization: Bearer <token>。"""
    settings = get_settings()
    if not settings.api_auth_enabled:
        return
    path = request.url.path or ""
    if path in {"/health", "/docs", "/openapi.json", "/redoc"}:
        return
    token = _extract_bearer_token(request.headers.get("Authorization", ""))
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if token != settings.api_auth_token:
        raise HTTPException(status_code=401, detail="invalid bearer token")
