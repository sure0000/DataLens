from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from database import get_db
from models import (
    BusinessDomain,
    BusinessDomainDescription,
    BusinessDomainKnowledgeBase,
    BusinessDomainSelection,
    DataSource,
    KnowledgeBase,
)

TEMPORARY_DOMAIN_NAME = "临时域"
DOMAIN_HEADER = "X-Business-Domain-Id"


def ensure_temporary_domain(db: Session) -> BusinessDomain:
    rows = (
        db.execute(
            select(BusinessDomain)
            .where(BusinessDomain.name == TEMPORARY_DOMAIN_NAME)
            .order_by(BusinessDomain.id.asc())
        )
        .scalars()
        .all()
    )
    if rows:
        if len(rows) == 1:
            return rows[0]
        score_by_domain_id: dict[int, int] = {}
        for row in rows:
            domain_id = row.id
            ref_count = 0
            ref_count += db.execute(
                select(func.count()).select_from(DataSource).where(DataSource.business_domain_id == domain_id)
            ).scalar_one()
            ref_count += db.execute(
                select(func.count()).select_from(KnowledgeBase).where(KnowledgeBase.business_domain_id == domain_id)
            ).scalar_one()
            ref_count += db.execute(
                select(func.count()).select_from(BusinessDomainSelection).where(BusinessDomainSelection.domain_id == domain_id)
            ).scalar_one()
            ref_count += db.execute(
                select(func.count()).select_from(BusinessDomainDescription).where(BusinessDomainDescription.domain_id == domain_id)
            ).scalar_one()
            ref_count += db.execute(
                select(func.count()).select_from(BusinessDomainKnowledgeBase).where(BusinessDomainKnowledgeBase.domain_id == domain_id)
            ).scalar_one()
            score_by_domain_id[domain_id] = int(ref_count)

        canonical = sorted(rows, key=lambda item: (-score_by_domain_id.get(item.id, 0), item.id))[0]
        for row in rows:
            if row.id == canonical.id:
                continue
            db.execute(
                update(DataSource)
                .where(DataSource.business_domain_id == row.id)
                .values(business_domain_id=canonical.id)
            )
            db.execute(
                update(KnowledgeBase)
                .where(KnowledgeBase.business_domain_id == row.id)
                .values(business_domain_id=canonical.id)
            )
            db.execute(
                update(BusinessDomainSelection)
                .where(BusinessDomainSelection.domain_id == row.id)
                .values(domain_id=canonical.id)
            )
            db.execute(
                update(BusinessDomainDescription)
                .where(BusinessDomainDescription.domain_id == row.id)
                .values(domain_id=canonical.id)
            )
            kb_links = (
                db.execute(
                    select(BusinessDomainKnowledgeBase).where(BusinessDomainKnowledgeBase.domain_id == row.id)
                )
                .scalars()
                .all()
            )
            for link in kb_links:
                exists = db.execute(
                    select(BusinessDomainKnowledgeBase.id).where(
                        BusinessDomainKnowledgeBase.domain_id == canonical.id,
                        BusinessDomainKnowledgeBase.knowledge_base_id == link.knowledge_base_id,
                    )
                ).scalar_one_or_none()
                if exists:
                    db.delete(link)
                else:
                    link.domain_id = canonical.id
            db.delete(row)
        db.commit()
        db.refresh(canonical)
        return canonical

    created = BusinessDomain(name=TEMPORARY_DOMAIN_NAME)
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def resolve_scope_domain(request: Request, db: Session = Depends(get_db)) -> BusinessDomain:
    # Backward compatibility: legacy call sites may still pass (db, request).
    actual_request = request
    actual_db = db
    if isinstance(request, Session):
        if not isinstance(db, Request):
            raise HTTPException(status_code=500, detail="invalid scope resolver arguments")
        actual_request = db
        actual_db = request

    raw = (actual_request.headers.get(DOMAIN_HEADER) or "").strip()
    if raw:
        try:
            domain_id = int(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid business domain header") from exc
        row = actual_db.get(BusinessDomain, domain_id)
        if not row:
            raise HTTPException(status_code=404, detail="business domain not found")
        return row
    return ensure_temporary_domain(actual_db)


def is_temporary_domain(domain: BusinessDomain) -> bool:
    return (domain.name or "").strip() == TEMPORARY_DOMAIN_NAME
