"""Knowledge base ingestion — evidence package registry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeBase
from services.ingestion.registry import list_all_packages, normalize_package, register_package

router = APIRouter(prefix="/api/knowledge-bases", tags=["ingestion"])


class EvidencePackageCreate(BaseModel):
    asset_kind: str
    connector: str
    title: str
    source_ref: dict[str, Any] = Field(default_factory=dict)
    linked_entry_ids: list[int] = Field(default_factory=list)
    linked_document_id: int | None = None
    processing_state: str = "registered"


@router.get("/{kb_id}/ingestion/packages")
def get_ingestion_packages(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    packages = list_all_packages(db, kb_id)
    return {"ok": True, "kb_id": kb_id, "packages": packages, "total": len(packages)}


@router.post("/{kb_id}/ingestion/packages")
def create_ingestion_package(
    kb_id: int, body: EvidencePackageCreate, db: Session = Depends(get_db)
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    row = register_package(
        db,
        kb_id,
        asset_kind=body.asset_kind,
        connector=body.connector,
        title=body.title,
        source_ref=body.source_ref,
        linked_entry_ids=body.linked_entry_ids,
        linked_document_id=body.linked_document_id,
        processing_state=body.processing_state,
    )
    from services.ingestion.registry import _row_to_dict

    return {"ok": True, "package": _row_to_dict(row)}


@router.post("/{kb_id}/ingestion/packages/{package_id}/normalize")
def normalize_ingestion_package(
    kb_id: int, package_id: int, db: Session = Depends(get_db)
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    result = normalize_package(db, kb_id, package_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "规范化失败"))
    return result
