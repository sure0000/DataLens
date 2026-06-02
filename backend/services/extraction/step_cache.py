"""Persist per-step extraction triples so a failed pipeline can resume without re-calling the LLM."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import PipelineRun
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

CACHED_EXTRACTION_STEPS: tuple[str, ...] = (
    "term_extraction",
    "metric_extraction",
    "dimension_extraction",
    "rule_extraction",
    "relation_extraction",
    "hierarchy_building",
    "data_lineage",
    "join_extraction",
)


def _cache_dir(kb_id: int, run_id: int) -> Path:
    root = Path(".run") / "extraction-cache" / str(kb_id) / str(run_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_file(kb_id: int, run_id: int, step_key: str) -> Path:
    return _cache_dir(kb_id, run_id) / f"{step_key}.jsonl"


def triple_to_dict(triple: RawTriple) -> dict[str, Any]:
    return asdict(triple)


def triple_from_dict(data: dict[str, Any]) -> RawTriple:
    return RawTriple(
        subject=str(data["subject"]),
        predicate=str(data["predicate"]),
        object=str(data["object"]),
        object_is_uri=bool(data.get("object_is_uri", False)),
        lang=data.get("lang"),
        graph=data.get("graph"),
        confidence=float(data.get("confidence", 70.0)),
        source_type=str(data.get("source_type", "document")),
        provenance=data.get("provenance"),
    )


def step_cache_exists(kb_id: int, run_id: int, step_key: str) -> bool:
    path = _cache_file(kb_id, run_id, step_key)
    return path.is_file() and path.stat().st_size > 0


def save_step_triples(kb_id: int, run_id: int, step_key: str, triples: list[RawTriple]) -> None:
    path = _cache_file(kb_id, run_id, step_key)
    with path.open("w", encoding="utf-8") as fh:
        for triple in triples:
            fh.write(json.dumps(triple_to_dict(triple), ensure_ascii=False) + "\n")
    _logger.info("Cached %d triples for kb=%s run=%s step=%s", len(triples), kb_id, run_id, step_key)


def load_step_triples(kb_id: int, run_id: int, step_key: str) -> list[RawTriple]:
    path = _cache_file(kb_id, run_id, step_key)
    if not path.is_file():
        return []
    triples: list[RawTriple] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            triples.append(triple_from_dict(json.loads(line)))
    return triples


def step_status(steps: dict[str, Any] | None, step_key: str) -> str | None:
    if not isinstance(steps, dict):
        return None
    raw = steps.get(step_key)
    if isinstance(raw, dict):
        return str(raw.get("status")) if raw.get("status") is not None else None
    if isinstance(raw, str):
        return raw
    return None


def step_is_resumable(steps: dict[str, Any] | None, step_key: str, kb_id: int, cache_run_id: int) -> bool:
    return step_status(steps, step_key) == "done" and step_cache_exists(kb_id, cache_run_id, step_key)


def resume_options_payload(db: Session, kb_id: int, source_type: str, source_id: int) -> dict[str, Any]:
    """Build API payload describing whether the user can resume a failed pipeline."""
    from services.extraction.pipeline_status import pipeline_active_step, pipeline_failure_reason, step_label

    full_type = source_type if source_type.startswith("source:") else f"source:{source_type}"
    run = find_resumable_run(db, kb_id, full_type, source_id)
    if run is None:
        return {"can_resume": False}

    steps = run.steps if isinstance(run.steps, dict) else {}
    cached_steps = [
        key for key in CACHED_EXTRACTION_STEPS if step_is_resumable(steps, key, kb_id, run.id)
    ]
    active = pipeline_active_step(steps)
    failed_step = active
    if not failed_step:
        for key in CACHED_EXTRACTION_STEPS:
            if step_status(steps, key) == "failed":
                failed_step = key
                break
    if not failed_step and step_status(steps, "ontology_write") == "failed":
        failed_step = "ontology_write"

    return {
        "can_resume": True,
        "resume_from_run_id": run.id,
        "failed_at_step": failed_step,
        "failed_at_step_label": step_label(failed_step) if failed_step else None,
        "cached_steps": cached_steps,
        "cached_step_labels": [step_label(k) for k in cached_steps],
        "failure_reason": pipeline_failure_reason(run),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def find_resumable_run(
    db: Session,
    kb_id: int,
    source_type: str | None = None,
    source_id: int | None = None,
) -> PipelineRun | None:
    """Latest failed run for the same source that has at least one cached completed step."""
    q = select(PipelineRun).where(
        PipelineRun.knowledge_base_id == kb_id,
        PipelineRun.status == "failed",
    )
    if source_type is not None:
        q = q.where(PipelineRun.source_type == source_type)
    if source_id is not None:
        q = q.where(PipelineRun.source_id == source_id)

    for run in db.execute(q.order_by(PipelineRun.id.desc()).limit(5)).scalars():
        steps = run.steps if isinstance(run.steps, dict) else {}
        for key in CACHED_EXTRACTION_STEPS:
            if step_is_resumable(steps, key, kb_id, run.id):
                return run
        # ontology_write failed after extraction: all extraction steps done but no ontology cache needed
        if step_status(steps, "ontology_write") == "failed":
            if all(
                step_status(steps, k) in ("done", "skipped")
                for k in CACHED_EXTRACTION_STEPS
                if step_status(steps, k) is not None
            ):
                return run
    return None
