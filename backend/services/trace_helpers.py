"""Trace 追踪行辅助函数。"""
from __future__ import annotations

from typing import Any


def insert_reasoning_4_after_reasoning_3(traces: list[dict[str, Any]], detail: str) -> None:
    """在 reasoning_3 之后插入第 4 步（SQL 修复/执行后写入）。"""
    d = (detail or "").strip()
    if len(d) > 2800:
        d = d[:2800] + "…"
    row: dict[str, Any] = {"id": "reasoning_4", "label": "7. 查询逻辑以及 SQL", "detail": d}
    for i, t in enumerate(traces):
        if t.get("id") == "reasoning_3":
            traces.insert(i + 1, row)
            return
    traces.append(row)
