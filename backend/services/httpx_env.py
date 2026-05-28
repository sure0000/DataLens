"""httpx 客户端：兼容系统 SOCKS 代理但未安装 socksio、或代理端口不可达的环境。"""

from __future__ import annotations

import logging
import os
import socket
from urllib.parse import urlparse

import httpx

_logger = logging.getLogger(__name__)
_warned_socks_fallback = False
_warned_proxy_unreachable = False
_warned_proxy_ssl_broken = False
_proxy_reachable_cache: bool | None = None
_proxy_https_ok_cache: bool | None = None


def _env_proxy_url() -> str:
    for key in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def _proxy_endpoint_reachable(proxy_url: str, *, timeout: float = 0.6) -> bool:
    """检测代理地址 TCP 是否可连（仅用于避免指向已关闭端口的 ALL_PROXY）。"""
    if not proxy_url.strip():
        return True
    try:
        parsed = urlparse(proxy_url.strip())
    except Exception:
        return True
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return True
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _system_proxy_reachable() -> bool:
    global _proxy_reachable_cache
    if _proxy_reachable_cache is not None:
        return _proxy_reachable_cache
    proxy = _env_proxy_url()
    if not proxy:
        _proxy_reachable_cache = True
        return True
    ok = _proxy_endpoint_reachable(proxy)
    _proxy_reachable_cache = ok
    return ok


def _system_proxy_https_ok() -> bool:
    """代理端口可连但 TLS 仍可能失败；用轻量 HEAD 探测一次并缓存。"""
    global _proxy_https_ok_cache
    if _proxy_https_ok_cache is not None:
        return _proxy_https_ok_cache
    proxy = _env_proxy_url()
    if not proxy:
        _proxy_https_ok_cache = True
        return True
    if not _system_proxy_reachable():
        _proxy_https_ok_cache = False
        return False
    try:
        with httpx.Client(proxy=proxy, timeout=8.0, follow_redirects=True) as client:
            resp = client.head("https://api.github.com/")
            _proxy_https_ok_cache = resp.status_code < 500
    except Exception:
        _proxy_https_ok_cache = False
    return bool(_proxy_https_ok_cache)


def _socks_proxy_without_socksio() -> bool:
    all_proxy = (os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or "").strip()
    if not all_proxy.lower().startswith(("socks4://", "socks5://", "socks://")):
        return False
    try:
        import socksio  # noqa: F401
    except ImportError:
        return True
    return False


def _resolve_trust_env(*, for_local: bool) -> bool:
    global _warned_socks_fallback, _warned_proxy_unreachable, _warned_proxy_ssl_broken

    if for_local:
        return False

    try:
        from config import get_settings

        if not get_settings().http_trust_env:
            return False
    except Exception:
        pass

    if _socks_proxy_without_socksio():
        if not _warned_socks_fallback:
            _warned_socks_fallback = True
            all_proxy = (os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or "").strip()
            _logger.warning(
                "检测到 SOCKS 代理 (%s) 但未安装 socksio；本次 HTTP 将不走系统代理。"
                "如需经代理访问外网，请执行: pip install httpx[socks]",
                all_proxy,
            )
        return False

    proxy = _env_proxy_url()
    if not proxy:
        return True

    if not _system_proxy_reachable():
        if not _warned_proxy_unreachable:
            _warned_proxy_unreachable = True
            _logger.warning(
                "检测到系统代理 %s 但端口不可达；出站 HTTP 将直连。"
                "请启动代理软件，或取消 ALL_PROXY/HTTP_PROXY，或在 .env 设置 DATALENS_HTTP_TRUST_ENV=false",
                proxy,
            )
        return False

    if not _system_proxy_https_ok():
        if not _warned_proxy_ssl_broken:
            _warned_proxy_ssl_broken = True
            _logger.warning(
                "系统代理 %s 可连接但 HTTPS 探测失败（常见为 SSL EOF）；出站 HTTP 将改为直连。"
                "若访问 GitHub 必须走代理，请检查代理规则；否则可在 .env 设置 DATALENS_HTTP_TRUST_ENV=false 并取消 ALL_PROXY",
                proxy,
            )
        return False

    return True


def sync_client(
    timeout: float = 60.0,
    *,
    for_local: bool = False,
    follow_redirects: bool = False,
) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        trust_env=_resolve_trust_env(for_local=for_local),
        follow_redirects=follow_redirects,
    )


def async_client(
    timeout: float = 60.0,
    *,
    for_local: bool = False,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        trust_env=_resolve_trust_env(for_local=for_local),
        follow_redirects=follow_redirects,
    )


def format_http_request_error(exc: BaseException) -> str:
    """将 httpx 网络错误整理为用户可读说明（含常见 SSL/代理提示）。"""
    raw = str(exc) or type(exc).__name__
    if "UNEXPECTED_EOF_WHILE_READING" in raw or "SSLError" in raw or "SSL:" in raw:
        proxy = _env_proxy_url()
        hint = (
            "TLS 握手被中断，常见于：系统代理/VPN 未启动或端口错误、公司网络拦截、或需配置代理才能访问外网。"
        )
        if proxy:
            reachable = _system_proxy_reachable()
            if not reachable:
                hint += f" 当前环境代理 {proxy} 端口不可达，请启动代理或取消 ALL_PROXY，或在 .env 设置 DATALENS_HTTP_TRUST_ENV=false。"
            else:
                hint += f" 当前环境代理：{proxy}。可尝试切换网络、在 .env 设置 DATALENS_HTTP_TRUST_ENV=false 直连，或修正代理配置。"
        else:
            hint += " 若访问 GitHub/OpenAI 需代理，请配置可用的 HTTP_PROXY/ALL_PROXY 并安装 httpx[socks]。"
        return f"网络请求失败：{raw}。{hint}"
    return f"网络请求失败：{raw}"
