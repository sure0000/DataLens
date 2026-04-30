from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database import get_db
from models import (
    BusinessDomain,
    BusinessDomainDescription,
    BusinessDomainKnowledgeBase,
    BusinessDomainSelection,
    DataSource,
    KnowledgeBase,
    TableMeta,
    TableSummary,
)
from services.schema_extractor import get_databases, get_tables_meta_for_database

router = APIRouter(prefix="/api/business-domains", tags=["business-domains"])


class SelectionInput(BaseModel):
    datasource_id: int
    database_name: str
    table_names: list[str] = []


class DomainCreateBody(BaseModel):
    name: str
    description: str = ""
    descriptions: list[str] = []
    selections: list[SelectionInput] = []


class DescriptionCreateBody(BaseModel):
    content: str


class DomainKnowledgeBasesBody(BaseModel):
    knowledge_base_ids: list[int] = []


def _latest_description_map(db: Session) -> dict[int, BusinessDomainDescription]:
    desc_rows = (
        db.execute(select(BusinessDomainDescription).order_by(BusinessDomainDescription.created_at.desc()))
        .scalars()
        .all()
    )
    latest: dict[int, BusinessDomainDescription] = {}
    for row in desc_rows:
        if row.domain_id not in latest:
            latest[row.domain_id] = row
    return latest


def _set_single_description(db: Session, domain_id: int, content: str) -> BusinessDomainDescription:
    desc_rows = (
        db.execute(select(BusinessDomainDescription).where(BusinessDomainDescription.domain_id == domain_id))
        .scalars()
        .all()
    )
    if desc_rows:
        primary = desc_rows[0]
        primary.content = content
        for extra in desc_rows[1:]:
            db.delete(extra)
        db.flush()
        return primary
    row = BusinessDomainDescription(domain_id=domain_id, content=content)
    db.add(row)
    db.flush()
    return row


@router.get("/options")
def list_domain_options(db: Session = Depends(get_db)) -> dict:
    sources = db.execute(select(DataSource).order_by(DataSource.created_at.desc())).scalars().all()
    items = []
    for s in sources:
        conn_info = {
            "source_type": s.source_type,
            "host": s.host,
            "port": s.port,
            "database": s.database,
            "username": s.username,
            "password": s.password,
        }
        try:
            databases = []
            for db_name in get_databases(conn_info):
                tables = get_tables_meta_for_database(conn_info, db_name)
                databases.append(
                    {
                        "name": db_name,
                        "tables": [{"name": t["name"], "comment": t.get("comment", "")} for t in tables],
                    }
                )
        except Exception:  # noqa: BLE001
            databases = []
        items.append(
            {
                "id": s.id,
                "name": s.name,
                "source_type": s.source_type,
                "description": s.description or "",
                "databases": databases,
            }
        )
    return {"datasources": items}


@router.get("")
def list_domains(db: Session = Depends(get_db)) -> dict:
    domains = db.execute(select(BusinessDomain).order_by(BusinessDomain.created_at.desc())).scalars().all()
    latest_desc_map = _latest_description_map(db)
    sel_rows = db.execute(select(BusinessDomainSelection)).scalars().all()
    source_map = {s.id: s for s in db.execute(select(DataSource)).scalars().all()}

    sel_map: dict[int, list[dict]] = defaultdict(list)
    for row in sel_rows:
        source = source_map.get(row.datasource_id)
        sel_map[row.domain_id].append(
            {
                "datasource_id": row.datasource_id,
                "datasource_name": source.name if source else f"#{row.datasource_id}",
                "database_name": row.database_name,
                "table_name": row.table_name,
            }
        )

    return {
        "domains": [
            {
                "id": d.id,
                "name": d.name,
                "description": (latest_desc_map[d.id].content if d.id in latest_desc_map else ""),
                "selections": sel_map.get(d.id, []),
                "created_at": d.created_at.isoformat() if d.created_at else "",
            }
            for d in domains
        ]
    }


