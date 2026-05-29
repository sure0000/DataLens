"""Business-domain scoped ontology browse API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import BusinessDomain
from services.ontology.domain_aggregation import (
    domain_assets,
    domain_dimensions,
    domain_graph,
    domain_layer_detail,
    domain_layers_summary,
    domain_lineage,
    domain_metrics,
    domain_overview,
    domain_rules,
    domain_terms,
)

router = APIRouter(prefix="/api/business-domains", tags=["domain-ontology"])


def _require_domain(db: Session, domain_id: int) -> BusinessDomain:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="domain not found")
    return domain


@router.get("/{domain_id}/ontology/overview")
def get_domain_ontology_overview(domain_id: int, db: Session = Depends(get_db)) -> dict:
    _require_domain(db, domain_id)
    return domain_overview(db, domain_id)


@router.get("/{domain_id}/ontology/terms")
def get_domain_ontology_terms(
    domain_id: int,
    kb: int | None = Query(None, description="Filter by knowledge base id"),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_terms(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/metrics")
def get_domain_ontology_metrics(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_metrics(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/dimensions")
def get_domain_ontology_dimensions(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_dimensions(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/rules")
def get_domain_ontology_rules(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_rules(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/graph")
def get_domain_ontology_graph(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_graph(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/lineage")
def get_domain_ontology_lineage(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_lineage(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/assets")
def get_domain_ontology_assets(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_assets(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/layers")
def get_domain_ontology_layers(
    domain_id: int,
    kb: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    return domain_layers_summary(db, domain_id, kb_filter=kb)


@router.get("/{domain_id}/ontology/layers/{layer_key}")
def get_domain_ontology_layer_detail(
    domain_id: int,
    layer_key: str,
    kb: int | None = Query(None),
    limit: int = Query(20, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    _require_domain(db, domain_id)
    result = domain_layer_detail(
        db,
        domain_id,
        layer_key,
        kb_filter=kb,
        limit=limit,
        offset=offset,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "未知清洗层"))
    return result
