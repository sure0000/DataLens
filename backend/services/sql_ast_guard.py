"""AST-level read-only validation for LLM-generated SQL (guardrail layer)."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

_MAX_JOINS = 16

_FORBIDDEN: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Merge,
    exp.Replace,
)


def source_type_to_sqlglot_dialect(source_type: str) -> str:
    """Map DataLens `DataSource.source_type` to sqlglot `read` dialect name."""
    st = (source_type or "").strip().lower()
    if st in ("mysql", "mariadb", "doris", "starrocks"):
        return "mysql"
    if st in ("postgres", "postgresql", "greenplum"):
        return "postgres"
    if st == "clickhouse":
        return "clickhouse"
    if st == "trino":
        return "trino"
    if st == "sqlserver":
        return "tsql"
    if st == "sqlite":
        return "sqlite"
    if st == "hive":
        return "hive"
    return "mysql"


def validate_readonly_sql_ast(sql: str, *, dialect: str) -> tuple[bool, str]:
    """
    Parse SQL with sqlglot and reject non-read-only or multi-statement batches.

    Returns (ok, error_message). error_message is empty when ok is True.
    """
    raw = (sql or "").strip()
    if not raw:
        return False, "SQL 为空"

    try:
        statements = sqlglot.parse(raw, read=dialect)
    except sqlglot.errors.ParseError as e:
        return False, f"SQL 语法解析失败（方言={dialect}）：{e}"

    if not statements:
        return False, "SQL 解析结果为空"

    if len(statements) > 1:
        return False, "禁止一次提交多条 SQL 语句"

    root = statements[0]

    for cls in _FORBIDDEN:
        if root.find(cls):
            return False, f"禁止非只读语句（检测到 {cls.__name__}）"

    allowed_root = isinstance(root, (exp.Select, exp.Union, exp.Show, exp.Describe))
    if not allowed_root:
        if isinstance(root, exp.Command):
            return False, "不支持该命令类语句，请使用 SELECT / WITH / SHOW / DESCRIBE / EXPLAIN 形式"
        return False, f"不支持的语句类型: {type(root).__name__}"

    join_count = len(list(root.find_all(exp.Join)))
    if join_count > _MAX_JOINS:
        return False, f"JOIN 数量过多（>{_MAX_JOINS}），请拆分查询以降低风险"

    return True, ""
