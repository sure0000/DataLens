"""Ontology API: SPARQL proxy, TTL import/export, quarantine, RDF-native CRUD."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models import KnowledgeBase
from ontology import NS, concept_slug, kb_graph_iri, metric_iri, quarantine_graph_iri, term_iri
from services.ontology_loader import init_ontology
from services.ontology_rdf_browser import fetch_kb_rdf_view
from services.ontology_store import delete_graph, export_graph_ttl, graph_stats, insert_graph, sparql_query
from services.ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result
from services.ontology_validation import validate_ttl
from services.ontology.writer import OntologyWriter, TermInput, MetricInput
from services.ontology.validator import validate as shacl_validate
from services.ontology.quarantine import QuarantineManager

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


class SparqlRequest(BaseModel):
    query: str
    kb_id: int | None = None


class TtlImportRequest(BaseModel):
    ttl: str
    kb_id: int
    replace: bool = False


class QuarantineResolveRequest(BaseModel):
    kb_id: int
    subject: str
    predicate: str
    object: str
    object_is_uri: bool = False
    approve: bool = True


class QuarantineApplyFixRequest(BaseModel):
    template_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class TermOntologyCreate(BaseModel):
    name: str
    definition: str = ""
    related_fields: list[str] = Field(default_factory=list)
    confidence: float = 80.0
    status: str = "approved"


class MetricOntologyCreate(BaseModel):
    name: str
    formula: str
    caliber: str | None = None
    bound_table_refs: list[str] = Field(default_factory=list)
    confidence: float = 80.0
    status: str = "approved"


class AssertionPromoteRequest(BaseModel):
    subject: str
    target_status: str | None = None
    target_lifecycle: str | None = None


class CopilotValidateRequest(BaseModel):
    question: str | None = None
    subject: str | None = None
    table_id: int | None = None
    entity_name: str | None = None
    auto_apply: bool = False


class ModelingRunRequest(BaseModel):
    source_type: str = "manual"
    source_id: int | None = None
    skip_if_running: bool = True


def _get_writer() -> OntologyWriter:
    """Create an OntologyWriter wired to the current triple store."""
    from services.triple_store import get_triple_store
    store = get_triple_store()
    quarantine = QuarantineManager(store)
    return OntologyWriter(store=store, validator=shacl_validate, quarantine_manager=quarantine)


@router.get("/health")
def ontology_health() -> dict:
    init_ontology()
    return {"ok": True, **graph_stats()}


@router.post("/sparql")
def run_sparql(body: SparqlRequest) -> dict:
    settings = get_settings()
    if not settings.ontology_enabled:
        raise HTTPException(status_code=503, detail="Ontology disabled")
    try:
        rows = sparql_query(body.query)
        return {"ok": True, "results": rows}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge-bases/{kb_id}/export")
def export_kb_ontology(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    graph = kb_graph_iri(kb_id)
    ttl = export_graph_ttl(graph)
    return {"ok": True, "kb_id": kb_id, "graph": graph, "ttl": ttl}


@router.post("/knowledge-bases/{kb_id}/import")
def import_kb_ontology(kb_id: int, body: TtlImportRequest, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    report = validate_ttl(body.ttl)
    if not report.get("conforms") and not report.get("skipped"):
        return {"ok": False, "shacl": report}
    if body.replace:
        from services.ontology_store import delete_graph
        delete_graph(kb_graph_iri(kb_id))
    insert_graph(kb_graph_iri(kb_id), body.ttl)
    try:
        from services.ingestion.connectors import register_evidence_from_import

        register_evidence_from_import(
            db,
            kb_id,
            title="TTL 导入",
            route_key="ontology/import",
            source_ref={"ttl_import": True},
            processing_state="ready_for_extraction",
        )
    except Exception:
        pass
    return {"ok": True, "shacl": report}


@router.post("/knowledge-bases/{kb_id}/sync-from-legacy")
def sync_from_legacy(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """Legacy migration endpoint — no longer needed (Phase 1 ontology refactoring)."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"ok": True, "message": "Legacy PG semantic tables have been removed. Use RDF-native endpoints instead.", "kb_id": kb_id}