@router.get("/{domain_id}")
def get_domain_detail(domain_id: int, db: Session = Depends(get_db)) -> dict:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")

    desc_rows = (
        db.execute(
            select(BusinessDomainDescription)
            .where(BusinessDomainDescription.domain_id == domain_id)
            .order_by(BusinessDomainDescription.created_at.desc())
        )
        .scalars()
        .all()
    )
    sel_rows = db.execute(select(BusinessDomainSelection).where(BusinessDomainSelection.domain_id == domain_id)).scalars().all()
    source_map = {s.id: s for s in db.execute(select(DataSource)).scalars().all()}

    # Resolve to concrete table rows for page display.
    table_rows: list[dict] = []
    analysis_cache: dict[tuple[int, str], dict[str, dict[str, object]]] = {}
    for sel in sel_rows:
        source = source_map.get(sel.datasource_id)
        if not source:
            continue
        conn_info = {
            "source_type": source.source_type,
            "host": source.host,
            "port": source.port,
            "database": source.database,
            "username": source.username,
            "password": source.password,
        }
        try:
            tables_meta = get_tables_meta_for_database(conn_info, sel.database_name)
        except Exception:  # noqa: BLE001
            tables_meta = []
        comment_map = {t["name"]: t.get("comment", "") for t in tables_meta}
        cache_key = (source.id, sel.database_name)
        if cache_key not in analysis_cache:
            table_meta_rows = (
                db.execute(
                    select(TableMeta).where(
                        TableMeta.datasource_id == source.id,
                        TableMeta.database_name == sel.database_name,
                    )
                )
                .scalars()
                .all()
            )
            latest_table_id_by_name: dict[str, int] = {}
            latest_created_at_by_name: dict[str, object] = {}
            for tm in table_meta_rows:
                created_at = tm.created_at
                prev = latest_created_at_by_name.get(tm.table_name)
                if prev is None or (created_at and prev and created_at > prev) or (created_at and prev is None):
                    latest_created_at_by_name[tm.table_name] = created_at
                    latest_table_id_by_name[tm.table_name] = tm.id

            summary_map: dict[int, str] = {}
            if latest_table_id_by_name:
                summary_rows = (
                    db.execute(select(TableSummary).where(TableSummary.table_id.in_(list(latest_table_id_by_name.values()))))
                    .scalars()
                    .all()
                )
                for summary in summary_rows:
                    summary_map[summary.table_id] = summary.summary or ""

            analysis_cache[cache_key] = {
                table_name: {"description": summary_map.get(table_id, ""), "table_id": table_id}
                for table_name, table_id in latest_table_id_by_name.items()
            }
        table_analysis_map = analysis_cache.get(cache_key, {})

        if sel.table_name:
            table_cache = table_analysis_map.get(sel.table_name, {})
            table_rows.append(
                {
                    "datasource_id": source.id,
                    "datasource_name": source.name,
                    "database_name": sel.database_name,
                    "table_name": sel.table_name,
                    "table_comment": comment_map.get(sel.table_name, ""),
                    "table_description": str(table_cache.get("description", "") or ""),
                    "table_id": table_cache.get("table_id"),
                }
            )
        else:
            for t in tables_meta:
                table_cache = table_analysis_map.get(t["name"], {})
                table_rows.append(
                    {
                        "datasource_id": source.id,
                        "datasource_name": source.name,
                        "database_name": sel.database_name,
                        "table_name": t["name"],
                        "table_comment": t.get("comment", ""),
                        "table_description": str(table_cache.get("description", "") or ""),
                        "table_id": table_cache.get("table_id"),
                    }
                )

    unique_rows = {}
    for row in table_rows:
        key = (row["datasource_id"], row["database_name"], row["table_name"])
        unique_rows[key] = row
    sorted_rows = sorted(unique_rows.values(), key=lambda r: (r["database_name"], r["table_name"]))

    kb_link_rows = (
        db.execute(select(BusinessDomainKnowledgeBase).where(BusinessDomainKnowledgeBase.domain_id == domain_id)).scalars().all()
    )
    kb_ids = [r.knowledge_base_id for r in kb_link_rows]
    kb_rows = (
        db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)).order_by(KnowledgeBase.name.asc())).scalars().all()
        if kb_ids
        else []
    )

    return {
        "domain": {
            "id": domain.id,
            "name": domain.name,
            "created_at": domain.created_at.isoformat() if domain.created_at else "",
        },
        "description": (
            {
                "id": desc_rows[0].id,
                "content": desc_rows[0].content,
                "created_at": desc_rows[0].created_at.isoformat() if desc_rows[0].created_at else "",
            }
            if desc_rows
            else None
        ),
        "tables": sorted_rows,
        "knowledge_bases": [{"id": kb.id, "name": kb.name, "description": kb.description or ""} for kb in kb_rows],
    }


