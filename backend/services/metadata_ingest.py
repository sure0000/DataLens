"""数据库元数据自动导入：添加数据源时提取 TABLE/COLUMN COMMENT 为知识条目。"""

import threading
from datetime import datetime

from database import SessionLocal
from models import DataSource, KnowledgeBase, KnowledgeEntry
from services.entry_service import create_entry
from services.schema_extractor import get_columns, get_tables_meta_for_database


def _create_metadata_kb(db, ds_name: str) -> KnowledgeBase:
    """为数据源创建专属元数据知识库（如已存在同名知识库则复用）。"""
    from sqlalchemy import select

    existing = db.execute(
        select(KnowledgeBase).where(KnowledgeBase.name == f"{ds_name} 元数据")
    ).scalar_one_or_none()
    if existing:
        return existing
    kb = KnowledgeBase(
        name=f"{ds_name} 元数据",
        description=f"数据源「{ds_name}」的表与字段元数据，由系统自动导入。",
        created_at=datetime.utcnow(),
    )
    db.add(kb)
    db.flush()
    return kb


def _metadata_info(conn_info: dict) -> list[dict]:
    """从数据源提取完整的表+列元数据，返回 Markdown 条目列表。"""
    items: list[dict] = []
    databases: list[str] = []

    source_type = conn_info.get("source_type", "")
    database = conn_info.get("database", "")

    if source_type in ("trino", "hive", "clickhouse"):
        from services.schema_extractor import get_databases as _get_dbs

        dbs = _get_dbs(conn_info)
        databases = [d for d in dbs if d]
    elif database:
        databases = [database]

    if not databases:
        databases = [database] if database else []

    for db_name in databases:
        db_conn = {**conn_info, "database": db_name}
        try:
            tables = get_tables_meta_for_database(db_conn, db_name)
        except Exception:
            continue

        for tbl in tables:
            tbl_name = tbl["name"]
            tbl_comment = tbl.get("comment", "")
            try:
                cols = get_columns({**db_conn, "database": db_name}, tbl_name)
            except Exception:
                cols = []

            # 构建 Markdown 条目
            parts = [f"# {tbl_name}"]
            if tbl_comment:
                parts.append(f"\n**表说明**: {tbl_comment}")

            if cols:
                parts.append("\n## 字段列表\n")
                parts.append("| 字段名 | 类型 | 说明 |")
                parts.append("|--------|------|------|")
                for c in cols:
                    cname = c.get("column_name", "")
                    ctype = c.get("data_type", "")
                    ccomment = c.get("comment", "") or ""
                    parts.append(f"| {cname} | {ctype} | {ccomment} |")
            else:
                parts.append("\n（暂无字段元数据）")

            body = "\n".join(parts)
            items.append({
                "title": tbl_name,
                "body": body,
                "source_meta": {
                    "kind": "database_metadata",
                    "database": db_name,
                    "table_name": tbl_name,
                    "label": "数据库元数据",
                },
            })

    return items


def run_metadata_ingest_for_datasource(datasource_id: int) -> None:
    """后台执行：为数据源提取元数据并写入知识库。"""

    def _run():
        db = SessionLocal()
        try:
            ds = db.get(DataSource, datasource_id)
            if not ds:
                return

            conn_info = {
                "source_type": ds.source_type,
                "host": ds.host,
                "port": ds.port,
                "database": ds.database,
                "username": ds.username,
                "password": ds.password,
            }

            items = _metadata_info(conn_info)
            if not items:
                return

            kb = _create_metadata_kb(db, ds.name)

            for item in items:
                create_entry(
                    db,
                    kb.id,
                    item["title"],
                    item["body"],
                    source_meta=item["source_meta"],
                )

            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True, name=f"metadata-ingest-ds-{datasource_id}")
    t.start()
