from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import ColumnMeta, DataSource, TableMeta, TableSummary
from routers.analyze import schedule_table_analyze
from services.schema_extractor import get_columns, get_databases, get_tables, get_tables_for_database, get_tables_meta_for_database

router = APIRouter(prefix="/api", tags=["datasources"])


class DataSourceBody(BaseModel):
    name: str
    source_type: str
    description: str | None = None
    host: str
    port: int
    database: str
    username: str
    password: str


SUMMARY_SECTION_TITLES = {"业务描述", "数据定位", "核心口径", "使用建议", "风险边界"}


def _extract_business_description(summary_text: str) -> str:
    text = (summary_text or "").replace("\r", "").strip()
    if not text:
        return ""
    lines = text.split("\n")
    in_business_section = False
    items: list[str] = []
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed == "业务描述":
            in_business_section = True
            continue
        if in_business_section and trimmed in SUMMARY_SECTION_TITLES and trimmed != "业务描述":
            break
        if in_business_section:
            if trimmed.startswith("- "):
                trimmed = trimmed[2:].strip()
            elif trimmed.startswith(("*", "•")):
                trimmed = trimmed[1:].strip()
            if trimmed:
                items.append(trimmed)
    if items:
        return "；".join(items)
    return text.split("\n")[0].strip()


def _datasource_to_dict(r: DataSource) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "source_type": r.source_type,
        "description": r.description,
        "host": r.host,
        "port": r.port,
        "database": r.database,
        "username": r.username,
    }


@router.get("/datasources")
def list_datasources(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(DataSource).order_by(DataSource.created_at.desc())).scalars().all()
    return {"datasources": [_datasource_to_dict(r) for r in rows]}


