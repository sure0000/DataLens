import re
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg2
import pymysql
from clickhouse_driver import Client as ClickHouseClient
from psycopg2 import sql as psql
from psycopg2.extras import RealDictCursor

MYSQL_FAMILY = frozenset({"mysql", "mariadb", "doris", "starrocks"})
POSTGRES_FAMILY = frozenset({"postgres", "postgresql", "greenplum"})
ALLOWED_SOURCE_TYPES = frozenset(
    {
        *MYSQL_FAMILY,
        *POSTGRES_FAMILY,
        "sqlserver",
        "sqlite",
        "clickhouse",
        "trino",
        "hive",
    }
)


def _is_mysql_family(source_type: str) -> bool:
    return source_type in MYSQL_FAMILY


def _is_postgres_family(source_type: str) -> bool:
    return source_type in POSTGRES_FAMILY


def _pg_schema(conn_info: dict[str, Any]) -> str:
    return conn_info.get("namespace") or "public"


def _trino_catalog_schema(conn_info: dict[str, Any]) -> tuple[str, str]:
    raw = (conn_info.get("namespace") or conn_info.get("database") or "").strip()
    if "." in raw:
        catalog, schema = raw.split(".", 1)
        return catalog.strip(), schema.strip() or "default"
    return raw, "default"


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


