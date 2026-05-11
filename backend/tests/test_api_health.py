"""应用启动与健康检查 — 轻量集成（startup 容忍数据库不可用）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint() -> None:
    try:
        from main import app
    except ImportError as exc:
        pytest.skip(f"完整后端依赖未安装，跳过集成测试: {exc}")

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
