"""httpx 客户端：兼容系统 SOCKS 代理但未安装 socksio 的环境。"""

from __future__ import annotations

import logging
import os

import httpx

_logger = logging.getLogger(__name__)
_warned_socks_fallback = False


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
    global _warned_socks_fallback
    if for_local:
        return False
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
    return True


def sync_client(timeout: float = 60.0, *, for_local: bool = False) -> httpx.Client:
    return httpx.Client(timeout=timeout, trust_env=_resolve_trust_env(for_local=for_local))


def async_client(timeout: float = 60.0, *, for_local: bool = False) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, trust_env=_resolve_trust_env(for_local=for_local))
