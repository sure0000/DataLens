"""AST-level read-only validation for LLM-generated SQL (guardrail layer)."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

_MAX_JOINS = 16

# These can only appear as top-level statements — tree search is safe.
_FORBIDDEN_STMT: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Merge,
)
# These can also appear as functions within SELECT (e.g. REPLACE()).
_FORBIDDEN_ROOT_ONLY: tuple[type[exp.Expression], ...] = (
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


def format_sql_for_display(sql: str, *, dialect: str) -> str:
    """
    将 SQL 格式化为多行可读形式（用于推理链路展示与返回给前端的 sql 字段）。
    解析失败时返回去首尾空白后的原文，不抛异常。
    """
    raw = (sql or "").strip()
    if not raw:
        return ""
    read_d = (dialect or "mysql").strip() or "mysql"
    try:
        statements = sqlglot.parse(raw, read=read_d)
    except Exception:  # noqa: BLE001
        return raw
    if not statements:
        return raw
    parts: list[str] = []
    for stmt in statements:
        if stmt is None:
            continue
        txt = stmt.sql(dialect=read_d, pretty=True)
        if txt.strip():
            parts.append(txt.strip())
    return "\n\n".join(parts) if parts else raw


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

    for cls in _FORBIDDEN_STMT:
        if root.find(cls):
            return False, f"禁止非只读语句（检测到 {cls.__name__}）"

    for cls in _FORBIDDEN_ROOT_ONLY:
        if isinstance(root, cls):
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


def extract_table_refs_from_sql(sql: str, *, dialect: str) -> list[tuple[str | None, str | None, str]]:
    """
    从 SELECT / WITH 语句中收集 FROM/JOIN 等处的物理表引用（catalog, db/schema, name）。
    忽略 WITH 子句内定义的 CTE 名，避免把 CTE 当作真实表。
    解析失败时返回空列表。
    """
    raw = (sql or "").strip()
    if not raw:
        return []
    try:
        statements = sqlglot.parse(raw, read=dialect)
    except Exception:  # noqa: BLE001
        return []
    if not statements:
        return []
    root = statements[0]
    cte_names: set[str] = set()
    with_ = root.args.get("with_")
    if with_ and hasattr(with_, "expressions"):
        for cte in with_.expressions:
            alias = getattr(cte, "alias", None)
            if alias:
                cte_names.add(str(alias))

    out: list[tuple[str | None, str | None, str]] = []
    for t in root.find_all(exp.Table):
        name = (t.name or "").strip() if hasattr(t, "name") else ""
        if not name or name in cte_names:
            continue
        cat = str(t.catalog).strip() if t.catalog else None
        db_part = str(t.db).strip() if t.db else None
        if cat == "":
            cat = None
        if db_part == "":
            db_part = None
        out.append((cat, db_part, name))
    return out