@router.put("/{domain_id}/knowledge-bases")
def set_domain_knowledge_bases(domain_id: int, body: DomainKnowledgeBasesBody, db: Session = Depends(get_db)) -> dict:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")
    seen: set[int] = set()
    ordered_ids: list[int] = []
    for kb_id in body.knowledge_base_ids:
        if kb_id in seen:
            continue
        seen.add(kb_id)
        ordered_ids.append(kb_id)
    for kb_id in ordered_ids:
        if not db.get(KnowledgeBase, kb_id):
            raise HTTPException(status_code=400, detail=f"knowledge base not found: {kb_id}")
    db.execute(delete(BusinessDomainKnowledgeBase).where(BusinessDomainKnowledgeBase.domain_id == domain_id))
    for kb_id in ordered_ids:
        db.add(BusinessDomainKnowledgeBase(domain_id=domain_id, knowledge_base_id=kb_id))
    db.commit()
    return {"ok": True, "knowledge_base_ids": ordered_ids}


@router.post("")
def create_domain(body: DomainCreateBody, db: Session = Depends(get_db)) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="domain name is required")

    domain = BusinessDomain(name=name)
    db.add(domain)
    db.commit()
    db.refresh(domain)

    description = (body.description or "").strip()
    if not description:
        description = next((d.strip() for d in body.descriptions if d.strip()), "")
    if description:
        db.add(BusinessDomainDescription(domain_id=domain.id, content=description))

    for selection in body.selections:
        tables = sorted(set([t.strip() for t in selection.table_names if t.strip()]))
        if tables:
            for t in tables:
                db.add(
                    BusinessDomainSelection(
                        domain_id=domain.id,
                        datasource_id=selection.datasource_id,
                        database_name=selection.database_name,
                        table_name=t,
                    )
                )
        else:
            db.add(
                BusinessDomainSelection(
                    domain_id=domain.id,
                    datasource_id=selection.datasource_id,
                    database_name=selection.database_name,
                    table_name=None,
                )
            )

    db.commit()
    return {"id": domain.id}


@router.post("/{domain_id}/descriptions")
def add_domain_description(domain_id: int, body: DescriptionCreateBody, db: Session = Depends(get_db)) -> dict:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="description content is required")
    row = _set_single_description(db, domain_id, content)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/{domain_id}/description")
def upsert_domain_description(domain_id: int, body: DescriptionCreateBody, db: Session = Depends(get_db)) -> dict:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="description content is required")
    row = _set_single_description(db, domain_id, content)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "success": True}


@router.put("/{domain_id}/descriptions/{description_id}")
def update_domain_description(domain_id: int, description_id: int, body: DescriptionCreateBody, db: Session = Depends(get_db)) -> dict:
    row = db.get(BusinessDomainDescription, description_id)
    if not row or row.domain_id != domain_id:
        raise HTTPException(status_code=404, detail="description not found")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="description content is required")
    _set_single_description(db, domain_id, content)
    db.commit()
    return {"success": True}


@router.post("/{domain_id}/selections")
def add_domain_selections(domain_id: int, body: list[SelectionInput], db: Session = Depends(get_db)) -> dict:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")

    added = 0
    for selection in body:
        db_key_filter = (
            BusinessDomainSelection.domain_id == domain_id,
            BusinessDomainSelection.datasource_id == selection.datasource_id,
            BusinessDomainSelection.database_name == selection.database_name,
        )
        tables = sorted(set([t.strip() for t in selection.table_names if t.strip()]))
        if tables:
            # remove whole-database selection so table-level can take effect
            db.execute(delete(BusinessDomainSelection).where(*db_key_filter, BusinessDomainSelection.table_name.is_(None)))
            for t in tables:
                exists = db.execute(
                    select(BusinessDomainSelection).where(*db_key_filter, BusinessDomainSelection.table_name == t)
                ).scalar_one_or_none()
                if exists:
                    continue
                db.add(
                    BusinessDomainSelection(
                        domain_id=domain_id,
                        datasource_id=selection.datasource_id,
                        database_name=selection.database_name,
                        table_name=t,
                    )
                )
                added += 1
        else:
            # whole-database selection overrides table-level selection
            db.execute(delete(BusinessDomainSelection).where(*db_key_filter))
            db.add(
                BusinessDomainSelection(
                    domain_id=domain_id,
                    datasource_id=selection.datasource_id,
                    database_name=selection.database_name,
                    table_name=None,
                )
            )
            added += 1
    db.commit()
    return {"success": True, "added": added}


@router.delete("/{domain_id}")
def delete_domain(domain_id: int, db: Session = Depends(get_db)) -> dict:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")
    db.execute(delete(BusinessDomainDescription).where(BusinessDomainDescription.domain_id == domain_id))
    db.execute(delete(BusinessDomainSelection).where(BusinessDomainSelection.domain_id == domain_id))
    db.execute(delete(BusinessDomainKnowledgeBase).where(BusinessDomainKnowledgeBase.domain_id == domain_id))
    db.delete(domain)
    db.commit()
    return {"success": True}
