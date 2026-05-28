from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import BusinessDomain

TEMPORARY_DOMAIN_NAME = "临时域"
DOMAIN_HEADER = "X-Business-Domain-Id"


def ensure_temporary_domain(db: Session) -> BusinessDomain:
    canonical = (
        db.execute(
            select(BusinessDomain)
            .where(BusinessDomain.name == TEMPORARY_DOMAIN_NAME)
            .order_by(BusinessDomain.id.asc())
        )
        .scalars()
        .first()
    )
    if canonical:
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