@contextmanager
def postgres_conn(conn_info: dict[str, Any]) -> Iterable[Any]:
    conn = psycopg2.connect(
        host=conn_info["host"],
        port=int(conn_info.get("port", 5432)),
        dbname=conn_info["database"],
        user=conn_info["username"],
        password=conn_info["password"],
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def sqlserver_conn(conn_info: dict[str, Any]) -> Iterable[Any]:
    import pymssql

    conn = pymssql.connect(
        server=conn_info["host"],
        port=int(conn_info.get("port", 1433)),
        user=conn_info["username"],
        password=conn_info["password"],
        database=conn_info["database"],
        as_dict=True,
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def sqlite_conn(conn_info: dict[str, Any]) -> Iterable[sqlite3.Connection]:
    path = (conn_info.get("database") or "").strip()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _sqlite_cursor(conn: sqlite3.Connection) -> Iterable[sqlite3.Cursor]:
    """sqlite3.Cursor 在部分 Python 版本下不支持用作 context manager，统一用 try/finally 关闭。"""
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


@contextmanager
def hive_conn(conn_info: dict[str, Any]) -> Iterable[Any]:
    from pyhive import hive

    pw = (conn_info.get("password") or "").strip()
    kwargs: dict[str, Any] = {
        "host": conn_info["host"],
        "port": int(conn_info.get("port", 10000)),
        "username": conn_info.get("username") or "hive",
        "database": conn_info.get("database") or "default",
    }
    if pw:
        kwargs["password"] = pw
        kwargs["auth"] = "CUSTOM"
    else:
        kwargs["auth"] = "NOSASL"
    conn = hive.Connection(**kwargs)
    try:
        yield conn
    finally:
        conn.close()


def _hive_parse_describe_rows(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        name = str(row[0]).strip() if row[0] is not None else ""
        if not name or name.startswith("#"):
            break
        if name == "col_name" and len(row) > 1 and str(row[1]).strip() == "data_type":
            continue
        dtype = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        comment = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
        out.append({"column_name": name, "data_type": dtype, "comment": comment})
    return out


def _clickhouse_client(conn_info: dict[str, Any]) -> ClickHouseClient:
    return ClickHouseClient(
        host=conn_info["host"],
        port=int(conn_info.get("port", 9000)),
        user=conn_info["username"],
        password=conn_info["password"],
        database=conn_info["database"],
    )


def _trino_connection(conn_info: dict[str, Any]) -> Any:
    from trino.auth import BasicAuthentication
    from trino.dbapi import connect as trino_connect

    catalog, schema = _trino_catalog_schema(conn_info)
    user = conn_info.get("username") or "trino"
    password = conn_info.get("password") or ""
    auth = BasicAuthentication(user, password) if password else None
    return trino_connect(
        host=conn_info["host"],
        port=int(conn_info.get("port", 8080)),
        user=user,
        catalog=catalog,
        schema=schema,
        auth=auth,
    )


def get_databases(conn_info: dict[str, Any]) -> list[str]:
    st = conn_info["source_type"]
    if _is_mysql_family(st):
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            rows = [r["Database"] for r in cursor.fetchall()]
            system_dbs = {"information_schema", "mysql", "performance_schema", "sys"}
            return [db for db in rows if db not in system_dbs]

    if _is_postgres_family(st):
        with postgres_conn(conn_info) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                  AND schema_name NOT LIKE 'pg\\_temp\\_%' ESCAPE '\\'
                  AND schema_name NOT LIKE 'pg\\_toast\\_%' ESCAPE '\\'
                ORDER BY schema_name
                """
            )
            return [r["schema_name"] for r in cursor.fetchall()]

    if st == "sqlserver":
        with sqlserver_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT name FROM sys.databases
                WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
                ORDER BY name
                """
            )
            return [r["name"] for r in cursor.fetchall()]

    if st == "sqlite":
        return ["main"]

    if st == "trino":
        raw = (conn_info.get("database") or "").strip()
        if "." in raw:
            return [raw]
        catalog = raw
        _validate_identifier(catalog)
        boot = {**conn_info, "database": f"{catalog}.information_schema", "namespace": f"{catalog}.information_schema"}
        conn = _trino_connection(boot)
        cur = conn.cursor()
        cur.execute(f'SHOW SCHEMAS FROM "{catalog}"')
        rows = cur.fetchall()
        conn.close()
        return [f"{catalog}.{r[0]}" for r in rows if r[0] != "information_schema"]

    if st == "clickhouse":
        client = _clickhouse_client(conn_info)
        rows = client.execute("SHOW DATABASES")
        return [r[0] for r in rows if r[0] not in {"system", "information_schema", "INFORMATION_SCHEMA"}]

    if st == "hive":
        boot = {**conn_info, "database": conn_info.get("database") or "default"}
        with hive_conn(boot) as conn:
            cur = conn.cursor()
            cur.execute("SHOW DATABASES")
            names = [r[0] for r in cur.fetchall() if r and r[0]]
        skip = {"sys", "information_schema"}
        return [n for n in names if str(n).lower() not in skip]

    raise ValueError(f"不支持的数据源类型: {st}")


def get_tables_for_database(conn_info: dict[str, Any], database_name: str) -> list[str]:
    return [t["name"] for t in get_tables_meta_for_database(conn_info, database_name)]


def get_tables_meta_for_database(conn_info: dict[str, Any], database_name: str) -> list[dict[str, str]]:
    st = conn_info["source_type"]
    if _is_mysql_family(st):
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

    if _is_postgres_family(st):
        schema = database_name
        pg_info = {**conn_info, "namespace": schema}
        with postgres_conn(pg_info) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT c.relname AS table_name, COALESCE(d.description, '') AS table_comment
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
                WHERE c.relkind = 'r' AND n.nspname = %s
                ORDER BY c.relname
                """,
                (schema,),
            )
            return [{"name": row["table_name"], "comment": row["table_comment"] or ""} for row in cursor.fetchall()]

    if st == "sqlserver":
        mssql_info = {**conn_info, "database": database_name}
        with sqlserver_conn(mssql_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT TABLE_NAME, CAST(ep.value AS NVARCHAR(MAX)) AS comment
                FROM INFORMATION_SCHEMA.TABLES t
                LEFT JOIN sys.tables st ON st.name = t.TABLE_NAME
                LEFT JOIN sys.extended_properties ep ON ep.major_id = st.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
                WHERE t.TABLE_TYPE = 'BASE TABLE' AND t.TABLE_CATALOG = DB_NAME()
                ORDER BY t.TABLE_NAME
                """
            )
            return [{"name": row["TABLE_NAME"], "comment": (row["comment"] or "").strip()} for row in cursor.fetchall()]

    if st == "sqlite":
        with sqlite_conn(conn_info) as conn, _sqlite_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
            return [{"name": row["name"], "comment": ""} for row in cursor.fetchall()]

    if st == "trino":
        cat, sch = database_name.split(".", 1) if "." in database_name else _trino_catalog_schema({**conn_info, "database": database_name})
        conn = _trino_connection({**conn_info, "database": f"{cat}.{sch}", "namespace": f"{cat}.{sch}"})
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name, CAST(NULL AS VARCHAR) AS comment
            FROM information_schema.tables
            WHERE table_catalog = %s AND table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (cat, sch),
        )
        rows = [{"name": r[0], "comment": ""} for r in cur.fetchall()]
        conn.close()
        return rows

    if st == "clickhouse":
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

    if st == "hive":
        _validate_identifier(database_name)
        hive_info = {**conn_info, "database": database_name}
        with hive_conn(hive_info) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT table_name, comment FROM information_schema.tables "
                    "WHERE lower(table_type) IN ('managed_table', 'external_table') "
                    "AND table_schema = %s ORDER BY table_name",
                    (database_name,),
                )
                meta = [{"name": str(r[0]), "comment": str(r[1] or "").strip()} for r in cur.fetchall()]
                if meta:
                    return meta
            except Exception:  # noqa: BLE001
                pass
            cur = conn.cursor()
            cur.execute(f"SHOW TABLES IN `{database_name}`")
            return [{"name": str(r[0]), "comment": ""} for r in cur.fetchall() if r and r[0]]

    raise ValueError(f"不支持的数据源类型: {st}")


