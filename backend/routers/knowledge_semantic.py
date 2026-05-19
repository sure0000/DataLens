"""语义知识库 API：术语、指标、血缘的 CRUD + 流水线统计 + 触发清洗。"""

from datetime import datetime, timezone

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


def _list_semantic(db: Session, model: type, kb_id: int, status: str | None = None):
    """通用列表查询：按 kb_id 过滤，可选 status，按 confidence desc + name 排序。"""
    q = select(model).where(model.knowledge_base_id == kb_id)
    if status:
        q = q.where(model.status == status)
    q = q.order_by(model.confidence.desc().nulls_last(), model.name)
    return db.execute(q).scalars().all()


def _delete_semantic(db: Session, model: type, entity_id: int, kb_id: int, label: str) -> dict:
    """通用删除：校验归属后删除并返回 {"ok": true}。"""
    entity = db.get(model, entity_id)
    if not entity or entity.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail=f"{label}不存在")
    db.delete(entity)
    db.commit()
    return {"ok": True}


def _count_grouped(db: Session, model: type, kb_id: int):
    """通用分组计数：返回 (total, {status: count})。"""
    total = db.execute(
        select(func.count(model.id)).where(model.knowledge_base_id == kb_id)
    ).scalar() or 0
    by_status = dict(
        db.execute(
            select(model.status, func.count(model.id))
            .where(model.knowledge_base_id == kb_id)
            .group_by(model.status)
        ).all()
    )
    return total, by_status


# ── Terms ────────────────────────────────────────────────────────────────


@router.get("/{kb_id}/terms")
def list_terms(kb_id: int, status: str | None = None, db: Session = Depends(get_db)):
    terms = _list_semantic(db, BusinessTerm, kb_id, status)
    return {"terms": [t.to_dict() for t in terms]}


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
    return {"term": term.to_dict()}


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
    return {"term": term.to_dict()}


@router.delete("/{kb_id}/terms/{term_id}")
def delete_term(kb_id: int, term_id: int, db: Session = Depends(get_db)):
    return _delete_semantic(db, BusinessTerm, term_id, kb_id, "术语")


# ── Metrics ──────────────────────────────────────────────────────────────


@router.get("/{kb_id}/metrics")
def list_metrics(kb_id: int, status: str | None = None, db: Session = Depends(get_db)):
    metrics = _list_semantic(db, MetricDefinition, kb_id, status)
    return {"metrics": [m.to_dict() for m in metrics]}


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
    return {"metric": metric.to_dict()}


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
    return {"metric": metric.to_dict()}


@router.delete("/{kb_id}/metrics/{metric_id}")
def delete_metric(kb_id: int, metric_id: int, db: Session = Depends(get_db)):
    return _delete_semantic(db, MetricDefinition, metric_id, kb_id, "指标")


# ── Lineage ──────────────────────────────────────────────────────────────


@router.get("/{kb_id}/lineage")
def get_lineage(kb_id: int, db: Session = Depends(get_db)):
    edges = db.execute(
        select(DataLineage)
        .where(DataLineage.knowledge_base_id == kb_id)
        .order_by(DataLineage.layer, DataLineage.source_table)
    ).scalars().all()

    layers_map: dict[str, list[dict]] = {}
    for edge in edges:
        for table_name in (edge.source_table, edge.target_table):
            if edge.layer not in layers_map:
                layers_map[edge.layer] = []
            if not any(n["name"] == table_name for n in layers_map[edge.layer]):
                layers_map[edge.layer].append({
                    "id": table_name,
                    "name": table_name,
                    "layer": edge.layer,
                    "status": edge.status,
                })

    return {
        "layers": [{"name": k, "nodes": v} for k, v in layers_map.items()],
        "edges": [e.to_dict() for e in edges],
        "stats": {
            "done": sum(1 for e in edges if e.status == "done"),
            "processing": sum(1 for e in edges if e.status == "processing"),
            "pending": sum(1 for e in edges if e.status == "pending"),
        },
    }


# ── Pipeline Stats ───────────────────────────────────────────────────────


@router.get("/{kb_id}/pipeline-stats")
def get_pipeline_stats(kb_id: int, db: Session = Depends(get_db)):
    term_count, terms_by_status = _count_grouped(db, BusinessTerm, kb_id)
    metric_count, metrics_by_status = _count_grouped(db, MetricDefinition, kb_id)
    lineage_count, lineage_by_status = _count_grouped(db, DataLineage, kb_id)

    doc_counts = dict(
        db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .group_by(Document.status)
        ).all()
    )
    total_docs = sum(doc_counts.values())

    git_sources = db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id)
    ).scalars().all()

    last_run = db.execute(
        select(PipelineRun)
        .where(PipelineRun.knowledge_base_id == kb_id)
        .order_by(PipelineRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if last_run and last_run.status == "running" and last_run.started_at:
        elapsed = datetime.now(timezone.utc) - last_run.started_at
        if elapsed.total_seconds() > 300:
            last_run.status = "failed"
            last_run.steps = {
                k: (v if isinstance(v, dict) else {"status": "failed", "reason": "timeout"})
                for k, v in (last_run.steps or {}).items()
            }
            last_run.completed_at = datetime.now(timezone.utc)
            db.commit()

    return {
        "term_count": term_count,
        "metric_count": metric_count,
        "terms_by_status": terms_by_status,
        "metrics_by_status": metrics_by_status,
        "documents_by_status": doc_counts,
        "total_documents": total_docs,
        "indexed_documents": doc_counts.get("indexed", 0),
        "git_sources": [
            {
                "id": gs.id,
                "name": gs.name,
                "provider": gs.provider,
                "last_sync_status": gs.last_sync_status,
                "last_sync_at": gs.last_sync_at.isoformat() if gs.last_sync_at else None,
                "tags": gs.tags if isinstance(gs.tags, list) else [],
            }
            for gs in git_sources
        ],
        "lineage_stats": {
            "done": lineage_by_status.get("done", 0),
            "processing": lineage_by_status.get("processing", 0),
            "pending": lineage_by_status.get("pending", 0),
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
    """手动触发语义清洗流水线（后台执行，立即返回）。"""
    from services.semantic_extraction import trigger_semantic_pipeline_background

    # 检查是否已有正在运行的流水线
    existing = db.execute(
        select(PipelineRun).where(
            PipelineRun.knowledge_base_id == kb_id,
            PipelineRun.status == "running",
        )
    ).scalars().first()

    if existing:
        elapsed = datetime.now(timezone.utc) - existing.started_at
        if elapsed.total_seconds() > 300:
            existing.status = "failed"
            existing.steps = {
                k: (v if isinstance(v, dict) else {"status": "failed", "reason": "timeout"})
                for k, v in (existing.steps or {}).items()
            }
            existing.completed_at = datetime.now(timezone.utc)
            db.commit()
        else:
            return {"status": "skipped", "reason": "已有正在运行的流水线", "run_id": existing.id}

    trigger_semantic_pipeline_background(kb_id, source_type="manual", skip_if_running=False)
    return {"status": "started", "reason": "流水线已在后台启动"}
