"""语义知识库 API：术语、指标、血缘的 CRUD + 流水线统计 + 触发清洗。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import (
    BusinessTerm,
    DataLineage,
    Document,
    KnowledgeGitSource,
    MetricDefinition,
    PipelineRun,
)

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-semantic"])

# ── Pydantic Schemas ────────────────────────────────────────────────────


class TermCreate(BaseModel):
    name: str
    type: str = "other"
    definition: str = ""
    related_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class TermUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    definition: str | None = None
    related_fields: list[str] | None = None
    confidence: float | None = None
    status: str | None = None


class MetricCreate(BaseModel):
    name: str
    formula: str = ""
    caliber: str | None = None
    related_terms: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class MetricUpdate(BaseModel):
    name: str | None = None
    formula: str | None = None
    caliber: str | None = None
    related_terms: list[str] | None = None
    confidence: float | None = None
    status: str | None = None


# ── Helper ───────────────────────────────────────────────────────────────


def _term_row(t: BusinessTerm) -> dict:
    return {
        "id": t.id,
        "knowledge_base_id": t.knowledge_base_id,
        "name": t.name,
        "type": t.type,
        "definition": t.definition,
        "source_entry_id": t.source_entry_id,
        "related_fields": t.related_fields or [],
        "confidence": t.confidence,
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _metric_row(m: MetricDefinition) -> dict:
    return {
        "id": m.id,
        "knowledge_base_id": m.knowledge_base_id,
        "name": m.name,
        "formula": m.formula,
        "caliber": m.caliber,
        "source_entry_id": m.source_entry_id,
        "related_terms": m.related_terms or [],
        "confidence": m.confidence,
        "status": m.status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _lineage_row(l: DataLineage) -> dict:
    return {
        "id": l.id,
        "knowledge_base_id": l.knowledge_base_id,
        "git_source_id": l.git_source_id,
        "source_table": l.source_table,
        "target_table": l.target_table,
        "source_field": l.source_field,
        "target_field": l.target_field,
        "layer": l.layer,
        "transform_logic": l.transform_logic,
        "status": l.status,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
    }


# ── Terms ────────────────────────────────────────────────────────────────


@router.get("/{kb_id}/terms")
def list_terms(kb_id: int, status: str | None = None, db: Session = Depends(get_db)):
    q = select(BusinessTerm).where(BusinessTerm.knowledge_base_id == kb_id)
    if status:
        q = q.where(BusinessTerm.status == status)
    q = q.order_by(BusinessTerm.confidence.desc().nulls_last(), BusinessTerm.name)
    terms = db.execute(q).scalars().all()
    return {"terms": [_term_row(t) for t in terms]}


@router.post("/{kb_id}/terms")
def create_term(kb_id: int, body: TermCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(BusinessTerm).where(
            BusinessTerm.knowledge_base_id == kb_id, BusinessTerm.name == body.name
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="术语已存在")
    term = BusinessTerm(
        knowledge_base_id=kb_id,
        name=body.name,
        type=body.type,
        definition=body.definition,
        related_fields=body.related_fields,
        confidence=body.confidence,
        status="pending_review",
    )
    db.add(term)
    db.commit()
    return {"term": _term_row(term)}


@router.put("/{kb_id}/terms/{term_id}")
def update_term(kb_id: int, term_id: int, body: TermUpdate, db: Session = Depends(get_db)):
    term = db.get(BusinessTerm, term_id)
    if not term or term.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="术语不存在")
    for key in ("name", "type", "definition", "related_fields", "confidence", "status"):
        val = getattr(body, key, None)
        if val is not None:
            setattr(term, key, val)
    db.commit()
    return {"term": _term_row(term)}


@router.delete("/{kb_id}/terms/{term_id}")
def delete_term(kb_id: int, term_id: int, db: Session = Depends(get_db)):
    term = db.get(BusinessTerm, term_id)
    if not term or term.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="术语不存在")
    db.delete(term)
    db.commit()
    return {"ok": True}


# ── Metrics ──────────────────────────────────────────────────────────────


@router.get("/{kb_id}/metrics")
def list_metrics(kb_id: int, status: str | None = None, db: Session = Depends(get_db)):
    q = select(MetricDefinition).where(MetricDefinition.knowledge_base_id == kb_id)
    if status:
        q = q.where(MetricDefinition.status == status)
    q = q.order_by(MetricDefinition.confidence.desc().nulls_last(), MetricDefinition.name)
    metrics = db.execute(q).scalars().all()
    return {"metrics": [_metric_row(m) for m in metrics]}


@router.post("/{kb_id}/metrics")
def create_metric(kb_id: int, body: MetricCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(MetricDefinition).where(
            MetricDefinition.knowledge_base_id == kb_id, MetricDefinition.name == body.name
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="指标已存在")
    metric = MetricDefinition(
        knowledge_base_id=kb_id,
        name=body.name,
        formula=body.formula,
        caliber=body.caliber,
        related_terms=body.related_terms,
        confidence=body.confidence,
        status="pending_review",
    )
    db.add(metric)
    db.commit()
    return {"metric": _metric_row(metric)}


@router.put("/{kb_id}/metrics/{metric_id}")
def update_metric(kb_id: int, metric_id: int, body: MetricUpdate, db: Session = Depends(get_db)):
    metric = db.get(MetricDefinition, metric_id)
    if not metric or metric.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="指标不存在")
    for key in ("name", "formula", "caliber", "related_terms", "confidence", "status"):
        val = getattr(body, key, None)
        if val is not None:
            setattr(metric, key, val)
    db.commit()
    return {"metric": _metric_row(metric)}


@router.delete("/{kb_id}/metrics/{metric_id}")
def delete_metric(kb_id: int, metric_id: int, db: Session = Depends(get_db)):
    metric = db.get(MetricDefinition, metric_id)
    if not metric or metric.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="指标不存在")
    db.delete(metric)
    db.commit()
    return {"ok": True}


# ── Lineage ──────────────────────────────────────────────────────────────


@router.get("/{kb_id}/lineage")
def get_lineage(kb_id: int, db: Session = Depends(get_db)):
    edges = db.execute(
        select(DataLineage)
        .where(DataLineage.knowledge_base_id == kb_id)
        .order_by(DataLineage.layer, DataLineage.source_table)
    ).scalars().all()

    # Build layered graph structure
    layers_map: dict[str, list[dict]] = {}
    for edge in edges:
        row = _lineage_row(edge)
        for table_name in (edge.source_table, edge.target_table):
            layer = row["layer"]
            if layer not in layers_map:
                layers_map[layer] = []
            if not any(n["name"] == table_name for n in layers_map[layer]):
                layers_map[layer].append({
                    "id": table_name,
                    "name": table_name,
                    "layer": layer,
                    "status": edge.status,
                })

    return {
        "layers": [
            {"name": k, "nodes": v}
            for k, v in layers_map.items()
        ],
        "edges": [_lineage_row(e) for e in edges],
        "stats": {
            "done": sum(1 for e in edges if e.status == "done"),
            "processing": sum(1 for e in edges if e.status == "processing"),
            "pending": sum(1 for e in edges if e.status == "pending"),
        },
    }


# ── Pipeline Stats ───────────────────────────────────────────────────────


@router.get("/{kb_id}/pipeline-stats")
def get_pipeline_stats(kb_id: int, db: Session = Depends(get_db)):
    # Term stats
    term_count = db.execute(
        select(func.count(BusinessTerm.id)).where(BusinessTerm.knowledge_base_id == kb_id)
    ).scalar() or 0
    terms_by_status = dict(
        db.execute(
            select(BusinessTerm.status, func.count(BusinessTerm.id))
            .where(BusinessTerm.knowledge_base_id == kb_id)
            .group_by(BusinessTerm.status)
        ).all()
    )

    # Metric stats
    metric_count = db.execute(
        select(func.count(MetricDefinition.id)).where(MetricDefinition.knowledge_base_id == kb_id)
    ).scalar() or 0
    metrics_by_status = dict(
        db.execute(
            select(MetricDefinition.status, func.count(MetricDefinition.id))
            .where(MetricDefinition.knowledge_base_id == kb_id)
            .group_by(MetricDefinition.status)
        ).all()
    )

    # Document stats
    doc_counts = dict(
        db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .group_by(Document.status)
        ).all()
    )
    total_docs = sum(doc_counts.values())
    indexed_docs = doc_counts.get("indexed", 0)

    # Git sources
    git_sources = db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id)
    ).scalars().all()

    # Lineage stats
    lineage_done = db.execute(
        select(func.count(DataLineage.id)).where(
            DataLineage.knowledge_base_id == kb_id, DataLineage.status == "done"
        )
    ).scalar() or 0
    lineage_processing = db.execute(
        select(func.count(DataLineage.id)).where(
            DataLineage.knowledge_base_id == kb_id, DataLineage.status == "processing"
        )
    ).scalar() or 0
    lineage_pending = db.execute(
        select(func.count(DataLineage.id)).where(
            DataLineage.knowledge_base_id == kb_id, DataLineage.status == "pending"
        )
    ).scalar() or 0

    # Last pipeline run
    last_run = db.execute(
        select(PipelineRun)
        .where(PipelineRun.knowledge_base_id == kb_id)
        .order_by(PipelineRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "term_count": term_count,
        "metric_count": metric_count,
        "terms_by_status": terms_by_status,
        "metrics_by_status": metrics_by_status,
        "documents_by_status": doc_counts,
        "total_documents": total_docs,
        "indexed_documents": indexed_docs,
        "git_sources": [
            {
                "id": gs.id,
                "name": gs.name,
                "provider": gs.provider,
                "last_sync_status": gs.last_sync_status,
                "last_sync_at": gs.last_sync_at.isoformat() if gs.last_sync_at else None,
                "category": gs.category,
            }
            for gs in git_sources
        ],
        "lineage_stats": {
            "done": lineage_done,
            "processing": lineage_processing,
            "pending": lineage_pending,
        },
        "last_pipeline_run": {
            "id": last_run.id,
            "status": last_run.status,
            "steps": last_run.steps,
            "started_at": last_run.started_at.isoformat() if last_run and last_run.started_at else None,
            "completed_at": last_run.completed_at.isoformat() if last_run and last_run.completed_at else None,
        } if last_run else None,
    }


# ── Trigger Pipeline ─────────────────────────────────────────────────────


@router.post("/{kb_id}/semantic-pipeline/run")
def trigger_semantic_pipeline(kb_id: int, db: Session = Depends(get_db)):
    """手动触发语义清洗流水线（同步等待完成）。"""
    import asyncio
    from services.semantic_extraction import run_semantic_pipeline

    try:
        result = asyncio.run(run_semantic_pipeline(db, kb_id, source_type="manual"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流水线执行失败: {e}") from e