def get_tables(conn_info: dict[str, Any]) -> list[str]:
    st = conn_info["source_type"]
    if _is_postgres_family(st):
        return get_tables_for_database(conn_info, _pg_schema(conn_info))
    if st == "sqlite":
        return get_tables_for_database(conn_info, "main")
    if st == "trino":
        key = (conn_info.get("namespace") or conn_info.get("database") or "").strip()
        return get_tables_for_database(conn_info, key)
    return get_tables_for_database(conn_info, conn_info["database"])


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _validate_identifier(name: str) -> None:
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")


def get_ddl(conn_info: dict[str, Any], table_name: str) -> str:
    st = conn_info["source_type"]
    if _is_mysql_family(st):
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
            row = cursor.fetchone()
            return row["Create Table"] if row else ""

    if _is_postgres_family(st):
        schema = _pg_schema(conn_info)
        with postgres_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, table_name),
            )
            rows = cursor.fetchall()
            if not rows:
                return ""
            parts: list[str] = []
            for col, dtype, char_len, nullable, default in rows:
                seg = f'"{col}" {dtype}'
                if char_len:
                    seg += f"({char_len})"
                if nullable == "NO":
                    seg += " NOT NULL"
                if default is not None:
                    seg += f" DEFAULT {str(default)}"
                parts.append(seg)
            return f'CREATE TABLE "{schema}"."{table_name}" (\n  ' + ",\n  ".join(parts) + "\n);"

    if st == "sqlserver":
        safe_tbl = table_name.replace("]", "]]")
        with sqlserver_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (table_name,),
            )
            rows = cursor.fetchall()
            if not rows:
                return ""
            parts = []
            for row in rows:
                cn, dt, cmax, nul = row["COLUMN_NAME"], row["DATA_TYPE"], row["CHARACTER_MAXIMUM_LENGTH"], row["IS_NULLABLE"]
                seg = f"[{cn}] {dt}"
                if cmax:
                    seg += f"({cmax})"
                if nul == "NO":
                    seg += " NOT NULL"
                parts.append(seg)
            return f"CREATE TABLE [{safe_tbl}] (\n  " + ",\n  ".join(parts) + "\n);"

    if st == "sqlite":
        with sqlite_conn(conn_info) as conn, _sqlite_cursor(conn) as cursor:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            row = cursor.fetchone()
            return row["sql"] or "" if row else ""

    if st == "trino":
        cat, sch = _trino_catalog_schema(conn_info)
        _validate_identifier(table_name)
        conn = _trino_connection(conn_info)
        cur = conn.cursor()
        cur.execute(f'SHOW CREATE TABLE "{cat}"."{sch}"."{table_name}"')
        r = cur.fetchone()
        conn.close()
        return r[0] if r else ""

    if st == "clickhouse":
        _validate_identifier(table_name)
        client = _clickhouse_client(conn_info)
        row = client.execute(f"SHOW CREATE TABLE {table_name}")
        return row[0][0] if row else ""

    if st == "hive":
        db = conn_info["database"]
        _validate_identifier(table_name)
        with hive_conn(conn_info) as conn:
            cur = conn.cursor()
            cur.execute(f"SHOW CREATE TABLE `{db}`.`{table_name}`")
            row = cur.fetchone()
            return str(row[0]) if row and row[0] is not None else ""

    raise ValueError(f"不支持的数据源类型: {st}")


