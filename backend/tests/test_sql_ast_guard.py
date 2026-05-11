"""SQL AST 护栏：只读校验、方言映射、表引用抽取 — Copilot 执行前关键路径。"""

from __future__ import annotations

import pytest

from services.sql_ast_guard import (
    extract_table_refs_from_sql,
    format_sql_for_display,
    source_type_to_sqlglot_dialect,
    validate_readonly_sql_ast,
)


@pytest.mark.parametrize(
    "source_type,expected",
    [
        ("mysql", "mysql"),
        ("MariaDB", "mysql"),
        ("clickhouse", "clickhouse"),
        ("postgres", "postgres"),
        ("trino", "trino"),
        ("sqlserver", "tsql"),
        ("sqlite", "sqlite"),
        ("hive", "hive"),
        ("unknown_vendor", "mysql"),
    ],
)
def test_source_type_to_sqlglot_dialect(source_type: str, expected: str) -> None:
    assert source_type_to_sqlglot_dialect(source_type) == expected


@pytest.mark.parametrize(
    "sql,dialect,expect_ok",
    [
        ("SELECT 1", "mysql", True),
        ("WITH a AS (SELECT 1) SELECT * FROM a", "mysql", True),
        ("SHOW TABLES", "mysql", True),
        ("DESCRIBE t", "mysql", True),
        ("", "mysql", False),
        ("SELECT 1; SELECT 2", "mysql", False),
        ("INSERT INTO t VALUES (1)", "mysql", False),
        ("UPDATE t SET x=1", "mysql", False),
        ("DELETE FROM t", "mysql", False),
        ("DROP TABLE t", "mysql", False),
        ("TRUNCATE TABLE t", "mysql", False),
    ],
)
def test_validate_readonly_sql_ast(sql: str, dialect: str, expect_ok: bool) -> None:
    ok, err = validate_readonly_sql_ast(sql, dialect=dialect)
    assert ok is expect_ok
    if expect_ok:
        assert err == ""
    else:
        assert err


def test_validate_readonly_sql_ast_join_limit() -> None:
    inner = "SELECT 1 AS x FROM t0"
    for i in range(1, 20):
        inner = f"SELECT a.x FROM ({inner}) AS a JOIN t{i} ON 1=1"
    sql = inner
    ok, err = validate_readonly_sql_ast(sql, dialect="mysql")
    assert ok is False
    assert "JOIN" in err


def test_extract_table_refs_ignores_cte_names() -> None:
    sql = """
    WITH cte AS (SELECT 1 AS id)
    SELECT u.id FROM cte JOIN users AS u ON u.id = cte.id
    """
    refs = extract_table_refs_from_sql(sql, dialect="mysql")
    table_names = [r[2] for r in refs]
    assert "users" in table_names
    assert "cte" not in table_names


def test_format_sql_for_display_non_empty() -> None:
    out = format_sql_for_display("select a,b from t where id=1", dialect="mysql")
    assert "SELECT" in out
    assert "FROM" in out


def test_format_sql_for_display_invalid_returns_raw() -> None:
    raw = "SELEC 1"
    assert format_sql_for_display(raw, dialect="mysql") == raw
