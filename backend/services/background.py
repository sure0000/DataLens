"""统一后台任务管理：用 asyncio 事件循环替代散落的 threading.Thread(daemon=True)。

所有 fire-and-forget 后台任务通过 `schedule(coro)` 投递，异常会被记录到日志。
同步任务通过 `schedule_sync(func, *args)` 在默认线程池执行。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_TASKS: set[asyncio.Task[Any]] = set()


def _task_done(task: asyncio.Task[Any]) -> None:
    _TASKS.discard(task)
    exc = task.exception()
    if exc is not None:
        _logger.error("后台任务异常: %s", exc, exc_info=exc)


def schedule(coro: Awaitable[Any]) -> None:
    """投递一个协程到事件循环，异常时自动日志记录。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _logger.warning("无运行中的事件循环，启动临时 loop 执行后台任务")
        asyncio.run(_safe_run(coro))
        return
    task = loop.create_task(coro)
    _TASKS.add(task)
    task.add_done_callback(_task_done)


async def _safe_run(coro: Awaitable[Any]) -> None:
    try:
        await coro
    except Exception:
        _logger.exception("临时 loop 后台任务异常")


def schedule_sync(func: Callable[..., _T], *args: Any) -> None:
    """在默认线程池中执行同步函数，异常时自动日志记录。"""

    async def _wrapper() -> None:
        try:
            await asyncio.to_thread(func, *args)
        except Exception:
            _logger.exception("后台同步任务异常: %s", getattr(func, "__name__", str(func)))

    schedule(_wrapper())


def pending_count() -> int:
    """当前未完成的后台任务数（用于健康检查/监控）。"""
    return len(_TASKS)