def get_columns(conn_info: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    st = conn_info["source_type"]
    if _is_mysql_family(st):
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
                ORDER BY ORDINAL_POSITION
                """,
                (conn_info["database"], table_name),
            )
            return [
                {
                    "column_name": row["COLUMN_NAME"],
                    "data_type": row["DATA_TYPE"],
                    "column_type": row.get("COLUMN_TYPE") or "",
                    "comment": row["COLUMN_COMMENT"] or "",
                }
                for row in cursor.fetchall()
            ]

    if _is_postgres_family(st):
        schema = _pg_schema(conn_info)
        with postgres_conn(conn_info) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT a.attname AS column_name,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                       COALESCE(d.description, '') AS comment
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = a.attnum
                WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
                """,
                (schema, table_name),
            )
            return [
                {"column_name": r["column_name"], "data_type": r["data_type"], "comment": r["comment"] or ""}
                for r in cursor.fetchall()
            ]

    if st == "sqlserver":
        with sqlserver_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_CATALOG = DB_NAME() AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (table_name,),
            )
            return [
                {"column_name": row["COLUMN_NAME"], "data_type": row["DATA_TYPE"], "comment": ""}
                for row in cursor.fetchall()
            ]

    if st == "sqlite":
        _validate_identifier(table_name)
        with sqlite_conn(conn_info) as conn, _sqlite_cursor(conn) as cursor:
            cursor.execute("SELECT name, type FROM pragma_table_info(?)", (table_name,))
            return [{"column_name": row["name"], "data_type": row["type"] or "", "comment": ""} for row in cursor.fetchall()]

    if st == "trino":
        cat, sch = _trino_catalog_schema(conn_info)
        conn = _trino_connection(conn_info)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type, CAST(NULL AS VARCHAR) AS comment
            FROM information_schema.columns
            WHERE table_catalog = %s AND table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (cat, sch, table_name),
        )
        rows = [{"column_name": r[0], "data_type": r[1], "comment": r[2] or ""} for r in cur.fetchall()]
        conn.close()
        return rows

    if st == "clickhouse":
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

    if st == "hive":
        db = conn_info["database"]
        _validate_identifier(table_name)
        with hive_conn(conn_info) as conn:
            cur = conn.cursor()
            cur.execute(f"DESCRIBE `{db}`.`{table_name}`")
            return _hive_parse_describe_rows(list(cur.fetchall() or []))

    raise ValueError(f"不支持的数据源类型: {st}")


