"""Extraction pipeline orchestrator — coordinates all extractors and writes to RDF."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from config import get_settings
from models import Document, DocumentChunk, KnowledgeDatabaseImport, KnowledgeEntry, KnowledgeGitSource, PipelineRun, TableMeta
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

_CHUNK_STEP_KEYS = (
    "term_extraction",
    "metric_caliber",
    "dimension_extraction",
    "rule_extraction",
    "relation_extraction",
    "hierarchy_building",
)


def _step_error(exc: Exception) -> str:
    return str(exc).strip()[:500] or exc.__class__.__name__


def _skipped_chunk_steps(reason: str) -> dict[str, Any]:
    return {key: {"status": "skipped", "reason": reason} for key in _CHUNK_STEP_KEYS}

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
    from services.extraction.pipeline_status import touch_pipeline_progress

    initial_steps = touch_pipeline_progress(
        {
            "term_extraction": "pending",
            "metric_caliber": "pending",
            "dimension_extraction": "pending",
            "rule_extraction": "pending",
            "relation_extraction": "pending",
            "hierarchy_building": "pending",
            "data_lineage": "pending",
            "join_extraction": "pending",
            "domain_term_extraction": "pending",
        },
    )
    run = PipelineRun(
        knowledge_base_id=kb_id,
        status="running",
        source_type=source_type,
        source_id=source_id,
        steps=initial_steps,
    )
    db.add(run)
    db.commit()
    return run


def _finish_pipeline_run(db: Session, run: PipelineRun, success: bool = True) -> None:
    run.status = "completed" if success else "failed"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


def _persist_pipeline_steps(db: Session, run: PipelineRun, steps: dict[str, Any]) -> None:
    """Write in-flight step progress and refresh progress_at heartbeat."""
    from services.extraction.pipeline_status import touch_pipeline_progress

    current = dict(run.steps) if isinstance(run.steps, dict) else {}
    for key, val in steps.items():
        current[key] = val
    run.steps = touch_pipeline_progress(current)
    db.commit()


# ── Query helpers ───────────────────────────────────────────────────────


def _json_text(column: Any, key: str) -> Any:
    """PostgreSQL JSON 字段取字符串值（须 cast 为 JSONB 才有 .astext）。"""
    return cast(column, JSONB)[key].astext


def _get_eligible_chunks(db: Session, kb_id: int, limit: int | None = None, source_type: str | None = None, source_id: int | None = None) -> list[Any]:
    if limit is None:
        limit = get_settings().extraction_max_chunks
    q = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status == "indexed",
            DocumentChunk.quality_score >= 0.4,
        )
    )
    if source_id is not None and source_type is not None:
        src = source_type.removeprefix("source:")
        if src == "git":
            q = q.join(KnowledgeEntry, KnowledgeEntry.id == Document.knowledge_entry_id).where(
                _json_text(KnowledgeEntry.source_meta, "kind") == "git_file",
                _json_text(KnowledgeEntry.source_meta, "git_source_id") == str(source_id),
            )
        elif src == "api":
            from sqlalchemy import or_

            q = q.join(KnowledgeEntry, KnowledgeEntry.id == Document.knowledge_entry_id).where(
                or_(
                    _json_text(KnowledgeEntry.source_meta, "api_source_id") == str(source_id),
                    _json_text(Document.source_meta, "api_source_id") == str(source_id),
                )
            )
        elif src in ("database",):
            q = q.where(_json_text(Document.source_meta, "import_id") == str(source_id))
        else:
            q = q.where(Document.knowledge_entry_id == source_id)
    return db.execute(
        q.order_by(DocumentChunk.quality_score.desc().nulls_last()).limit(limit)
    ).scalars().all()


_GIT_EXT_PRIORITY: dict[str, int] = {
    ".sql": 0,
    ".hql": 1,
    ".py": 2,
    ".yml": 3,
    ".yaml": 3,
}


def _entry_ref_path(entry: Any) -> str:
    meta = getattr(entry, "source_meta", None) or {}
    if isinstance(meta, dict):
        ref = str(meta.get("ref") or "").strip()
        if ref:
            return ref
    return str(getattr(entry, "title", "") or "")


def _git_ext_priority(path: str) -> int:
    lower = path.lower()
    for ext, pri in _GIT_EXT_PRIORITY.items():
        if lower.endswith(ext):
            return pri
    return 99


def _should_skip_git_entry(path: str, extraction_config: dict[str, Any] | None) -> bool:
    cfg = extraction_config or {}
    skip = cfg.get("skip_extensions") or []
    if cfg.get("extraction_profile") == "data_warehouse" and not skip:
        skip = [".ts", ".tsx", ".jsx"]
    lower = path.lower()
    for ext in skip:
        e = ext if str(ext).startswith(".") else f".{ext}"
        if lower.endswith(e):
            return True
    return False


def _resolve_git_extraction_config(db: Session, kb_id: int, source_id: int | None) -> dict[str, Any]:
    if source_id is None:
        return {}
    src = db.get(KnowledgeGitSource, source_id)
    if not src or src.knowledge_base_id != kb_id:
        return {}
    cfg = getattr(src, "extraction_config", None)
    return dict(cfg) if isinstance(cfg, dict) else {}


def _get_git_entries(
    db: Session,
    kb_id: int,
    limit: int = 200,
    source_type: str | None = None,
    source_id: int | None = None,
    extraction_config: dict[str, Any] | None = None,
) -> list[Any]:
    cfg = extraction_config if extraction_config is not None else _resolve_git_extraction_config(db, kb_id, source_id)
    if source_id is not None:
        src = db.get(KnowledgeGitSource, source_id)
        if src and src.knowledge_base_id == kb_id and src.max_files:
            limit = min(limit, int(src.max_files))

    q = select(KnowledgeEntry).where(
        KnowledgeEntry.knowledge_base_id == kb_id,
        _json_text(KnowledgeEntry.source_meta, "kind") == "git_file",
    )
    if source_id is not None and source_type is not None and source_type.removeprefix("source:") == "git":
        q = q.where(_json_text(KnowledgeEntry.source_meta, "git_source_id") == str(source_id))

    rows = list(db.execute(q).scalars().all())
    filtered = [e for e in rows if not _should_skip_git_entry(_entry_ref_path(e), cfg)]
    filtered.sort(key=lambda e: (_git_ext_priority(_entry_ref_path(e)), _entry_ref_path(e)))
    return filtered[:limit]


def _has_git_source(db: Session, kb_id: int) -> bool:
    return db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id).limit(1)
    ).first() is not None


def _resolve_domain_id(db: Session, kb_id: int) -> int | None:
    """Resolve a knowledge base ID to its primary business domain ID."""
    from models import BusinessDomainKnowledgeBase, KnowledgeBase
    row = db.execute(
        select(BusinessDomainKnowledgeBase.domain_id).where(
            BusinessDomainKnowledgeBase.knowledge_base_id == kb_id
        ).limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return int(row)

    # Backward-compatible fallback: many KBs only have knowledge_bases.business_domain_id
    kb_domain_id = db.execute(
        select(KnowledgeBase.business_domain_id).where(KnowledgeBase.id == kb_id).limit(1)
    ).scalar_one_or_none()
    return int(kb_domain_id) if kb_domain_id is not None else None


# ── Ontology injection context builder ────────────────────────────────────


def _build_ontology_injection_context(db: Session, kb_id: int, domain_id: int | None = None) -> str:
    """Build an ontology-awareness preamble injected into LLM extraction prompts.

    Queries the existing knowledge graph for known entities and relation types
    within the KB's domain, so the LLM can:
      - Re-use existing entity IRIs instead of creating duplicates
      - Use known relation types / class names
      - Respect the TBox schema

    Returns a short plain-text block prepended to the user message.
    """
    parts: list[str] = ["[本体上下文 - 请使用以下已知知识库信息]"]
    effective_domain = domain_id if domain_id is not None else kb_id

    parts.append(
        "已知实体类型: BusinessTerm(业务术语), Metric(指标), Dimension(维度), "
        "BusinessRule(业务规则), PhysicalTable(物理表), PhysicalColumn(列)"
    )
    parts.append(
        "已知关系类型: dependsOn(依赖), derivedFrom(派生), relatedTo(关联), "
        "aggregatesOver(聚合维度), computedFromTable(计算来源), "
        "mapsToColumn(映射到列), belongsToDomain(归属领域), groundedBy(证据来源)"
    )
    parts.append(
        "维度类型枚举: time(时间), geo(地理), category(分类), hierarchy(层级); "
        "规则类型枚举: validation(校验), derivation(派生), constraint(约束)"
    )

    try:
        from services.ontology.reader import OntologyReader
        from services.triple_store import get_triple_store
        store = get_triple_store()
        reader = OntologyReader(store)

        existing_terms = reader.list_terms(kb_id, limit=30)
        existing_metrics = reader.list_metrics(kb_id, limit=20)

        if existing_terms:
            term_strs = [f"{t.get('prefLabel','')}({t.get('iri','')})" for t in existing_terms[:30] if t.get('prefLabel')]
            if term_strs:
                parts.append(f"已有术语({len(term_strs)}): {', '.join(term_strs)}")

        if existing_metrics:
            metric_strs = [f"{m.get('prefLabel','')}({m.get('iri','')})" for m in existing_metrics[:20] if m.get('prefLabel')]
            if metric_strs:
                parts.append(f"已有指标({len(metric_strs)}): {', '.join(metric_strs)}")
    except Exception:
        pass

    from config import get_settings
    settings = get_settings()
    auto_threshold = settings.ontology_min_confidence_auto_approve
    parts.append(
        f"置信度规则: 清晰定义→≥80, 间接提及→50-70, 不确定则跳过。"
        f"置信度≥{auto_threshold}自动审批, <{auto_threshold}进入人工审核。"
    )

    return "\n".join(parts)


# ── Orchestrator ────────────────────────────────────────────────────────


class ExtractionOrchestrator:
    """Coordinates the full extraction pipeline: term → metric → relation → hierarchy → lineage.

    All results are written to RDF via OntologyWriter.write_many().
    """

    def __init__(self, writer: Any):
        self._writer = writer

    async def run(
        self,
        db: Session,
        kb_id: int,
        source_type: str | None = None,
        source_id: int | None = None,
        pipeline_run: PipelineRun | None = None,
        resume_from_run_id: int | None = None,
    ) -> dict[str, Any]:
        """Execute the full extraction pipeline for a knowledge base."""
        from services.extraction.step_cache import (
            load_step_triples,
            save_step_triples,
            step_is_resumable,
        )

        settings = get_settings()
        auto_approve = settings.ontology_min_confidence_auto_approve
        steps: dict[str, Any] = {}
        prior_steps: dict[str, Any] = {}
        resume_cache_run_id = resume_from_run_id
        if resume_from_run_id is not None:
            prior_run = db.get(PipelineRun, resume_from_run_id)
            if prior_run and isinstance(prior_run.steps, dict):
                prior_steps = prior_run.steps
                steps["_pipeline"] = {
                    **(prior_steps["_pipeline"] if isinstance(prior_steps.get("_pipeline"), dict) else {}),
                    "resumed_from_run_id": resume_from_run_id,
                }

        def _checkpoint() -> None:
            if pipeline_run is not None:
                _persist_pipeline_steps(db, pipeline_run, steps)

        def _save_step_cache(step_key: str, step_triples: list[RawTriple]) -> None:
            if pipeline_run is not None and step_triples:
                save_step_triples(kb_id, pipeline_run.id, step_key, step_triples)

        def _try_resume_step(step_key: str) -> bool:
            if resume_cache_run_id is None or pipeline_run is None:
                return False
            if not step_is_resumable(prior_steps, step_key, kb_id, resume_cache_run_id):
                return False
            cached = load_step_triples(kb_id, resume_cache_run_id, step_key)
            all_triples.extend(cached)
            prior_meta = prior_steps.get(step_key)
            steps[step_key] = (
                dict(prior_meta) if isinstance(prior_meta, dict) else {"status": "done", "triples": len(cached)}
            )
            _logger.info(
                "Resume kb=%s: skip step %s (%d triples from run %s)",
                kb_id,
                step_key,
                len(cached),
                resume_cache_run_id,
            )
            _checkpoint()
            return True

        client_info = _get_llm_client(db)
        if client_info is None:
            return {
                "status": "skipped",
                "reason": "no_llm_available",
                "steps": {"_pipeline": {"status": "skipped", "reason": "no_llm_available"}},
            }

        llm_client, model_name = client_info
        src = source_type.removeprefix("source:") if source_type else None

        chunks = _get_eligible_chunks(db, kb_id, source_type=source_type, source_id=source_id)
        if chunks:
            _logger.info(
                "Extraction kb=%s: %d chunks (max=%s), source=%s:%s",
                kb_id,
                len(chunks),
                get_settings().extraction_max_chunks,
                source_type,
                source_id,
            )
        git_extraction_config = _resolve_git_extraction_config(db, kb_id, source_id) if src == "git" else {}
        git_entries = (
            _get_git_entries(
                db,
                kb_id,
                source_type=source_type,
                source_id=source_id,
                extraction_config=git_extraction_config,
            )
            if src == "git" or _has_git_source(db, kb_id)
            else []
        )

        from services.extraction.git_entry_chunks import git_entries_as_llm_chunks


        min_body_chars = int(git_extraction_config.get("min_body_chars") or 50)
        llm_chunks = chunks
        if not llm_chunks and git_entries:
            llm_chunks = git_entries_as_llm_chunks(git_entries, min_body_chars=min_body_chars)
            if llm_chunks:
                _logger.info(
                    "Extraction kb=%s: %d git file bodies as LLM input (no document index), source=%s:%s",
                    kb_id,
                    len(llm_chunks),
                    source_type,
                    source_id,
                )

        if not llm_chunks and not git_entries:
            if src == "git":
                return {
                    "status": "skipped",
                    "reason": "no_git_entries",
                    "steps": {"_pipeline": {"status": "skipped", "reason": "no_git_entries"}},
                }
            return {
                "status": "skipped",
                "reason": "no_eligible_chunks",
                "steps": {"_pipeline": {"status": "skipped", "reason": "no_eligible_chunks"}},
            }

        if not llm_chunks:
            steps.update(_skipped_chunk_steps("no_document_chunks"))

        domain_id = _resolve_domain_id(db, kb_id)
        all_triples: list[RawTriple] = []
        step_lock = threading.Lock()
        git_scope_entries: list[Any] = []
        git_diag: Any = None

        # Build ontology injection context once for all extraction steps
        ontology_injection_context = _build_ontology_injection_context(db, kb_id, domain_id)

        def _chunk_progress(step_key: str):
            def _report(done: int, total: int) -> None:
                with step_lock:
                    steps[step_key] = {"status": "running", "chunk_done": done, "chunk_total": total}
                    meta = steps.get("_pipeline")
                    if not isinstance(meta, dict):
                        meta = {}
                    steps["_pipeline"] = {**meta, "active_step": step_key}
                    _checkpoint()

            return _report

        async def _run_extraction_step(step_key: str, extract_coro) -> None:
            """Run one pipeline step; independent steps may execute concurrently."""
            with step_lock:
                if steps.get(step_key, {}).get("status") == "done":
                    return
                if _try_resume_step(step_key):
                    return
                steps[step_key] = {"status": "running"}
                meta = steps.get("_pipeline")
                if not isinstance(meta, dict):
                    meta = {}
                steps["_pipeline"] = {**meta, "active_step": step_key}
                _checkpoint()

            try:
                with step_lock:
                    if steps.get(step_key, {}).get("status") == "done":
                        return
                triples = await extract_coro
                with step_lock:
                    if steps.get(step_key, {}).get("status") == "skipped":
                        return
                    all_triples.extend(triples)
                    steps[step_key] = {"status": "done", "triples": len(triples)}
                    _save_step_cache(step_key, triples)
                    _checkpoint()
            except Exception as exc:
                _logger.warning("%s failed for kb=%s", step_key, kb_id, exc_info=True)
                with step_lock:
                    steps[step_key] = {"status": "failed", "reason": _step_error(exc)}
                    _checkpoint()

        parallel_tasks: list[Any] = []

        if llm_chunks:
            from services.extraction.dimension_extractor import extract_dimension_triples
            from services.extraction.metric_extractor import extract_metric_triples
            from services.extraction.rule_extractor import extract_rule_triples
            from services.extraction.term_extractor import extract_term_triples

            parallel_tasks.extend(
                [
                    _run_extraction_step(
                        "term_extraction",
                        extract_term_triples(
                            kb_id=kb_id,
                            chunks=llm_chunks,
                            llm_client=llm_client,
                            model_name=model_name,
                            call_llm_json=_call_llm_json,
                            load_prompt=_load_prompt,
                            auto_approve_confidence=auto_approve,
                            domain_id=domain_id,
                            on_chunk_progress=_chunk_progress("term_extraction"),
                            ontology_context=ontology_injection_context,
                        ),
                    ),
                    _run_extraction_step(
                        "metric_caliber",
                        extract_metric_triples(
                            kb_id=kb_id,
                            chunks=llm_chunks,
                            llm_client=llm_client,
                            model_name=model_name,
                            call_llm_json=_call_llm_json,
                            load_prompt=_load_prompt,
                            auto_approve_confidence=auto_approve,
                            domain_id=domain_id,
                            on_chunk_progress=_chunk_progress("metric_caliber"),
                            ontology_context=ontology_injection_context,
                        ),
                    ),
                    _run_extraction_step(
                        "dimension_extraction",
                        extract_dimension_triples(
                            kb_id=kb_id,
                            chunks=llm_chunks,
                            llm_client=llm_client,
                            model_name=model_name,
                            call_llm_json=_call_llm_json,
                            load_prompt=_load_prompt,
                            auto_approve_confidence=auto_approve,
                            domain_id=domain_id,
                            on_chunk_progress=_chunk_progress("dimension_extraction"),
                            ontology_context=ontology_injection_context,
                        ),
                    ),
                    _run_extraction_step(
                        "rule_extraction",
                        extract_rule_triples(
                            kb_id=kb_id,
                            chunks=llm_chunks,
                            llm_client=llm_client,
                            model_name=model_name,
                            call_llm_json=_call_llm_json,
                            load_prompt=_load_prompt,
                            auto_approve_confidence=auto_approve,
                            domain_id=domain_id,
                            on_chunk_progress=_chunk_progress("rule_extraction"),
                            ontology_context=ontology_injection_context,
                        ),
                    ),
                ]
            )

        if git_entries or _has_git_source(db, kb_id):
            entries = git_entries or _get_git_entries(
                db,
                kb_id,
                source_type=source_type,
                source_id=source_id,
                extraction_config=git_extraction_config,
            )
            git_scope_entries = list(entries)

            from services.extraction.code_patterns.diagnostics import GitDiagnostics

            git_diag = GitDiagnostics(
                total_entries=len(entries),
                processed_limit=len(entries),
            )
            git_diag.min_body_chars = int(git_extraction_config.get("min_body_chars") or 50)
            for _entry in entries:
                _body = (getattr(_entry, "body", None) or "").strip()
                git_diag.record_entry(_entry, _body)

            async def _lineage_coro():
                from services.extraction.lineage_extractor import extract_lineage_triples

                return await extract_lineage_triples(
                    kb_id=kb_id,
                    entries=entries,
                    llm_client=llm_client,
                    model_name=model_name,
                    call_llm_json=_call_llm_json,
                    load_prompt=_load_prompt,
                    diagnostics=git_diag,
                    extraction_config=git_extraction_config,
                )

            async def _join_coro():
                from services.extraction.join_extractor import extract_join_triples

                return await extract_join_triples(
                    kb_id=kb_id,
                    entries=entries,
                    llm_client=llm_client,
                    model_name=model_name,
                    call_llm_json=_call_llm_json,
                    load_prompt=_load_prompt,
                    domain_tables=None,
                    diagnostics=git_diag,
                    extraction_config=git_extraction_config,
                )

            async def _domain_term_coro():
                from services.extraction.domain_term_extractor import extract_domain_term_triples

                return extract_domain_term_triples(
                    kb_id=kb_id,
                    entries=entries,
                    domain_id=domain_id,
                    diagnostics=git_diag,
                    extraction_config=git_extraction_config,
                    auto_approve_confidence=auto_approve,
                )

            if entries:
                parallel_tasks.extend(
                    [
                        _run_extraction_step("data_lineage", _lineage_coro()),
                        _run_extraction_step("join_extraction", _join_coro()),
                        _run_extraction_step("domain_term_extraction", _domain_term_coro()),
                    ]
                )
            else:
                with step_lock:
                    steps["data_lineage"] = {"status": "skipped", "reason": "no_git_entries"}
                    steps["join_extraction"] = {"status": "skipped", "reason": "no_git_entries"}
                    steps["domain_term_extraction"] = {"status": "skipped", "reason": "no_git_entries"}
                    _checkpoint()
        else:
            steps["data_lineage"] = {"status": "skipped", "reason": "no_git_source"}
            steps["join_extraction"] = {"status": "skipped", "reason": "no_git_source"}
            steps["domain_term_extraction"] = {"status": "skipped", "reason": "no_git_source"}

        if parallel_tasks:
            await asyncio.gather(*parallel_tasks)

        if llm_chunks:
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

            if term_iris or metric_iris:
                from services.extraction.hierarchy_builder import build_hierarchy_triples
                from services.extraction.relation_extractor import extract_relation_triples

                await asyncio.gather(
                    _run_extraction_step(
                        "relation_extraction",
                        extract_relation_triples(
                            kb_id=kb_id,
                            term_iris=term_iris,
                            metric_iris=metric_iris,
                            chunks=llm_chunks,
                            llm_client=llm_client,
                            model_name=model_name,
                            call_llm_json=_call_llm_json,
                            load_prompt=_load_prompt,
                        ),
                    ),
                    _run_extraction_step(
                        "hierarchy_building",
                        build_hierarchy_triples(
                            kb_id=kb_id,
                            term_iris=term_iris,
                            metric_iris=metric_iris,
                            llm_client=llm_client,
                            model_name=model_name,
                            call_llm_json=_call_llm_json,
                            load_prompt=_load_prompt,
                        ),
                    ),
                )
            elif not steps.get("relation_extraction"):
                steps["relation_extraction"] = {"status": "skipped", "reason": "no_concepts"}
                steps["hierarchy_building"] = {"status": "skipped", "reason": "no_concepts"}
                _checkpoint()

        if all_triples:
            try:
                write_result = self._writer.write_many(kb_id, all_triples)
                written = int(write_result.get("written") or 0)
                shacl_blocked = bool(write_result.get("shacl_blocked"))
                if shacl_blocked and written == 0:
                    steps["ontology_write"] = {
                        "status": "failed",
                        "total": len(all_triples),
                        "reason": "shacl_blocked",
                        "message": "入图被 SHACL 校验拦截，请检查质量与隔离区",
                        **write_result,
                    }
                elif written == 0:
                    steps["ontology_write"] = {
                        "status": "failed",
                        "total": len(all_triples),
                        "reason": "no_triples_written",
                        "message": "入图未写入任何三元组，请检查抽取与清洗结果",
                        **write_result,
                    }
                else:
                    steps["ontology_write"] = {"status": "done", "total": len(all_triples), **write_result}
            except Exception as exc:
                _logger.warning("Ontology write failed for kb=%s", kb_id, exc_info=True)
                steps["ontology_write"] = {"status": "failed", "total": len(all_triples), "reason": _step_error(exc)}
        else:
            steps["ontology_write"] = {"status": "skipped", "reason": "no_triples"}

        has_failures = any(isinstance(v, dict) and v.get("status") == "failed" for v in steps.values())
        if not all_triples and not has_failures and (git_scope_entries or chunks):
            from services.extraction.pipeline_status import humanize_reason

            hint = humanize_reason("no_triples")
            if git_scope_entries:
                try:
                    steps["_git_diagnostics"] = git_diag.to_dict()
                except Exception:
                    pass
            steps["ontology_write"] = {"status": "failed", "reason": "no_triples", "message": hint}
            steps["_pipeline"] = {
                "status": "failed",
                "reason": "no_triples",
                "message": hint,
            }
            return {
                "status": "failed",
                "reason": "no_triples",
                "steps": steps,
                "total_triples": 0,
            }

        return {
            "status": "failed" if has_failures else "completed",
            "steps": steps,
            "total_triples": len(all_triples),
        }


# ── Top-level entry point ───────────────────────────────────────────────


async def run_database_schema_pipeline(db: Session, kb_id: int, import_id: int) -> dict[str, Any]:
    """Sync analyzed physical tables for a database import into the ontology."""
    from services.ontology_population import sync_physical_table_to_ontology

    di = db.get(KnowledgeDatabaseImport, import_id)
    if di is None:
        return {
            "status": "failed",
            "reason": "database_import_not_found",
            "steps": {"_pipeline": {"status": "failed", "reason": "database_import_not_found"}},
        }

    table_rows = db.execute(
        select(TableMeta.id, TableMeta.status).where(
            TableMeta.datasource_id == di.datasource_id,
            TableMeta.database_name.in_(di.database_names or []),
        )
    ).all()

    if not table_rows:
        return {
            "status": "skipped",
            "reason": "no_tables_found",
            "steps": {
                "_pipeline": {"status": "skipped", "reason": "no_tables_found", "pipeline_kind": "database_schema_sync"},
                "physical_schema": {"status": "skipped", "reason": "no_tables_found"},
            },
        }

    done_ids = [int(tid) for tid, status in table_rows if status == "done"]
    pending = len(table_rows) - len(done_ids)
    if not done_ids:
        return {
            "status": "skipped",
            "reason": "no_analyzed_tables",
            "steps": {
                "_pipeline": {"status": "skipped", "reason": "no_analyzed_tables", "pipeline_kind": "database_schema_sync"},
                "physical_schema": {
                    "status": "skipped",
                    "reason": "no_analyzed_tables",
                    "pending_tables": len(table_rows),
                },
            },
        }

    from models import TableKnowledgeBase

    synced = 0
    line_count = 0
    literal_count = 0
    shacl_blocked = False
    for tid in done_ids:
        out = sync_physical_table_to_ontology(db, tid, kb_id, datasource_id=di.datasource_id)
        written = int(out.get("written") or 0)
        line_count += written
        literal_count += int(out.get("literal_count") or 0)
        if out.get("shacl_blocked"):
            shacl_blocked = True
        synced += 1
        existing_link = db.execute(
            select(TableKnowledgeBase).where(
                TableKnowledgeBase.table_id == tid,
                TableKnowledgeBase.knowledge_base_id == kb_id,
            )
        ).scalar_one_or_none()
        if existing_link is None:
            db.add(TableKnowledgeBase(table_id=tid, knowledge_base_id=kb_id))
    db.commit()

    if shacl_blocked or literal_count == 0:
        return {
            "status": "failed",
            "reason": "shacl_blocked" if shacl_blocked else "no_attributes_written",
            "steps": {
                "physical_schema": {
                    "status": "failed",
                    "reason": "shacl_blocked" if shacl_blocked else "no_attributes_written",
                    "tables": synced,
                    "statements": line_count,
                },
                "_pipeline": {
                    "status": "failed",
                    "pipeline_kind": "database_schema_sync",
                    "reason": "shacl_blocked" if shacl_blocked else "no_attributes_written",
                    "message": "Schema 入图被 SHACL 拦截，请到「质量与隔离」查看详情"
                    if shacl_blocked
                    else "语义清洗未写入任何属性，请确认表已在数据源侧完成 AI 分析",
                },
            },
        }

    steps: dict[str, Any] = {
        "physical_schema": {
            "status": "done",
            "tables": synced,
            "statements": line_count,
            "literal_attributes": literal_count,
        },
        "_pipeline": {
            "status": "completed",
            "pipeline_kind": "database_schema_sync",
            "message": f"已同步 {synced} 张已分析表到本体",
        },
    }
    if pending:
        steps["_pipeline"]["reason"] = f"synced_with_pending:{pending}"
        steps["_pipeline"]["message"] = (
            f"已同步 {synced} 张已分析表，另有 {pending} 张待分析"
        )

    return {"status": "completed", "steps": steps, "total_triples": line_count}


def _finalize_pipeline_run(db: Session, run: PipelineRun, result: dict[str, Any]) -> dict[str, Any]:
    """Persist step details and set run status from orchestrator result."""
    from services.extraction.pipeline_status import humanize_reason, pipeline_failure_reason

    steps = result.get("steps") if isinstance(result.get("steps"), dict) else {}
    reason = result.get("reason")
    status = result.get("status")

    if reason and "_pipeline" not in steps:
        steps = {**steps, "_pipeline": {"status": status or "failed", "reason": reason}}

    run.steps = steps
    db.flush()

    if status == "completed":
        success = True
    elif status == "skipped":
        success = False
    else:
        success = False

    if not success:
        pipeline_meta = steps.get("_pipeline") if isinstance(steps.get("_pipeline"), dict) else {}
        if not pipeline_meta.get("message"):
            run.steps = steps
            message = pipeline_failure_reason(run) or humanize_reason(str(reason or status or "unknown"))
            steps = {
                **steps,
                "_pipeline": {
                    **pipeline_meta,
                    "status": status or "failed",
                    "reason": pipeline_meta.get("reason") or reason or status,
                    "message": message,
                },
            }
            run.steps = steps
    elif status == "skipped" and isinstance(steps.get("_pipeline"), dict) and not steps["_pipeline"].get("message"):
        steps["_pipeline"]["message"] = humanize_reason(str(reason or "unknown"))
        run.steps = steps

    _finish_pipeline_run(db, run, success=success)
    return {**result, "run_id": run.id}


async def run_extraction_pipeline(
    db: Session,
    kb_id: int,
    source_type: str | None = None,
    source_id: int | None = None,
    skip_if_running: bool = True,
    resume: bool = False,
    resume_from_run_id: int | None = None,
) -> dict[str, Any]:
    """Run the full ontology-native extraction pipeline for a knowledge base.

    Orchestrates: term → metric → relation → hierarchy → lineage extraction,
    writing all results to RDF through OntologyWriter (clean → SHACL → production).
    """
    from services.extraction.pipeline_status import (
        fail_stale_pipeline_run,
        is_pipeline_run_stale,
        pipeline_execution_timeout_seconds,
        pipeline_run_elapsed_seconds,
    )

    if skip_if_running:
        running_q = select(PipelineRun).where(
            PipelineRun.knowledge_base_id == kb_id,
            PipelineRun.status == "running",
        )
        if source_type and source_id is not None:
            running_q = running_q.where(
                PipelineRun.source_type == source_type,
                PipelineRun.source_id == source_id,
            )
        existing = db.execute(running_q).scalars().first()
        if existing:
            if is_pipeline_run_stale(existing):
                from services.extraction.pipeline_status import pipeline_active_step

                active = pipeline_active_step(existing.steps if isinstance(existing.steps, dict) else {})
                _logger.warning(
                    "PipelineRun %s stuck for %ss at step=%s, auto-failing",
                    existing.id,
                    pipeline_run_elapsed_seconds(existing),
                    active or "unknown",
                )
                fail_stale_pipeline_run(existing)
                db.commit()
            else:
                return {"status": "skipped", "reason": "already_running", "run_id": existing.id}

    from services.extraction.step_cache import find_resumable_run

    resumable_run: PipelineRun | None = None
    if resume_from_run_id is not None:
        resumable_run = db.get(PipelineRun, resume_from_run_id)
    elif resume:
        resumable_run = find_resumable_run(db, kb_id, source_type, source_id)

    resume_id = resumable_run.id if resumable_run else None
    if resume_id:
        _logger.info("Resuming extraction for kb=%s from failed run %s", kb_id, resume_id)

    run = _start_pipeline_run(db, kb_id, source_type, source_id)
    src_key = source_type.removeprefix("source:") if source_type else None

    if src_key == "database" and source_id is not None:
        try:
            result = await run_database_schema_pipeline(db, kb_id, int(source_id))
        except Exception as exc:
            _logger.warning("Database schema pipeline failed for kb=%s import=%s", kb_id, source_id, exc_info=True)
            result = {
                "status": "failed",
                "reason": str(exc)[:500],
                "steps": {"_pipeline": {"status": "failed", "reason": _step_error(exc)}},
            }
        return _finalize_pipeline_run(db, run, result)

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
        exec_timeout = pipeline_execution_timeout_seconds()
        result = await asyncio.wait_for(
            orchestrator.run(
                db,
                kb_id,
                source_type=source_type,
                source_id=source_id,
                pipeline_run=run,
                resume_from_run_id=resume_id,
            ),
            timeout=exec_timeout,
        )
    except asyncio.TimeoutError:
        from services.extraction.pipeline_status import pipeline_active_step, step_label

        active = pipeline_active_step(run.steps if isinstance(run.steps, dict) else {})
        _logger.warning(
            "Extraction pipeline timed out for kb=%s after %ss at step=%s",
            kb_id,
            exec_timeout,
            active or "unknown",
        )
        steps_out = dict(run.steps) if isinstance(run.steps, dict) else {}
        steps_out["_pipeline"] = {
            "status": "failed",
            "reason": "pipeline_timeout",
            "active_step": active,
            "message": (
                f"抽取整体超时（超过 {exec_timeout // 60} 分钟）"
                + (f"，停留在步骤：{step_label(active)}" if active else "")
            ),
        }
        if active and isinstance(steps_out.get(active), dict):
            steps_out[active] = {**steps_out[active], "status": "failed", "reason": "pipeline_timeout"}
        result = {"status": "timeout", "reason": "pipeline_timeout", "steps": steps_out}
        return _finalize_pipeline_run(db, run, result)
    except Exception as exc:
        from services.extraction.pipeline_status import humanize_reason

        _logger.warning("Extraction pipeline failed for kb=%s", kb_id, exc_info=True)
        err = _step_error(exc)
        result = {
            "status": "failed",
            "reason": err,
            "steps": {
                **(run.steps if isinstance(run.steps, dict) else {}),
                "_pipeline": {
                    "status": "failed",
                    "reason": err,
                    "message": humanize_reason(err),
                },
            },
        }
        return _finalize_pipeline_run(db, run, result)

    out = _finalize_pipeline_run(db, run, result)
    if resume_id:
        out["resumed_from_run_id"] = resume_id
    return out


def trigger_extraction_pipeline_background(
    kb_id: int,
    source_type: str = "auto",
    source_id: int | None = None,
    resume: bool = False,
    resume_from_run_id: int | None = None,
) -> None:
    """Trigger extraction pipeline in a background daemon thread."""

    def _run():
        from database import SessionLocal
        db = SessionLocal()
        try:
            asyncio.run(
                run_extraction_pipeline(
                    db,
                    kb_id,
                    source_type=source_type,
                    source_id=source_id,
                    resume=resume,
                    resume_from_run_id=resume_from_run_id,
                )
            )
        except Exception:
            _logger.exception("Background extraction pipeline failed for kb=%s", kb_id)
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True, name=f"extraction-pipeline-kb-{kb_id}")
    t.start()
    _logger.info("Started background extraction pipeline for kb=%s", kb_id)
