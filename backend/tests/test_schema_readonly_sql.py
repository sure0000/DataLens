"""只读 SQL 执行入口的前缀校验 + SQLite 真实执行（无需外部 MySQL）。"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from services.schema_extractor import execute_readonly_sql


@pytest.mark.parametrize(
    "sql,expect_ok",
    [
        ("SELECT 1", True),
        ("WITH x AS (SELECT 1) SELECT * FROM x", True),
        ("DELETE FROM t WHERE 1=1", False),
        ("INSERT INTO t VALUES (1)", False),
        ("UPDATE t SET a=1", False),
    ],
)
def test_execute_readonly_sql_rejects_non_select_prefix(sql: str, expect_ok: bool) -> None:
    """未连库即可覆盖：前缀不满足时不得打开下游连接。"""
    conn_info = {"source_type": "sqlite", "database": ":memory:"}
    r = execute_readonly_sql(conn_info, sql, limit=10)
    assert r["ok"] is expect_ok
    if not expect_ok:
        assert "仅允许只读" in (r.get("error") or "")
        assert r["rows"] == []


def test_execute_readonly_sql_sqlite_select_and_limit_wrap() -> None:
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
        raw.executemany("INSERT INTO demo (name) VALUES (?)", [("a",), ("b",)])
        raw.commit()
        raw.close()

        conn_info = {"source_type": "sqlite", "database": path}
        r = execute_readonly_sql(conn_info, "SELECT id, name FROM demo ORDER BY id", limit=1)
        assert r["ok"] is True
        assert r["columns"]
        assert len(r["rows"]) == 1
        assert r["rows"][0]["name"] in ("a", "b")
    finally:
        os.unlink(path)