@router.get("/datasources/{datasource_id}")
def get_datasource(datasource_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    return {"datasource": _datasource_to_dict(row)}


@router.post("/datasources")
def create_datasource(body: DataSourceBody, db: Session = Depends(get_db)) -> dict:
    row = DataSource(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/datasources/{datasource_id}")
def update_datasource(datasource_id: int, body: DataSourceBody, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return {"success": True}


@router.delete("/datasources/{datasource_id}")
def delete_datasource(datasource_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    db.delete(row)
    db.commit()
    return {"success": True}


@router.post("/datasources/test")
def test_datasource_connection(body: DataSourceBody) -> dict:
    try:
        tables = get_tables(body.model_dump())
        return {"success": True, "tables_count": len(tables), "sample_tables": tables[:5]}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


@router.post("/datasources/{datasource_id}/test")
def test_saved_datasource_connection(datasource_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    payload = {
        "source_type": row.source_type,
        "host": row.host,
        "port": row.port,
        "database": row.database,
        "username": row.username,
        "password": row.password,
    }
    try:
        tables = get_tables(payload)
        return {"success": True, "tables_count": len(tables), "sample_tables": tables[:5]}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


def _conn_payload(row: DataSource) -> dict:
    return {
        "source_type": row.source_type,
        "host": row.host,
        "port": row.port,
        "database": row.database,
        "username": row.username,
        "password": row.password,
    }


def _conn_payload_with_database(row: DataSource, database_name: str) -> dict:
    payload = _conn_payload(row)
    payload["database"] = database_name
    return payload


@router.get("/datasources/{datasource_id}/catalog")
def get_datasource_catalog(datasource_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    conn_info = _conn_payload(row)
    db_names = get_databases(conn_info)
    analyzed = (
        db.execute(
            select(TableMeta).where(TableMeta.datasource_id == datasource_id).order_by(TableMeta.created_at.desc())
        )
        .scalars()
        .all()
    )
    latest_status: dict[str, str] = {}
    latest_table_id: dict[str, int] = {}
    for t in analyzed:
        key = f"{t.database_name}.{t.table_name}"
        if key not in latest_status:
            latest_status[key] = t.status
            latest_table_id[key] = t.id

    databases = []
    for db_name in db_names:
        tables = get_tables_for_database(conn_info, db_name)
        databases.append(
            {
                "name": db_name,
                "description": f"{db_name} 数据库，包含 {len(tables)} 张表",
            }
        )
    return {
        "datasource": {
            "id": row.id,
            "name": row.name,
            "database": row.database,
            "source_type": row.source_type,
            "description": row.description,
        },
        "databases": databases,
    }


@router.get("/datasources/{datasource_id}/databases/{database_name}/catalog")
def get_database_catalog(datasource_id: int, database_name: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")

    conn_info = _conn_payload(row)
    tables_meta = get_tables_meta_for_database(conn_info, database_name)
    analyzed = (
        db.execute(
            select(TableMeta)
            .where(TableMeta.datasource_id == datasource_id, TableMeta.database_name == database_name)
            .order_by(TableMeta.created_at.desc())
        )
        .scalars()
        .all()
    )
    latest_status: dict[str, str] = {}
    latest_table_id: dict[str, int] = {}
    latest_analyzed_at: dict[str, str] = {}
    ai_summary: dict[str, str] = {}
    for t in analyzed:
        if t.table_name not in latest_status:
            latest_status[t.table_name] = t.status
            latest_table_id[t.table_name] = t.id
            latest_analyzed_at[t.table_name] = t.created_at.isoformat() if t.created_at else ""

    table_ids = list(latest_table_id.values())
    summary_by_table_id: dict[int, TableSummary] = {}
    if table_ids:
        summary_rows = (
            db.execute(select(TableSummary).where(TableSummary.table_id.in_(table_ids))).scalars().all()
        )
        for srow in summary_rows:
            prev = summary_by_table_id.get(srow.table_id)
            if prev is None:
                summary_by_table_id[srow.table_id] = srow
            elif srow.generated_at and (not prev.generated_at or srow.generated_at > prev.generated_at):
                summary_by_table_id[srow.table_id] = srow

    for name, tid in latest_table_id.items():
        summary = summary_by_table_id.get(tid)
        if summary and summary.generated_at:
            latest_analyzed_at[name] = summary.generated_at.isoformat()
        ai_summary[name] = _extract_business_description(summary.summary if summary and summary.summary else "")

    return {
        "datasource": {"id": row.id, "name": row.name},
        "database": {"name": database_name, "description": f"{database_name} 数据库，包含 {len(tables_meta)} 张表"},
        "tables": [
            {
                "name": t["name"],
                "comment": t.get("comment", ""),
                "status": latest_status.get(t["name"], "pending"),
                "latest_analyzed_at": latest_analyzed_at.get(t["name"], ""),
                "ai_analysis": ai_summary.get(t["name"], ""),
                "table_id": latest_table_id.get(t["name"]),
            }
            for t in tables_meta
        ],
    }


@router.post("/datasources/{datasource_id}/analyze/table/{table_name}")
def analyze_table_by_datasource(
    datasource_id: int, table_name: str, database_name: str | None = None, db: Session = Depends(get_db)
) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    target_database = database_name or row.database
    table_id = schedule_table_analyze(
        db,
        table_name,
        _conn_payload_with_database(row, target_database),
        row.source_type,
        target_database,
        datasource_id,
    )
    return {"scope": "table", "table_id": table_id, "status": "analyzing"}


@router.post("/datasources/{datasource_id}/analyze/database/{database_name}")
def analyze_database_by_datasource(datasource_id: int, database_name: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    conn = _conn_payload_with_database(row, database_name)
    tables = get_tables_for_database(conn, database_name)
    ids = [schedule_table_analyze(db, t, conn, row.source_type, database_name, datasource_id) for t in tables]
    return {"scope": "database", "database": database_name, "table_ids": ids, "count": len(ids), "status": "analyzing"}


@router.post("/datasources/{datasource_id}/analyze/datasource")
def analyze_datasource(datasource_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")
    conn = _conn_payload(row)
    all_ids: list[int] = []
    db_count = 0
    for db_name in get_databases(conn):
        db_count += 1
        db_conn = _conn_payload_with_database(row, db_name)
        for table_name in get_tables_for_database(db_conn, db_name):
            all_ids.append(schedule_table_analyze(db, table_name, db_conn, row.source_type, db_name, datasource_id))
    return {"scope": "datasource", "databases_count": db_count, "table_ids": all_ids, "count": len(all_ids), "status": "analyzing"}


@router.get("/datasources/{datasource_id}/tables/{table_name}/columns")
def get_table_columns(datasource_id: int, table_name: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(DataSource, datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="datasource not found")

    source_columns = get_columns(_conn_payload_with_database(row, row.database), table_name)
    latest_table = (
        db.execute(
            select(TableMeta)
            .where(TableMeta.datasource_id == datasource_id, TableMeta.table_name == table_name)
            .order_by(TableMeta.created_at.desc())
        )
        .scalars()
        .first()
    )
    semantic_map: dict[str, dict] = {}
    if latest_table:
        semantic_rows = db.execute(select(ColumnMeta).where(ColumnMeta.table_id == latest_table.id)).scalars().all()
        semantic_map = {
            c.column_name: {"semantic_desc": c.semantic_desc or "", "semantic_type": c.semantic_type or "", "comment": c.comment or ""}
            for c in semantic_rows
        }

    columns = []
    for col in source_columns:
        sem = semantic_map.get(col["column_name"], {})
        columns.append(
            {
                "column_name": col["column_name"],
                "data_type": col.get("data_type", ""),
                "comment": sem.get("comment") or col.get("comment", ""),
                "semantic_desc": sem.get("semantic_desc", ""),
                "semantic_type": sem.get("semantic_type", ""),
            }
        )
    return {"table_name": table_name, "columns": columns}