@router.post("/knowledge-bases/{kb_id}/documents/{document_id}/assert")
def assert_document_ontology(
    kb_id: int, document_id: int, db: Session = Depends(get_db)
) -> dict:
    """Trigger ontology extraction for a document (Phase 2 will rewrite this)."""
    from models import Document
    from services.ontology_population import populate_from_document

    doc = db.get(Document, document_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    return populate_from_document(db, document_id, kb_id=kb_id, domain_tables=[], domain_id=None)


def _quarantine_items_payload(kb_id: int) -> list[dict[str, Any]]:
    from services.ontology.quarantine import QuarantineManager
    from services.ontology.quarantine_templates import REASON_LABELS, suggest_templates
    from services.triple_store import get_triple_store
    import json
    import re

    mgr = QuarantineManager(get_triple_store())
    result = mgr.list_items(kb_id)
    items: list[dict[str, Any]] = []
    for item in result.items:
        raw = item.raw_triple or {}
        m = re.search(r"/item/(\d+)$", item.subject)
        item_idx = int(m.group(1)) if m else item.index
        reason = item.reason or "unknown"
        items.append(
            {
                "item_idx": item_idx,
                "q": item.subject,
                "reason": reason,
                "reason_label": REASON_LABELS.get(reason, reason),
                "raw": json.dumps(raw, ensure_ascii=False) if raw else item.suggested_fix,
                "subject": raw.get("subject"),
                "predicate": raw.get("predicate"),
                "object": raw.get("object"),
                "object_is_uri": raw.get("object_is_uri", False),
                "suggested_fix": item.suggested_fix,
                "fix_templates": suggest_templates(reason, raw),
            }
        )
    return items


@router.get("/knowledge-bases/{kb_id}/quarantine")
def list_quarantine(
    kb_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    all_items = _quarantine_items_payload(kb_id)
    total = len(all_items)
    page = all_items[offset : offset + limit]
    return {
        "ok": True,
        "kb_id": kb_id,
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < total,
    }


@router.post("/knowledge-bases/{kb_id}/quarantine/{item_idx}/resolve")
def resolve_kb_quarantine(
    kb_id: int, item_idx: int, approve: bool = Query(True), db: Session = Depends(get_db)
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.quarantine import QuarantineManager
    from services.triple_store import get_triple_store

    mgr = QuarantineManager(get_triple_store())
    ok = mgr.resolve(kb_id, item_idx, approved=approve)
    if not ok:
        raise HTTPException(status_code=400, detail="隔离项处理失败")
    return {"ok": True, "action": "approved" if approve else "rejected", "item_idx": item_idx}


@router.post("/knowledge-bases/{kb_id}/quarantine/{item_idx}/apply-fix")
def apply_quarantine_fix(
    kb_id: int, item_idx: int, body: QuarantineApplyFixRequest, db: Session = Depends(get_db)
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    items = _quarantine_items_payload(kb_id)
    target = next((i for i in items if i["item_idx"] == item_idx), None)
    if not target:
        raise HTTPException(status_code=404, detail="隔离项不存在")

    from services.ontology.quarantine import QuarantineManager
    from services.ontology.quarantine_templates import apply_template
    from services.ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result
    from services.triple_store import get_triple_store

    raw: dict[str, Any] = {
        "subject": target.get("subject") or "",
        "predicate": target.get("predicate") or "",
        "object": target.get("object") or "",
        "object_is_uri": bool(target.get("object_is_uri", False)),
    }
    if not raw["subject"] and target.get("raw"):
        try:
            raw = json.loads(target["raw"])
        except json.JSONDecodeError:
            pass

    fix = apply_template(
        kb_id,
        reason=target["reason"],
        raw_triple=raw,
        template_id=body.template_id,
        params=body.params,
    )
    if not fix.get("ok"):
        raise HTTPException(status_code=400, detail=fix.get("error", "修复失败"))

    mgr = QuarantineManager(get_triple_store())
    if fix.get("action") == "drop":
        mgr.resolve(kb_id, item_idx, approved=False)
        return {"ok": True, "action": "dropped"}

    tdata = fix["triple"]
    triple = RawTriple(
        tdata["subject"],
        tdata["predicate"],
        tdata["object"],
        tdata.get("object_is_uri", False),
        graph=kb_graph_iri(kb_id),
        confidence=90.0,
    )
    result = clean_triples([triple], kb_id=kb_id)
    out = persist_clean_result(result, kb_id)
    mgr.resolve(kb_id, item_idx, approved=False)
    return {"ok": True, "action": "applied", **out}


@router.post("/quarantine/{item_idx}/resolve")
def resolve_quarantine_legacy(item_idx: int, body: QuarantineResolveRequest) -> dict:
    """Legacy resolve with explicit triple body."""
    if not body.approve:
        return {"ok": True, "action": "rejected"}
    triple = RawTriple(
        body.subject,
        body.predicate,
        body.object,
        body.object_is_uri,
        graph=kb_graph_iri(body.kb_id),
        confidence=90.0,
    )
    result = clean_triples([triple], kb_id=body.kb_id)
    out = persist_clean_result(result, body.kb_id)
    return {"ok": True, **out}


@router.get("/knowledge-bases/{kb_id}/rdf-view")
def get_kb_rdf_view(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """Entities stored in RDF named graphs (production + quarantine stats)."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    try:
        rdf = fetch_kb_rdf_view(kb_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RDF 查询失败: {exc}") from exc
    return {"ok": True, "kb_id": kb_id, "kb_name": kb.name, **rdf, "store": graph_stats()}


@router.get("/knowledge-bases/{kb_id}/graph")
def get_ontology_graph(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    graph_iri = kb_graph_iri(kb_id)
    nodes: list[dict] = []
    edges: list[dict] = []
    rdf_view: dict | None = None
    try:
        rdf_view = fetch_kb_rdf_view(kb_id)
        for t in rdf_view.get("production", {}).get("terms", []):
            nodes.append({
                "id": t["iri"],
                "type": "term",
                "label": t["label"],
                "status": t.get("status"),
                "source": "rdf",
            })
        for m in rdf_view.get("production", {}).get("metrics", []):
            nodes.append({
                "id": m["iri"],
                "type": "metric",
                "label": m["label"],
                "status": m.get("status"),
                "source": "rdf",
            })
        for tbl in rdf_view.get("production", {}).get("physical_tables", []):
            nodes.append({
                "id": tbl["iri"],
                "type": "physical_table",
                "label": tbl.get("summary")[:40] if tbl.get("summary") else f"表 #{tbl.get('platform_id')}",
                "status": "rdf",
                "source": "rdf",
                "platform_id": tbl.get("platform_id"),
            })
    except Exception:
        rdf_view = None

    # Legacy PG semantic tables removed in Phase 1 — all data comes from RDF now.

    return {
        "ok": True,
        "graph_iri": graph_iri,
        "nodes": nodes,
        "edges": edges,
        "rdf": rdf_view,
        "store": graph_stats(),
    }


# ── Modeling pipeline status ───────────────────────────────────────────


@router.get("/knowledge-bases/{kb_id}/modeling/status")
def get_modeling_status(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """Aggregate extraction pipeline, document indexing, and RDF quality metrics."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.modeling_status import get_modeling_status as _status

    return _status(db, kb_id)


@router.get("/knowledge-bases/{kb_id}/modeling/layers/{layer_key}")
def get_modeling_layer(
    kb_id: int,
    layer_key: str,
    limit: int = Query(20, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="全层搜索（属性层支持表名/字段/属性值）"),
    physical_only: bool = Query(
        False,
        description="属性层：仅返回数据源物理表/列（database_schema_sync 入图）",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Return a single cleaning layer (vocabulary, rule, dimension, relation, …)."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.modeling_layers import get_modeling_layer as _layer

    result = _layer(
        db,
        kb_id,
        layer_key,
        limit=limit,
        offset=offset,
        q=q,
        physical_only=physical_only,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "未知清洗层"))
    return result


@router.post("/knowledge-bases/{kb_id}/modeling/runs")
def start_modeling_run(
    kb_id: int,
    body: ModelingRunRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Trigger the 8-step extraction pipeline in the background."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    req = body or ModelingRunRequest()
    from models import PipelineRun

    if req.skip_if_running:
        running = db.execute(
            select(PipelineRun).where(
                PipelineRun.knowledge_base_id == kb_id,
                PipelineRun.status == "running",
            )
        ).scalars().first()
        if running:
            return {
                "ok": True,
                "status": "already_running",
                "run_id": running.id,
                "message": "已有建模任务在运行中",
            }

    from services.extraction.orchestrator import trigger_extraction_pipeline_background

    trigger_extraction_pipeline_background(kb_id, source_type=req.source_type)
    return {
        "ok": True,
        "status": "started",
        "kb_id": kb_id,
        "source_type": req.source_type,
        "message": "已启动 8 步抽取流水线（后台运行）",
    }


# ── Presentation views (read-only SPARQL) ────────────────────────────────


@router.get("/knowledge-bases/{kb_id}/views/overview")
def get_view_overview(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.views import view_overview

    return view_overview(db, kb_id)


@router.get("/knowledge-bases/{kb_id}/views/terms")
def get_view_terms(
    kb_id: int,
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.views import view_terms

    return view_terms(kb_id, status=status, limit=limit)


@router.get("/knowledge-bases/{kb_id}/views/graph")
def get_view_graph(
    kb_id: int,
    center: str | None = Query(None, description="Center node IRI for 1-hop neighborhood"),
    db: Session = Depends(get_db),
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.views import view_graph

    return view_graph(kb_id, center=center)


@router.get("/knowledge-bases/{kb_id}/views/triples")
def get_view_triples(
    kb_id: int,
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.views import view_triples

    return view_triples(kb_id, limit=limit)


@router.get("/knowledge-bases/{kb_id}/views/lineage")
def get_view_lineage(
    kb_id: int,
    table: str | None = Query(None, description="Table IRI or platform id substring"),
    db: Session = Depends(get_db),
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.views import view_lineage

    return view_lineage(kb_id, table=table)


@router.get("/knowledge-bases/{kb_id}/views/hierarchy")
def get_view_hierarchy(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.hierarchy_view import build_hierarchy_roots

    return {"ok": True, "kb_id": kb_id, "roots": build_hierarchy_roots(kb_id)}


@router.get("/knowledge-bases/{kb_id}/provenance")
def get_provenance(
    kb_id: int,
    subject: str = Query(..., description="Entity IRI"),
    db: Session = Depends(get_db),
) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.provenance import get_provenance_chain

    return get_provenance_chain(db, kb_id, subject.strip())


@router.post("/knowledge-bases/{kb_id}/copilot-validate")
def copilot_validate_entity(kb_id: int, body: CopilotValidateRequest, db: Session = Depends(get_db)) -> dict:
    """Copilot 验证：根据 routing_trace 匹配隔离区并建议/自动修复。"""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.copilot_validation import run_copilot_validation

    result = run_copilot_validation(
        db,
        kb_id,
        question=body.question,
        subject_iri=(body.subject or "").strip() or None,
        table_id=body.table_id,
        entity_name=(body.entity_name or "").strip() or None,
        auto_apply=body.auto_apply,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "验证失败"))
    return result


@router.post("/knowledge-bases/{kb_id}/assertions/promote")
def promote_assertion(kb_id: int, body: AssertionPromoteRequest, db: Session = Depends(get_db)) -> dict:
    """Promote assertion lifecycle via dl:approvalStatus (draft → pending_review → approved)."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.assertion_lifecycle import promote_assertion as _promote

    result = _promote(
        kb_id,
        body.subject.strip(),
        target_status=body.target_status,
        target_lifecycle=body.target_lifecycle,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "promote failed"))
    return result


@router.get("/knowledge-bases/{kb_id}/assertions/status")
def get_assertion_status(kb_id: int, subject: str = Query(...), db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.assertion_lifecycle import get_assertion_status as _status

    return {"ok": True, "kb_id": kb_id, **_status(kb_id, subject)}


# ── Ontology 5-Layer Cleaning Results ──────────────────────────────────


@router.get("/knowledge-bases/{kb_id}/ontology-cleaning-results")
def get_ontology_cleaning_results(
    kb_id: int,
    include_items: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    """Return ontology cleaning results organized by the 5-layer model (summary by default)."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology.modeling_layers import get_cleaning_results

    return get_cleaning_results(db, kb_id, include_items=include_items)


# ── RDF-native term/metric CRUD (Phase 1: writes go through OntologyWriter) ──


@router.get("/knowledge-bases/{kb_id}/terms")
def list_terms(kb_id: int) -> dict:
    """List terms from the RDF production graph."""
    graph = kb_graph_iri(kb_id)
    query = f"""
    PREFIX dl: <{NS}>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?s ?label ?definition ?status ?confidence WHERE {{
      GRAPH <{graph}> {{
        ?s a dl:BusinessTerm ;
           skos:prefLabel ?label .
        OPTIONAL {{ ?s skos:definition ?definition . }}
        OPTIONAL {{ ?s dl:approvalStatus ?status . }}
        OPTIONAL {{ ?s dl:confidence ?confidence . }}
      }}
    }}
    ORDER BY ?label
    """
    try:
        rows = sparql_query(query)
    except Exception as exc:
        _logger.warning("SPARQL term list failed: %s", exc)
        rows = []
    terms = []
    for i, r in enumerate(rows):
        terms.append(
            {
                "id": i + 1,
                "iri": r.get("s", ""),
                "name": r.get("label", ""),
                "type": "other",
                "definition": r.get("definition", ""),
                "related_fields": [],
                "concept_id": None,
                "confidence": float(r.get("confidence") or 0),
                "status": r.get("status") or "draft",
            }
        )
    return {"terms": terms}


@router.post("/knowledge-bases/{kb_id}/terms")
def create_term(kb_id: int, body: TermOntologyCreate) -> dict:
    """Create a term via OntologyWriter (RDF-native, with SHACL validation)."""
    writer = _get_writer()
    term_input = TermInput(
        domain_id=kb_id,
        name=body.name,
        definition=body.definition,
        related_fields=body.related_fields,
        confidence=body.confidence,
        status=body.status,
    )
    result = writer.write_term(kb_id, term_input)
    return {"ok": True, "kb_id": kb_id, **result}


@router.get("/knowledge-bases/{kb_id}/metrics")
def list_metrics(kb_id: int) -> dict:
    """List metrics from the RDF production graph."""
    graph = kb_graph_iri(kb_id)
    query = f"""
    PREFIX dl: <{NS}>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?s ?label ?formula ?caliber ?status ?confidence WHERE {{
      GRAPH <{graph}> {{
        ?s a dl:Metric ;
           skos:prefLabel ?label .
        OPTIONAL {{ ?s dl:formula ?formula . }}
        OPTIONAL {{ ?s dl:caliber ?caliber . }}
        OPTIONAL {{ ?s dl:approvalStatus ?status . }}
        OPTIONAL {{ ?s dl:confidence ?confidence . }}
      }}
    }}
    ORDER BY ?label
    """
    try:
        rows = sparql_query(query)
    except Exception as exc:
        _logger.warning("SPARQL metric list failed: %s", exc)
        rows = []
    metrics = []
    for i, r in enumerate(rows):
        metrics.append(
            {
                "id": i + 1,
                "iri": r.get("s", ""),
                "name": r.get("label", ""),
                "formula": r.get("formula", ""),
                "caliber": r.get("caliber"),
                "bound_table_refs": [],
                "concept_id": None,
                "confidence": float(r.get("confidence") or 0),
                "status": r.get("status") or "draft",
            }
        )
    return {"metrics": metrics}


@router.get("/knowledge-bases/{kb_id}/dimensions")
def list_dimensions(kb_id: int) -> dict:
    """List dl:Dimension instances from the RDF production graph."""
    graph = kb_graph_iri(kb_id)
    query = f"""
    PREFIX dl: <{NS}>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?s ?label ?definition ?dimType ?status ?confidence WHERE {{
      GRAPH <{graph}> {{
        ?s a dl:Dimension ;
           skos:prefLabel ?label .
        OPTIONAL {{ ?s skos:definition ?definition . }}
        OPTIONAL {{ ?s dl:dimensionType ?dimType . }}
        OPTIONAL {{ ?s dl:approvalStatus ?status . }}
        OPTIONAL {{ ?s dl:confidence ?confidence . }}
      }}
    }}
    ORDER BY ?label
    """
    try:
        rows = sparql_query(query)
    except Exception as exc:
        _logger.warning("SPARQL dimension list failed: %s", exc)
        rows = []
    dimensions = []
    for i, r in enumerate(rows):
        dimensions.append(
            {
                "id": i + 1,
                "iri": r.get("s", ""),
                "name": r.get("label", ""),
                "definition": r.get("definition", ""),
                "dim_type": r.get("dimType", ""),
                "confidence": float(r.get("confidence") or 0),
                "status": r.get("status") or "draft",
            }
        )
    return {"dimensions": dimensions}


@router.get("/knowledge-bases/{kb_id}/rules")
def list_rules(kb_id: int) -> dict:
    """List dl:BusinessRule instances from the RDF production graph."""
    graph = kb_graph_iri(kb_id)
    query = f"""
    PREFIX dl: <{NS}>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?s ?label ?ruleExpression ?ruleType ?status ?confidence WHERE {{
      GRAPH <{graph}> {{
        ?s a dl:BusinessRule ;
           skos:prefLabel ?label .
        OPTIONAL {{ ?s dl:ruleExpression ?ruleExpression . }}
        OPTIONAL {{ ?s dl:ruleType ?ruleType . }}
        OPTIONAL {{ ?s dl:approvalStatus ?status . }}
        OPTIONAL {{ ?s dl:confidence ?confidence . }}
      }}
    }}
    ORDER BY ?label
    """
    try:
        rows = sparql_query(query)
    except Exception as exc:
        _logger.warning("SPARQL rule list failed: %s", exc)
        rows = []
    rules = []
    for i, r in enumerate(rows):
        rules.append(
            {
                "id": i + 1,
                "iri": r.get("s", ""),
                "name": r.get("label", ""),
                "rule_expression": r.get("ruleExpression", ""),
                "rule_type": r.get("ruleType", ""),
                "confidence": float(r.get("confidence") or 0),
                "status": r.get("status") or "draft",
            }
        )
    return {"rules": rules}


@router.post("/knowledge-bases/{kb_id}/metrics")
def create_metric(kb_id: int, body: MetricOntologyCreate) -> dict:
    """Create a metric via OntologyWriter (RDF-native, with SHACL validation)."""
    writer = _get_writer()
    metric_input = MetricInput(
        domain_id=kb_id,
        name=body.name,
        formula=body.formula,
        caliber=body.caliber or "",
        confidence=body.confidence,
        status=body.status,
    )
    result = writer.write_metric(kb_id, metric_input)
    return {"ok": True, "kb_id": kb_id, **result}
