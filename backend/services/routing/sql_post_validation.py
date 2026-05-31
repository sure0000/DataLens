"""P2-4 生成后 SQL 校验：trust 标签驱动 review / 跳过自动执行。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models import DataSource, TableMeta
from services.context_builder import resolve_table_meta_for_trace, tables_from_business_domain
from services.sql_ast_guard import extract_table_refs_from_sql, source_type_to_sqlglot_dialect


def evaluate_sql_execution_review(
    db: Session,
    *,
    sql_text: str,
    business_domain_id: int | None,
    candidate_table_ids: list[int],
    table_id: int | None,
    ds_anchor: DataSource | None,
    default_db: str | None,
) -> dict[str, Any]:
    """解析 SQL 引用表，对比域挂载与路由候选集，决定是否需人工 review。"""
    out: dict[str, Any] = {
        "review_required": False,
        "trust_level": "high",
        "reasons": [],
        "sql_table_ids": [],
        "out_of_domain_table_ids": [],
        "outside_candidate_table_ids": [],
        "execution_mode": "auto",
    }
    sql = (sql_text or "").strip()
    if not sql or ds_anchor is None:
        return out

    dialect = source_type_to_sqlglot_dialect(ds_anchor.source_type) or "mysql"
    refs = extract_table_refs_from_sql(sql, dialect=dialect)
    sql_tables: list[TableMeta] = []
    seen: set[int] = set()
    for _cat, dbp, name in refs:
        tm = resolve_table_meta_for_trace(
            db,
            datasource_id=int(ds_anchor.id),
            default_database=default_db,
            db_part=dbp,
            table_name=name,
        )
        if tm and tm.id not in seen:
            seen.add(tm.id)
            sql_tables.append(tm)

    sql_ids = [t.id for t in sql_tables]
    out["sql_table_ids"] = sql_ids
    if not sql_ids:
        out["trust_level"] = "medium"
        return out

    domain_ids: set[int] = set()
    if business_domain_id:
        domain_ids = {t.id for t in tables_from_business_domain(db, business_domain_id)}

    out_of_domain: list[int] = []
    if domain_ids:
        out_of_domain = [tid for tid in sql_ids if tid not in domain_ids]
        out["out_of_domain_table_ids"] = out_of_domain
        if out_of_domain:
            out["reasons"].append(
                f"SQL 解析表 table_id={out_of_domain} 不在业务域挂载表范围内"
            )
            if len(out_of_domain) >= len(sql_ids):
                out["review_required"] = True
                out["trust_level"] = "review"
                out["execution_mode"] = "review"
            else:
                out["trust_level"] = "medium"
                out["reasons"].append("部分引用表不在业务域挂载范围内，结果请人工核对")

    candidate_set = set(candidate_table_ids or [])
    if table_id:
        candidate_set.add(table_id)
    outside_candidate: list[int] = []
    if candidate_set:
        outside_candidate = [tid for tid in sql_ids if tid not in candidate_set]
        out["outside_candidate_table_ids"] = outside_candidate
        if outside_candidate and len(outside_candidate) >= len(sql_ids):
            out["review_required"] = True
            out["trust_level"] = "review"
            out["execution_mode"] = "review"
            out["reasons"].append(
                "SQL 引用表均不在路由候选集内，建议确认后再执行"
            )
        elif outside_candidate:
            out["trust_level"] = "medium"
            out["reasons"].append(
                f"部分引用表 table_id={outside_candidate} 不在路由候选集内"
            )

    if not out["review_required"] and len(sql_ids) > 1:
        out["trust_level"] = "medium-high"

    return out
