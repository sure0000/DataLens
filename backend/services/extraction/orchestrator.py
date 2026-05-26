"""Extraction pipeline orchestrator — coordinates all extractors and writes to RDF."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Document, DocumentChunk, KnowledgeEntry, KnowledgeGitSource, PipelineRun
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

# ── LLM helpers (shared with old semantic_extraction until Phase 4) ──────


async def _call_llm_json(
    client: Any, model_name: str, system_prompt: str, user_message: str,
    temperature: float = 0.1, timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    import json, re
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
        timeout=timeout_seconds,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        _logger.warning("Failed to parse LLM JSON response: %s", raw[:200])
        return {}


def _get_llm_client(db: Session) -> tuple[Any, str] | None:
    try:
        from services.llm_models import has_any_llm_key, resolve_effective_model
        if not has_any_llm_key(db):
            return None
        settings = get_settings()
        semantic_ref = getattr(settings, "semantic_model_ref", None)
        model_ref = resolve_effective_model(semantic_ref, db)
        if not model_ref:
            return None
        from services.llm_service import _client_and_model_for_ref
        return _client_and_model_for_ref(model_ref, db)
    except Exception:
        _logger.warning("Failed to get LLM client", exc_info=True)
        return None


def _load_prompt(name: str) -> str:
    from prompts import load_prompt
    return load_prompt(name)


# ── Pipeline run helpers ────────────────────────────────────────────────


def _start_pipeline_run(db: Session, kb_id: int, source_type: str | None = None, source_id: int | None = None) -> PipelineRun:
    run = PipelineRun(
        knowledge_base_id=kb_id,
        status="running",
        source_type=source_type,
        source_id=source_id,
        steps={
            "term_extraction": "pending",
            "metric_caliber": "pending",
            "dimension_extraction": "pending",
            "rule_extraction": "pending",
            "relation_extraction": "pending",
            "hierarchy_building": "pending",
            "data_lineage": "pending",
            "join_extraction": "pending",
        },
    )
    db.add(run)
    db.commit()
    return run


def _finish_pipeline_run(db: Session, run: PipelineRun, success: bool = True) -> None:
    run.status = "completed" if success else "failed"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


# ── Query helpers ───────────────────────────────────────────────────────


def _get_eligible_chunks(db: Session, kb_id: int, limit: int = 50) -> list[Any]:
    return db.execute(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status == "indexed",
            DocumentChunk.quality_score >= 0.4,
        )
        .order_by(DocumentChunk.quality_score.desc().nulls_last())
        .limit(limit)
    ).scalars().all()


def _get_git_entries(db: Session, kb_id: int, limit: int = 80) -> list[Any]:
    return db.execute(
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            KnowledgeEntry.source_meta["kind"].astext == "git_file",
        )
        .limit(limit)
    ).scalars().all()


def _has_git_source(db: Session, kb_id: int) -> bool:
    return db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id).limit(1)
    ).first() is not None


def _resolve_domain_id(db: Session, kb_id: int) -> int | None:
    """Resolve a knowledge base ID to its primary business domain ID."""
    from models import BusinessDomainKnowledgeBase
    row = db.execute(
        select(BusinessDomainKnowledgeBase.domain_id).where(
            BusinessDomainKnowledgeBase.knowledge_base_id == kb_id
        ).limit(1)
    ).scalar_one_or_none()
    return int(row) if row is not None else None


# ── Orchestrator ────────────────────────────────────────────────────────


class ExtractionOrchestrator:
    """Coordinates the full extraction pipeline: term → metric → relation → hierarchy → lineage.

    All results are written to RDF via OntologyWriter.write_many().
    """

    def __init__(self, writer: Any):
        self._writer = writer

    async def run(self, db: Session, kb_id: int) -> dict[str, Any]:
        """Execute the full extraction pipeline for a knowledge base.

        Returns a dict with per-step stats.
        """
        settings = get_settings()
        auto_approve = settings.ontology_min_confidence_auto_approve
        steps: dict[str, Any] = {}

        client_info = _get_llm_client(db)
        if client_info is None:
            return {"status": "skipped", "reason": "no_llm_available"}

        llm_client, model_name = client_info

        # 1. Get eligible chunks
        chunks = _get_eligible_chunks(db, kb_id)
        if not chunks:
            _logger.info("No eligible chunks for extraction in kb=%s", kb_id)
            return {"status": "skipped", "reason": "no_eligible_chunks"}

        # Resolve domain for belongsToDomain assertions
        domain_id = _resolve_domain_id(db, kb_id)

        # 2. Term extraction
        all_triples: list[RawTriple] = []
        try:
            from services.extraction.term_extractor import extract_term_triples
            term_triples = await extract_term_triples(
                kb_id=kb_id, chunks=chunks,
                llm_client=llm_client, model_name=model_name,
                call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                auto_approve_confidence=auto_approve,
                domain_id=domain_id,
            )
            all_triples.extend(term_triples)
            steps["term_extraction"] = {"status": "done", "triples": len(term_triples)}
        except Exception:
            _logger.warning("Term extraction failed for kb=%s", kb_id, exc_info=True)
            steps["term_extraction"] = {"status": "failed"}

        # 3. Metric extraction
        try:
            from services.extraction.metric_extractor import extract_metric_triples
            metric_triples = await extract_metric_triples(
                kb_id=kb_id, chunks=chunks,
                llm_client=llm_client, model_name=model_name,
                call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                auto_approve_confidence=auto_approve,
                domain_id=domain_id,
            )
            all_triples.extend(metric_triples)
            steps["metric_caliber"] = {"status": "done", "triples": len(metric_triples)}
        except Exception:
            _logger.warning("Metric extraction failed for kb=%s", kb_id, exc_info=True)
            steps["metric_caliber"] = {"status": "failed"}

        # 3.5. Dimension extraction
        try:
            from services.extraction.dimension_extractor import extract_dimension_triples
            dim_triples = await extract_dimension_triples(
                kb_id=kb_id, chunks=chunks,
                llm_client=llm_client, model_name=model_name,
                call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                auto_approve_confidence=auto_approve,
                domain_id=domain_id,
            )
            all_triples.extend(dim_triples)
            steps["dimension_extraction"] = {"status": "done", "triples": len(dim_triples)}
        except Exception:
            _logger.warning("Dimension extraction failed for kb=%s", kb_id, exc_info=True)
            steps["dimension_extraction"] = {"status": "failed"}

        # 3.6. Business rule extraction
        try:
            from services.extraction.rule_extractor import extract_rule_triples
            rule_triples = await extract_rule_triples(
                kb_id=kb_id, chunks=chunks,
                llm_client=llm_client, model_name=model_name,
                call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                auto_approve_confidence=auto_approve,
                domain_id=domain_id,
            )
            all_triples.extend(rule_triples)
            steps["rule_extraction"] = {"status": "done", "triples": len(rule_triples)}
        except Exception:
            _logger.warning("Rule extraction failed for kb=%s", kb_id, exc_info=True)
            steps["rule_extraction"] = {"status": "failed"}

        # 4. Build IRI maps for relation/hierarchy extraction
        term_iris: dict[str, str] = {}
        metric_iris: dict[str, str] = {}
        for t in all_triples:
            pred = str(t.predicate)
            if pred == "http://www.w3.org/2004/02/skos/core#prefLabel":
                name = str(t.object).lower()
                if "term/" in str(t.subject):
                    term_iris[name] = str(t.subject)
                elif "metric/" in str(t.subject):
                    metric_iris[name] = str(t.subject)

        # 5. Relation extraction
        if term_iris or metric_iris:
            try:
                from services.extraction.relation_extractor import extract_relation_triples
                rel_triples = await extract_relation_triples(
                    kb_id=kb_id, term_iris=term_iris, metric_iris=metric_iris,
                    chunks=chunks, llm_client=llm_client, model_name=model_name,
                    call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                )
                all_triples.extend(rel_triples)
                steps["relation_extraction"] = {"status": "done", "triples": len(rel_triples)}
            except Exception:
                _logger.warning("Relation extraction failed for kb=%s", kb_id, exc_info=True)
                steps["relation_extraction"] = {"status": "failed"}

            # 6. Hierarchy building
            try:
                from services.extraction.hierarchy_builder import build_hierarchy_triples
                hier_triples = await build_hierarchy_triples(
                    kb_id=kb_id, term_iris=term_iris, metric_iris=metric_iris,
                    llm_client=llm_client, model_name=model_name,
                    call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                )
                all_triples.extend(hier_triples)
                steps["hierarchy_building"] = {"status": "done", "triples": len(hier_triples)}
            except Exception:
                _logger.warning("Hierarchy building failed for kb=%s", kb_id, exc_info=True)
                steps["hierarchy_building"] = {"status": "failed"}
        else:
            steps["relation_extraction"] = {"status": "skipped", "reason": "no_concepts"}
            steps["hierarchy_building"] = {"status": "skipped", "reason": "no_concepts"}

        # 7. Lineage extraction (code-only KBs)
        if _has_git_source(db, kb_id):
            try:
                from services.extraction.lineage_extractor import extract_lineage_triples
                entries = _get_git_entries(db, kb_id)
                if entries:
                    lineage_triples = await extract_lineage_triples(
                        kb_id=kb_id, entries=entries,
                        llm_client=llm_client, model_name=model_name,
                        call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                    )
                    all_triples.extend(lineage_triples)
                    steps["data_lineage"] = {"status": "done", "triples": len(lineage_triples)}
                else:
                    steps["data_lineage"] = {"status": "skipped", "reason": "no_git_entries"}
            except Exception:
                _logger.warning("Lineage extraction failed for kb=%s", kb_id, exc_info=True)
                steps["data_lineage"] = {"status": "failed"}
        else:
            steps["data_lineage"] = {"status": "skipped", "reason": "no_git_source"}

        # 7.5. Join relation extraction (code-only KBs)
        if _has_git_source(db, kb_id):
            try:
                from services.extraction.join_extractor import extract_join_triples
                entries = _get_git_entries(db, kb_id)
                if entries:
                    join_triples = await extract_join_triples(
                        kb_id=kb_id, entries=entries,
                        llm_client=llm_client, model_name=model_name,
                        call_llm_json=_call_llm_json, load_prompt=_load_prompt,
                        domain_tables=None,
                    )
                    all_triples.extend(join_triples)
                    steps["join_extraction"] = {"status": "done", "triples": len(join_triples)}
                else:
                    steps["join_extraction"] = {"status": "skipped", "reason": "no_git_entries"}
            except Exception:
                _logger.warning("Join extraction failed for kb=%s", kb_id, exc_info=True)
                steps["join_extraction"] = {"status": "failed"}
        else:
            steps["join_extraction"] = {"status": "skipped", "reason": "no_git_source"}

        # 8. Write all triples through OntologyWriter → clean → SHACL → production/quarantine
        write_result: dict[str, Any] = {}
        if all_triples:
            try:
                write_result = self._writer.write_many(kb_id, all_triples)
                steps["ontology_write"] = {
                    "status": "done",
                    "total": len(all_triples),
                    **write_result,
                }
            except Exception:
                _logger.warning("Ontology write failed for kb=%s", kb_id, exc_info=True)
                steps["ontology_write"] = {"status": "failed", "total": len(all_triples)}
        else:
            steps["ontology_write"] = {"status": "skipped", "reason": "no_triples"}

        return {
            "status": "completed",
            "steps": steps,
            "total_triples": len(all_triples),
        }


# ── Top-level entry point ───────────────────────────────────────────────


async def run_extraction_pipeline(
    db: Session, kb_id: int, source_type: str | None = None, source_id: int | None = None, skip_if_running: bool = True,
) -> dict[str, Any]:
    """Run the full ontology-native extraction pipeline for a knowledge base.

    Orchestrates: term → metric → relation → hierarchy → lineage extraction,
    writing all results to RDF through OntologyWriter (clean → SHACL → production).
    """
    if skip_if_running:
        existing = db.execute(
            select(PipelineRun).where(
                PipelineRun.knowledge_base_id == kb_id,
                PipelineRun.status == "running",
            )
        ).scalars().first()
        if existing:
            elapsed = datetime.now(timezone.utc) - existing.started_at
            if elapsed.total_seconds() > 300:
                _logger.warning("PipelineRun %s stuck for %s, auto-failing", existing.id, elapsed)
                existing.status = "failed"
                existing.completed_at = datetime.now(timezone.utc)
                db.commit()
            else:
                return {"status": "skipped", "reason": "already_running", "run_id": existing.id}

    run = _start_pipeline_run(db, kb_id, source_type, source_id)

    try:
        from services.ontology.writer import OntologyWriter
        from services.ontology.validator import validate as shacl_validate
        from services.ontology.quarantine import QuarantineManager
        from services.triple_store import get_triple_store

        store = get_triple_store()
        writer = OntologyWriter(
            store=store,
            validator=shacl_validate,
            quarantine_manager=QuarantineManager(store),
        )
        orchestrator = ExtractionOrchestrator(writer)
        result = await asyncio.wait_for(orchestrator.run(db, kb_id), timeout=600)
    except asyncio.TimeoutError:
        _logger.warning("Extraction pipeline timed out for kb=%s", kb_id)
        result = {"status": "timeout", "steps": run.steps or {}}
        _finish_pipeline_run(db, run, success=False)
        return {**result, "run_id": run.id}
    except Exception:
        _logger.warning("Extraction pipeline failed for kb=%s", kb_id, exc_info=True)
        result = {"status": "failed", "steps": run.steps or {}}
        _finish_pipeline_run(db, run, success=False)
        return {**result, "run_id": run.id}

    run.steps = result.get("steps", {})
    success = result.get("status") == "completed"
    _finish_pipeline_run(db, run, success)
    return {**result, "run_id": run.id}


def trigger_extraction_pipeline_background(kb_id: int, source_type: str = "auto") -> None:
    """Trigger extraction pipeline in a background daemon thread."""

    def _run():
        from database import SessionLocal
        db = SessionLocal()
        try:
            asyncio.run(run_extraction_pipeline(db, kb_id, source_type=source_type))
        except Exception:
            _logger.exception("Background extraction pipeline failed for kb=%s", kb_id)
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True, name=f"extraction-pipeline-kb-{kb_id}")
    t.start()
    _logger.info("Started background extraction pipeline for kb=%s", kb_id)
