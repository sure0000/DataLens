"""Aggregate modeling pipeline status for ontology UI."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import get_settings
from models import Document, PipelineRun

EXTRACTION_STEP_DEFS: list[tuple[str, str]] = [
    ("term_extraction", "术语"),
    ("metric_caliber", "指标"),
    ("dimension_extraction", "维度"),
    ("rule_extraction", "规则"),
    ("relation_extraction", "关系"),
    ("hierarchy_building", "层级"),
    ("data_lineage", "血缘"),
    ("join_extraction", "JOIN"),
    ("ontology_write", "入图"),
]

_STEP_STATUS_ICON = {
    "done": "ok",
    "completed": "ok",
    "skipped": "skip",
    "failed": "fail",
    "pending": "pending",
    "running": "running",
}


def _normalize_step(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        status = str(raw.get("status", "pending"))
        reason = raw.get("reason")
        done = raw.get("chunk_done")
        total = raw.get("chunk_total")
        if status == "running" and done is not None and total:
            reason = f"分块 {done}/{total}"
        return {
            "status": status,
            "icon": _STEP_STATUS_ICON.get(status, "pending"),
            "triples": raw.get("triples"),
            "reason": reason,
        }
    if isinstance(raw, str):
        return {"status": raw, "icon": _STEP_STATUS_ICON.get(raw, "pending")}
    return {"status": "pending", "icon": "pending"}


def get_modeling_status(db: Session, kb_id: int) -> dict[str, Any]:
    doc_counts = dict(
        db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .group_by(Document.status)
        ).all()
    )
    total_docs = sum(int(v) for v in doc_counts.values())
    indexed_docs = int(doc_counts.get("indexed", 0))

    last_run = db.execute(
        select(PipelineRun)
        .where(PipelineRun.knowledge_base_id == kb_id)
        .order_by(PipelineRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    steps_raw: dict[str, Any] = {}
    if last_run and last_run.steps:
        steps_raw = last_run.steps if isinstance(last_run.steps, dict) else {}

    extraction_steps = []
    done_count = 0
    for key, label in EXTRACTION_STEP_DEFS:
        info = _normalize_step(steps_raw.get(key, "pending"))
        if info["icon"] == "ok":
            done_count += 1
        extraction_steps.append({"key": key, "label": label, **info})

    total_steps = len(EXTRACTION_STEP_DEFS)
    if last_run and last_run.status == "completed":
        progress_pct = 100
    elif last_run and last_run.status == "running":
        progress_pct = round(done_count / total_steps * 100) if total_steps else 0
    else:
        progress_pct = round(done_count / total_steps * 100) if (last_run and done_count) else 0

    layers: dict[str, int] = {}
    quarantine_count = 0
    shacl_pass_rate: float | None = None
    rdf_triple_count = 0

    if get_settings().ontology_enabled:
        try:
            from services.ontology_rdf_browser import fetch_kb_rdf_view

            view = fetch_kb_rdf_view(kb_id)
            prod = view.get("production", {})
            rdf_triple_count = int(prod.get("triple_count") or 0)
            quarantine_count = int(view.get("quarantine", {}).get("assertion_count") or 0)
            report = view.get("shacl_report") or {}
            total_a = int(report.get("totalAssertions") or 0)
            passed = int(report.get("passed") or 0)
            if total_a > 0:
                shacl_pass_rate = round(passed / total_a * 100, 1)
            elif report.get("conforms") is True:
                shacl_pass_rate = 100.0
            elif rdf_triple_count > 0:
                # Fallback when runtime SHACL report payload is unavailable:
                # estimate pass rate from production triples vs quarantine assertions.
                denom = rdf_triple_count + quarantine_count
                if denom > 0:
                    shacl_pass_rate = round(max(0.0, (rdf_triple_count / denom) * 100), 1)
        except Exception:
            pass

        try:
            from services.ontology_store import sparql_query
            from ontology import kb_graph_iri

            graph = kb_graph_iri(kb_id)
            ns = "https://datalens.local/ontology/"
            for layer_key, sparql in [
                ("vocabulary", f"SELECT (COUNT(?s) AS ?c) WHERE {{ GRAPH <{graph}> {{ ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{ns}BusinessTerm> }} }}"),
                ("rule", f"SELECT (COUNT(?s) AS ?c) WHERE {{ GRAPH <{graph}> {{ ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?t . VALUES ?t {{ <{ns}Metric> <{ns}BusinessRule> }} }} }}"),
                ("entity_concept", f"SELECT (COUNT(?s) AS ?c) WHERE {{ GRAPH <{graph}> {{ ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{ns}BusinessConcept> }} }}"),
                ("dimension", f"SELECT (COUNT(?s) AS ?c) WHERE {{ GRAPH <{graph}> {{ ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{ns}Dimension> }} }}"),
            ]:
                rows = sparql_query(sparql)
                if rows and rows[0].get("c") is not None:
                    layers[layer_key] = int(rows[0]["c"])
        except Exception:
            pass

    pipeline_phase = "idle"
    if last_run:
        if last_run.status == "running":
            pipeline_phase = "extracting"
        elif last_run.status == "completed":
            pipeline_phase = "completed"
        elif last_run.status == "failed":
            pipeline_phase = "failed"

    indexing_complete = total_docs == 0 or indexed_docs >= total_docs

    active_run = None
    if last_run and last_run.status == "running":
        active_run = {
            "source_type": last_run.source_type,
            "source_id": last_run.source_id,
        }

    return {
        "ok": True,
        "kb_id": kb_id,
        "pipeline_phase": pipeline_phase,
        "active_run": active_run,
        "indexing": {
            "total_documents": total_docs,
            "indexed_documents": indexed_docs,
            "complete": indexing_complete,
        },
        "extraction": {
            "run_id": last_run.id if last_run else None,
            "status": last_run.status if last_run else None,
            "progress_percent": progress_pct,
            "steps": extraction_steps,
            "started_at": last_run.started_at.isoformat() if last_run and last_run.started_at else None,
            "completed_at": last_run.completed_at.isoformat() if last_run and last_run.completed_at else None,
        },
        "layers_summary": layers,
        "quality": {
            "shacl_pass_rate": shacl_pass_rate,
            "quarantine_count": quarantine_count,
            "rdf_triple_count": rdf_triple_count,
        },
    }
