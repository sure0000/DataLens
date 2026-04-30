import re
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any

import pymysql
from clickhouse_driver import Client as ClickHouseClient


@contextmanager
def mysql_conn(conn_info: dict[str, Any]) -> Iterable[pymysql.connections.Connection]:
    conn = pymysql.connect(
        host=conn_info["host"],
        port=int(conn_info.get("port", 3306)),
        user=conn_info["username"],
        password=conn_info["password"],
        database=conn_info["database"],
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


def _clickhouse_client(conn_info: dict[str, Any]) -> ClickHouseClient:
    return ClickHouseClient(
        host=conn_info["host"],
        port=int(conn_info.get("port", 9000)),
        user=conn_info["username"],
        password=conn_info["password"],
        database=conn_info["database"],
    )


def get_databases(conn_info: dict[str, Any]) -> list[str]:
    if conn_info["source_type"] == "mysql":
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            rows = [r["Database"] for r in cursor.fetchall()]
            system_dbs = {"information_schema", "mysql", "performance_schema", "sys"}
            return [db for db in rows if db not in system_dbs]
    client = _clickhouse_client(conn_info)
    rows = client.execute("SHOW DATABASES")
    return [r[0] for r in rows if r[0] not in {"system", "information_schema", "INFORMATION_SCHEMA"}]


def get_tables_for_database(conn_info: dict[str, Any], database_name: str) -> list[str]:
    return [t["name"] for t in get_tables_meta_for_database(conn_info, database_name)]


def get_tables_meta_for_database(conn_info: dict[str, Any], database_name: str) -> list[dict[str, str]]:
    if conn_info["source_type"] == "mysql":
        mysql_info = {**conn_info, "database": database_name}
        with mysql_conn(mysql_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME
                """,
                (database_name,),
            )
            return [{"name": row["TABLE_NAME"], "comment": row["TABLE_COMMENT"] or ""} for row in cursor.fetchall()]
    client = _clickhouse_client(conn_info)
    rows = client.execute(
        """
        SELECT name, comment
        FROM system.tables
        WHERE database = %(database)s
        ORDER BY name
        """,
        {"database": database_name},
    )
    return [{"name": r[0], "comment": (r[1] or "") if len(r) > 1 else ""} for r in rows]


def get_tables(conn_info: dict[str, Any]) -> list[str]:
    return get_tables_for_database(conn_info, conn_info["database"])


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _validate_identifier(name: str) -> None:
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")


def get_ddl(conn_info: dict[str, Any], table_name: str) -> str:
    if conn_info["source_type"] == "mysql":
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
            row = cursor.fetchone()
            return row["Create Table"]
    _validate_identifier(table_name)
    client = _clickhouse_client(conn_info)
    row = client.execute(f"SHOW CREATE TABLE {table_name}")
    return row[0][0] if row else ""


def get_columns(conn_info: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    if conn_info["source_type"] == "mysql":
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
                """,
                (conn_info["database"], table_name),
            )
            return [
                {
                    "column_name": row["COLUMN_NAME"],
                    "data_type": row["DATA_TYPE"],
                    "comment": row["COLUMN_COMMENT"] or "",
                }
                for row in cursor.fetchall()
            ]
    client = _clickhouse_client(conn_info)
    rows = client.execute(
        """
        SELECT name, type, comment
        FROM system.columns
        WHERE database = %(database)s AND table = %(table)s
        """,
        {"database": conn_info["database"], "table": table_name},
    )
    return [{"column_name": r[0], "data_type": r[1], "comment": r[2] or ""} for r in rows]


def get_sample(conn_info: dict[str, Any], table_name: str, limit: int = 1000) -> list[dict[str, Any]]:
    if conn_info["source_type"] == "mysql":
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM `{table_name}` LIMIT %s", (limit,))
            return list(cursor.fetchall())
    _validate_identifier(table_name)
    client = _clickhouse_client(conn_info)
    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    data, columns = client.execute(query, with_column_types=True)
    names = [c[0] for c in columns]
    return [dict(zip(names, row)) for row in data]


def get_row_count(conn_info: dict[str, Any], table_name: str) -> int:
    if conn_info["source_type"] == "mysql":
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM `{table_name}`")
            return int(cursor.fetchone()["c"])
    _validate_identifier(table_name)
    client = _clickhouse_client(conn_info)
    row = client.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(row[0][0]) if row else 0


def execute_readonly_sql(conn_info: dict[str, Any], sql: str, limit: int = 200) -> dict[str, Any]:
    sql_clean = sql.strip().rstrip(";")
    lowered = sql_clean.lower()
    allowed_prefixes = ("select", "show", "with", "desc", "describe", "explain")
    if not lowered.startswith(allowed_prefixes):
        return {"ok": False, "error": "仅允许只读查询语句（SELECT/SHOW/WITH/DESC/EXPLAIN）", "columns": [], "rows": []}

    # Only SELECT/WITH can be safely wrapped in a subquery; SHOW/DESC/EXPLAIN cannot
    can_wrap = lowered.startswith(("select", "with"))

    if conn_info["source_type"] == "mysql":
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            if can_wrap:
                cursor.execute(f"SELECT * FROM ({sql_clean}) __chatbi_sub LIMIT %s", (limit,))
            else:
                cursor.execute(sql_clean)
            rows = list(cursor.fetchall())[:limit]
            columns = list(rows[0].keys()) if rows else [d[0] for d in (cursor.description or [])]
            return {"ok": True, "columns": columns, "rows": rows}

    client = _clickhouse_client(conn_info)
    if can_wrap:
        data, cols = client.execute(f"SELECT * FROM ({sql_clean}) LIMIT {limit}", with_column_types=True)
    else:
        data, cols = client.execute(sql_clean, with_column_types=True)
        data = data[:limit]
    col_names = [c[0] for c in cols]
    rows = [dict(zip(col_names, row)) for row in data]
    return {"ok": True, "columns": col_names, "rows": rows}
