"""本地到 GitHub 的连通性探测（不涉及用户 Token，仅判断网络/TLS 是否可达）。"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter

from services.httpx_env import sync_client as httpx_sync_client

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

_UA = {"User-Agent": "DataLens-NetworkCheck/1.0"}


def _probe_get(url: str) -> dict[str, Any]:
    try:
        with httpx_sync_client(timeout=12.0, follow_redirects=True) as client:
            r = client.get(url, headers=_UA)
        reachable = r.status_code < 500
        return {
            "url": url,
            "reachable": reachable,
            "http_status": r.status_code,
            "body_preview": ((r.text or "")[:200]).replace("\n", " ").strip(),
        }
    except httpx.RequestError as exc:
        return {
            "url": url,
            "reachable": False,
            "error": str(exc),
            "hint": "无法建立 TLS/TCP 连接，常见原因：DNS 失败、防火墙/公司代理拦截、需 VPN、或本机未联网。",
        }


def _probe_head(url: str) -> dict[str, Any]:
    try:
        with httpx_sync_client(timeout=12.0, follow_redirects=True) as client:
            r = client.head(url, headers=_UA)
        return {
            "url": url,
            "reachable": r.status_code < 500,
            "http_status": r.status_code,
        }
    except httpx.RequestError as exc:
        return {
            "url": url,
            "reachable": False,
            "error": str(exc),
            "hint": "无法连接该地址（与 REST API 路径不同，仅作补充参考）。",
        }


@router.get("/github")
def github_reachability() -> dict[str, Any]:
    """
    探测本机进程能否访问 GitHub（不携带用户 PAT）。
    - `api.github.com`：与代码同步使用的 REST 入口一致。
    - `github.com`：主站，用于对比（部分网络只拦其一）。
    """
    api = _probe_get("https://api.github.com/")
    www = _probe_head("https://github.com/")

    if api.get("reachable"):
        summary = (
            "后端进程到 api.github.com 可连通（已收到 HTTP 响应）。"
            "若代码同步仍失败，更可能是 Token 权限、owner/repo、分支或组织 SSO，而非纯网络不通。"
        )
    elif www.get("reachable") and not api.get("reachable"):
        summary = (
            "能访问 github.com，但 api.github.com 异常。"
            "常见于企业代理只放行网页、或 DNS/路由对 API 子域单独策略；请放行 api.github.com。"
        )
    else:
        summary = (
            "后端很可能无法稳定访问 GitHub（API 与主站均异常）。"
            "请检查 VPN/代理、公司防火墙、或运行后端的机器出网策略。"
        )

    return {
        "api_github_com": api,
        "github_com": www,
        "summary": summary,
    }