def get_sample(conn_info: dict[str, Any], table_name: str, limit: int = 1000) -> list[dict[str, Any]]:
    st = conn_info["source_type"]
    if _is_mysql_family(st):
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM `{table_name}` LIMIT %s", (limit,))
            return list(cursor.fetchall())

    if _is_postgres_family(st):
        schema = _pg_schema(conn_info)
        with postgres_conn(conn_info) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            q = psql.SQL("SELECT * FROM {}.{} LIMIT %s").format(psql.Identifier(schema), psql.Identifier(table_name))
            cursor.execute(q, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    if st == "sqlserver":
        safe = table_name.replace("]", "]]")
        lim = int(limit)
        with sqlserver_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT TOP ({lim}) * FROM [{safe}]")
            return [dict(row) for row in cursor.fetchall()]

    if st == "sqlite":
        _validate_identifier(table_name)
        with sqlite_conn(conn_info) as conn, _sqlite_cursor(conn) as cursor:
            cursor.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (limit,))
            return [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]

    if st == "trino":
        cat, sch = _trino_catalog_schema(conn_info)
        _validate_identifier(table_name)
        conn = _trino_connection(conn_info)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {cat}.{sch}.{table_name} LIMIT {int(limit)}")
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return rows

    if st == "clickhouse":
        _validate_identifier(table_name)
        client = _clickhouse_client(conn_info)
        query = f"SELECT * FROM {table_name} LIMIT {limit}"
        data, columns = client.execute(query, with_column_types=True)
        names = [c[0] for c in columns]
        return [dict(zip(names, row)) for row in data]

    if st == "hive":
        db = conn_info["database"]
        _validate_identifier(table_name)
        lim = int(limit)
        with hive_conn(conn_info) as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM `{db}`.`{table_name}` LIMIT {lim}")
            cols = [d[0] for d in (cur.description or [])]
            return [dict(zip(cols, row)) for row in (cur.fetchall() or [])]

    raise ValueError(f"不支持的数据源类型: {st}")


def get_row_count(conn_info: dict[str, Any], table_name: str) -> int:
    st = conn_info["source_type"]
    if _is_mysql_family(st):
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM `{table_name}`")
            return int(cursor.fetchone()["c"])

    if _is_postgres_family(st):
        schema = _pg_schema(conn_info)
        with postgres_conn(conn_info) as conn, conn.cursor() as cursor:
            q = psql.SQL("SELECT COUNT(*) FROM {}.{}").format(psql.Identifier(schema), psql.Identifier(table_name))
            cursor.execute(q)
            return int(cursor.fetchone()[0])

    if st == "sqlserver":
        safe = table_name.replace("]", "]]")
        with sqlserver_conn(conn_info) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM [{safe}]")
            return int(cursor.fetchone()["c"])

    if st == "sqlite":
        with sqlite_conn(conn_info) as conn, _sqlite_cursor(conn) as cursor:
            cursor.execute(f'SELECT COUNT(*) AS c FROM "{table_name.replace(chr(34), chr(34)+chr(34))}"')
            return int(cursor.fetchone()["c"])

    if st == "trino":
        cat, sch = _trino_catalog_schema(conn_info)
        _validate_identifier(table_name)
        conn = _trino_connection(conn_info)
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {cat}.{sch}.{table_name}")
        n = int(cur.fetchone()[0])
        conn.close()
        return n

    if st == "clickhouse":
        _validate_identifier(table_name)
        client = _clickhouse_client(conn_info)
        row = client.execute(f"SELECT COUNT(*) FROM {table_name}")
        return int(row[0][0]) if row else 0

    if st == "hive":
        db = conn_info["database"]
        _validate_identifier(table_name)
        with hive_conn(conn_info) as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) AS c FROM `{db}`.`{table_name}`")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    raise ValueError(f"不支持的数据源类型: {st}")


def _json_safe_cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _normalize_query_result(columns: list[str], rows: list[Any]) -> dict[str, Any]:
    norm_rows: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            norm_rows.append({str(k): _json_safe_cell(v) for k, v in row.items()})
        else:
            norm_rows.append({columns[i]: _json_safe_cell(row[i]) for i in range(min(len(columns), len(row)))})
    return {
        "ok": True,
        "columns": [str(c) for c in columns],
        "rows": norm_rows,
        "row_count": len(norm_rows),
    }


