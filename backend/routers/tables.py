from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import BusinessDomain, BusinessDomainSelection, ColumnMeta, DataSource, TableMeta, TableSummary

router = APIRouter(prefix="/api", tags=["tables"])
SUMMARY_SECTIONS = ["业务描述", "数据定位", "核心口径", "使用建议", "风险边界"]


def _fallback_quality_metrics(null_ratio: float | None, distinct_count: int | None, top_values: list | None, row_count: int | None) -> dict:
    rows = row_count or 0
    non_null_est = max(rows - int((null_ratio or 0) * rows), 0) if rows else 0
    duplicate_ratio = 0.0
    if non_null_est > 0 and distinct_count is not None:
        duplicate_ratio = max(0.0, 1 - (distinct_count / non_null_est))

    top1_ratio = 0.0
    if top_values and non_null_est > 0 and isinstance(top_values[0], dict):
        count = top_values[0].get("count")
        if isinstance(count, int):
            top1_ratio = count / non_null_est

    risk = "low"
    if (null_ratio or 0) > 0.2 or duplicate_ratio > 0.3:
        risk = "high"
    elif (null_ratio or 0) > 0.05 or duplicate_ratio > 0.1 or top1_ratio > 0.9:
        risk = "medium"

    return {
        "duplicate_ratio": round(duplicate_ratio, 6),
        "top1_ratio": round(top1_ratio, 6),
        "completeness_score": round(1 - (null_ratio or 0), 6),
        "risk_level": risk,
    }


def _parse_summary_sections(raw_summary: str) -> list[dict]:
    parsed: dict[str, list[str]] = {section: [] for section in SUMMARY_SECTIONS}
    current = ""
    for line in (raw_summary or "").replace("\r", "").split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed in parsed:
            current = trimmed
            continue
        if current:
            bullet = trimmed[2:].strip() if trimmed.startswith("- ") else trimmed
            if bullet:
                parsed[current].append(bullet)
    return [{"title": title, "items": parsed[title]} for title in SUMMARY_SECTIONS]


@router.get("/tables")
def list_tables(
    datasource_id: int | None = Query(default=None), database_name: str | None = Query(default=None), db: Session = Depends(get_db)
) -> dict:
    stmt = select(TableMeta).order_by(TableMeta.created_at.desc())
    if datasource_id is not None:
        stmt = stmt.where(TableMeta.datasource_id == datasource_id)
    if database_name:
        stmt = stmt.where(TableMeta.database_name == database_name)
    rows = db.execute(stmt).scalars().all()
    return {
        "tables": [
            {
                "id": r.id,
                "table_name": r.table_name,
                "database_name": r.database_name,
                "datasource_id": r.datasource_id,
                "row_count": r.row_count,
                "status": r.status,
            }
            for r in rows
        ]
    }


@router.get("/table/{table_id}")
def get_table_detail(table_id: int, db: Session = Depends(get_db)) -> dict:
    table = db.get(TableMeta, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="table not found")
    cols = db.execute(select(ColumnMeta).where(ColumnMeta.table_id == table_id)).scalars().all()
    summary = db.execute(select(TableSummary).where(TableSummary.table_id == table_id)).scalar_one_or_none()
    summary_text = summary.summary if summary else ""

    # Resolve datasource name
    datasource_name = ""
    if table.datasource_id:
        ds = db.get(DataSource, table.datasource_id)
        if ds:
            datasource_name = ds.name

    # Resolve associated business domains
    domain_names: list[str] = []
    if table.datasource_id:
        sel_rows = (
            db.execute(
                select(BusinessDomainSelection).where(
                    BusinessDomainSelection.datasource_id == table.datasource_id,
                    BusinessDomainSelection.database_name == table.database_name,
                    (
                        (BusinessDomainSelection.table_name == table.table_name)
                        | (BusinessDomainSelection.table_name.is_(None))
                    ),
                )
            )
            .scalars()
            .all()
        )
        if sel_rows:
            domain_ids = list(dict.fromkeys([r.domain_id for r in sel_rows]))
            domains = db.execute(select(BusinessDomain).where(BusinessDomain.id.in_(domain_ids))).scalars().all()
            domain_names = [d.name for d in domains]

    return {
        "table": {
            "id": table.id,
            "table_name": table.table_name,
            "database_name": table.database_name,
            "datasource_name": datasource_name,
            "row_count": table.row_count,
            "status": table.status,
            "domain_names": domain_names,
        },
        "columns": [
            {
                "column_name": c.column_name,
                "data_type": c.data_type,
                "semantic_desc": c.semantic_desc,
                "semantic_type": c.semantic_type,
                "is_usable": c.is_usable,
                "null_ratio": c.null_ratio,
                "distinct_count": c.distinct_count,
                "top_values": c.top_values or [],
                "quality_metrics": c.quality_metrics
                or _fallback_quality_metrics(c.null_ratio, c.distinct_count, c.top_values, table.row_count),
            }
            for c in cols
        ],
        "summary": {
            "summary": summary_text,
            "sections": _parse_summary_sections(summary_text),
            "use_cases": summary.use_cases.split("|") if summary and summary.use_cases else [],
            "key_columns": summary.key_columns.split("|") if summary and summary.key_columns else [],
            "warnings": summary.warnings if summary else "",
        },
    }