def execute_readonly_sql(conn_info: dict[str, Any], sql: str, limit: int = 200) -> dict[str, Any]:
    sql_clean = sql.strip().rstrip(";")
    lowered = sql_clean.lower()
    allowed_prefixes = ("select", "show", "with", "desc", "describe", "explain")
    if not lowered.startswith(allowed_prefixes):
        return {"ok": False, "error": "仅允许只读查询语句（SELECT/SHOW/WITH/DESC/EXPLAIN）", "columns": [], "rows": []}

    can_wrap = lowered.startswith(("select", "with"))
    st = conn_info["source_type"]
    limit = max(1, min(int(limit), 5000))

    if _is_mysql_family(st):
        with mysql_conn(conn_info) as conn, conn.cursor() as cursor:
            if can_wrap:
                cursor.execute(f"SELECT * FROM ({sql_clean}) __chatbi_sub LIMIT %s", (limit,))
            else:
                cursor.execute(sql_clean)
            rows = list(cursor.fetchall())[:limit]
            columns = list(rows[0].keys()) if rows else [d[0] for d in (cursor.description or [])]
            return _normalize_query_result(columns, rows)

    if _is_postgres_family(st):
        with postgres_conn(conn_info) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if can_wrap:
                cursor.execute(f"SELECT * FROM ({sql_clean}) AS __chatbi_sub LIMIT %s", (limit,))
            else:
                cursor.execute(sql_clean)
            rows = list(cursor.fetchall())[:limit]
            columns = list(rows[0].keys()) if rows else [d[0] for d in (cursor.description or [])]
            return _normalize_query_result(columns, rows)

    if st == "sqlserver":
        with sqlserver_conn(conn_info) as conn, conn.cursor() as cursor:
            if can_wrap:
                cursor.execute(f"SELECT TOP ({limit}) * FROM ({sql_clean}) AS __chatbi_sub")
            else:
                cursor.execute(sql_clean)
            rows = cursor.fetchall()
            rows = rows[:limit] if rows else []
            columns = list(rows[0].keys()) if rows else [d[0] for d in (cursor.description or [])]
            return _normalize_query_result(columns, [dict(r) for r in rows])

    if st == "sqlite":
        with sqlite_conn(conn_info) as conn, _sqlite_cursor(conn) as cursor:
            if can_wrap:
                cursor.execute(f"SELECT * FROM ({sql_clean}) LIMIT {limit}")
            else:
                cursor.execute(sql_clean)
            rows = cursor.fetchall()
            rows = rows[:limit]
            columns = list(rows[0].keys()) if rows else [d[0] for d in (cursor.description or [])]
            return _normalize_query_result(columns, [dict(r) for r in rows])

    if st == "trino":
        conn = _trino_connection(conn_info)
        cur = conn.cursor()
        if can_wrap:
            cur.execute(f"SELECT * FROM ({sql_clean}) AS __chatbi_sub LIMIT {limit}")
        else:
            cur.execute(sql_clean)
        cols = [d[0] for d in cur.description] if cur.description else []
        data = cur.fetchmany(limit)
        conn.close()
        rows = [dict(zip(cols, row)) for row in data]
        return _normalize_query_result(cols, rows)

    if st == "clickhouse":
        client = _clickhouse_client(conn_info)
        if can_wrap:
            data, cols = client.execute(f"SELECT * FROM ({sql_clean}) LIMIT {limit}", with_column_types=True)
        else:
            data, cols = client.execute(sql_clean, with_column_types=True)
            data = data[:limit]
        col_names = [c[0] for c in cols]
        rows = [dict(zip(col_names, row)) for row in data]
        return _normalize_query_result(col_names, rows)

    if st == "hive":
        with hive_conn(conn_info) as conn:
            cur = conn.cursor()
            if can_wrap:
                cur.execute(f"SELECT * FROM ({sql_clean}) hive_sub LIMIT {limit}")
            else:
                cur.execute(sql_clean)
            cols = [d[0] for d in (cur.description or [])]
            data = cur.fetchmany(limit)
            rows = [dict(zip(cols, row)) for row in (data or [])]
            return _normalize_query_result(cols, rows)

    return {"ok": False, "error": f"不支持的数据源类型: {st}", "columns": [], "rows": [], "row_count": 0}
