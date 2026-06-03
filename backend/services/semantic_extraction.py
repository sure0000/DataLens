"""AI 语义提取服务：从知识库文档中提取业务术语、指标口径和数据血缘。

设计原则：
- 复用现有 LLM 基础设施（_client_and_model_for_ref / resolve_effective_model）
- 提取结果写入 business_terms / metric_definitions / data_lineage 表
- 同 name + kb_id 去重（更新已有记录）
- 支持手动触发和自动触发（Git 同步后 / 文件导入后）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import (
    Document,
    DocumentChunk,
    KnowledgeEntry,
    KnowledgeGitSource,
    PipelineRun,
)
# BusinessTerm, DataLineage, MetricDefinition removed in Phase 1 ontology refactoring
# This module will be rewritten in Phase 2 to write directly to RDF via OntologyWriter
from services.semantic_relation_sync import concept_slug, sync_semantic_relations_for_kb

_logger = logging.getLogger(__name__)

# ── LLM Prompt Templates ──────────────────────────────────────────────

from prompts import load_prompt as _load_prompt

# ── Pipeline orchestration ────────────────────────────────────────────


async def _call_llm_json(client: Any, model_name: str, system_prompt: str, user_message: str, temperature: float = 0.1, timeout_seconds: float = 120.0) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 响应。"""
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
    """获取 LLM 客户端和模型名；不可用时返回 None。"""
    try:
        from services.llm_models import has_any_llm_key, resolve_effective_model
        if not has_any_llm_key(db):
            return None
        from config import get_settings
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


def _start_pipeline_run(db: Session, kb_id: int, source_type: str | None = None, source_id: int | None = None) -> PipelineRun:
    run = PipelineRun(
        knowledge_base_id=kb_id,
        status="running",
        source_type=source_type,
        source_id=source_id,
        steps={"term_extraction": "pending", "metric_extraction": "pending", "data_lineage": "pending"},
    )
    db.add(run)
    db.commit()
    return run


def _finish_pipeline_run(db: Session, run: PipelineRun, success: bool = True) -> None:
    run.status = "completed" if success else "failed"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


# ── Term Extraction ────────────────────────────────────────────────────


def _bound_table_refs_from_chunk(chunk: DocumentChunk) -> list[str]:
    meta = chunk.semantic_meta if isinstance(chunk.semantic_meta, dict) else {}
    grounding = meta.get("grounding") if isinstance(meta.get("grounding"), dict) else {}
    return [
        str(x).strip()
        for x in (grounding.get("table_refs") or [])
        if str(x or "").strip()
    ]


async def extract_terms_from_kb(db: Session, kb_id: int) -> int:
    """从知识库中已索引的文档分块提取业务术语。

    返回提取到的术语数量（含更新）。
    """
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.warning("No LLM available for term extraction, kb=%s", kb_id)
        return 0

    client, model_name = client_info

    # 获取已索引的文档分块（采样：最多取 50 个高分块）
    chunks_query = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status == "indexed",
            DocumentChunk.quality_score >= 0.4,
        )
        .order_by(DocumentChunk.quality_score.desc().nulls_last())
        .limit(50)
    )
    chunks = db.execute(chunks_query).scalars().all()

    if not chunks:
        _logger.info("No eligible chunks for term extraction in kb=%s", kb_id)
        return 0

    total_extracted = 0
    existing_names: set[str] = set()

    for chunk in chunks:
        try:
            result = await _call_llm_json(client, model_name, _load_prompt("extraction/term_extraction_system"), chunk.content)
            terms_data = result.get("terms", [])
        except Exception:
            _logger.warning("LLM term extraction failed for chunk %s", chunk.id, exc_info=True)
            continue

        for item in terms_data:
            name = (item.get("name") or "").strip()
            if not name or name in existing_names:
                continue
            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            # 去重检查
            existing = db.execute(
                select(BusinessTerm).where(
                    BusinessTerm.knowledge_base_id == kb_id,
                    BusinessTerm.name == name,
                )
            ).scalar_one_or_none()

            if existing:
                existing.type = item.get("type", existing.type) or "other"
                existing.definition = item.get("definition") or existing.definition
                existing.related_fields = item.get("related_fields", existing.related_fields) or []
                existing.confidence = round(confidence, 1)
                if not (existing.concept_id or "").strip():
                    existing.concept_id = concept_slug(name, "term")
                if confidence >= get_settings().semantic_auto_approve_confidence:
                    existing.status = "approved"
                existing.updated_at = datetime.now(timezone.utc)
            else:
                term = BusinessTerm(
                    knowledge_base_id=kb_id,
                    name=name,
                    type=item.get("type") or "other",
                    definition=item.get("definition") or "",
                    source_entry_id=chunk.document.knowledge_entry_id if chunk.document else None,
                    related_fields=item.get("related_fields") or [],
                    concept_id=concept_slug(name, "term"),
                    confidence=round(confidence, 1),
                    status="approved" if confidence >= get_settings().semantic_auto_approve_confidence else "pending_review",
                )
                db.add(term)

            existing_names.add(name)
            total_extracted += 1

    db.commit()
    _logger.info("Term extraction completed for kb=%s: %s terms", kb_id, total_extracted)
    return total_extracted


# ── Metric Extraction ──────────────────────────────────────────────────


async def extract_metrics_from_kb(db: Session, kb_id: int) -> int:
    """从知识库文档中提取指标口径定义。"""
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.warning("No LLM available for metric extraction, kb=%s", kb_id)
        return 0

    client, model_name = client_info

    # 获取文档（优先取 semantic_role 为 business_metric 的条目，其次取已索引文档）
    chunks_query = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status == "indexed",
            DocumentChunk.quality_score >= 0.4,
        )
        .order_by(DocumentChunk.quality_score.desc().nulls_last())
        .limit(50)
    )
    chunks = db.execute(chunks_query).scalars().all()

    if not chunks:
        return 0

    total_extracted = 0
    existing_names: set[str] = set()

    for chunk in chunks:
        try:
            result = await _call_llm_json(client, model_name, _load_prompt("extraction/metric_extraction_system"), chunk.content)
            metrics_data = result.get("metrics", [])
        except Exception:
            _logger.warning("LLM metric extraction failed for chunk %s", chunk.id, exc_info=True)
            continue

        for item in metrics_data:
            name = (item.get("name") or "").strip()
            if not name or name in existing_names:
                continue
            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            existing = db.execute(
                select(MetricDefinition).where(
                    MetricDefinition.knowledge_base_id == kb_id,
                    MetricDefinition.name == name,
                )
            ).scalar_one_or_none()

            bound_refs = _bound_table_refs_from_chunk(chunk)

            if existing:
                existing.formula = item.get("formula") or existing.formula
                existing.caliber = item.get("caliber", existing.caliber)
                existing.related_terms = item.get("related_terms", existing.related_terms) or []
                existing.confidence = round(confidence, 1)
                if not (existing.concept_id or "").strip():
                    existing.concept_id = concept_slug(name, "metric")
                if bound_refs:
                    existing.bound_table_refs = list(
                        dict.fromkeys((existing.bound_table_refs or []) + bound_refs)
                    )
                if confidence >= get_settings().semantic_auto_approve_confidence:
                    existing.status = "approved"
                existing.updated_at = datetime.now(timezone.utc)
            else:
                metric = MetricDefinition(
                    knowledge_base_id=kb_id,
                    name=name,
                    formula=item.get("formula") or "",
                    caliber=item.get("caliber"),
                    source_entry_id=chunk.document.knowledge_entry_id if chunk.document else None,
                    related_terms=item.get("related_terms") or [],
                    bound_table_refs=bound_refs,
                    concept_id=concept_slug(name, "metric"),
                    confidence=round(confidence, 1),
                    status="approved" if confidence >= get_settings().semantic_auto_approve_confidence else "pending_review",
                )
                db.add(metric)

            existing_names.add(name)
            total_extracted += 1

    db.commit()
    _logger.info("Metric extraction completed for kb=%s: %s metrics", kb_id, total_extracted)
    return total_extracted


# ── Lineage Extraction ─────────────────────────────────────────────────


async def extract_lineage_from_kb(db: Session, kb_id: int) -> int:
    """从知识库的 Git 源代码文件中提取数据血缘关系。"""
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.warning("No LLM available for lineage extraction, kb=%s", kb_id)
        return 0

    client, model_name = client_info

    # 获取 Git 来源的已索引文档条目
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    entries_query = (
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
        )
        .limit(80)
    )
    entries = db.execute(entries_query).scalars().all()

    if not entries:
        _logger.info("No git-sourced entries for lineage extraction in kb=%s", kb_id)
        return 0

    # 获取 Git 源 id
    git_sources = db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id)
    ).scalars().all()
    git_source_id = git_sources[0].id if git_sources else None

    total_extracted = 0
    existing_pairs: set[tuple[str, str]] = set()

    for entry in entries:
        body = (entry.body or "").strip()
        if not body or len(body) < 50:
            continue

        # 限制发送给 LLM 的文本长度
        text = body[:8000]

        try:
            result = await _call_llm_json(client, model_name, _load_prompt("engineering/lineage_extraction_system"), text)
            edges_data = result.get("edges", [])
        except Exception:
            _logger.warning("LLM lineage extraction failed for entry %s", entry.id, exc_info=True)
            continue

        for item in edges_data:
            source_table = (item.get("source_table") or "").strip()
            target_table = (item.get("target_table") or "").strip()
            if not source_table or not target_table:
                continue
            pair = (source_table, target_table)
            if pair in existing_pairs:
                continue

            lineage = DataLineage(
                knowledge_base_id=kb_id,
                git_source_id=git_source_id,
                source_table=source_table,
                target_table=target_table,
                source_field=item.get("source_field"),
                target_field=item.get("target_field"),
                layer=item.get("target_layer") or item.get("source_layer") or "DWD",
                transform_logic=item.get("transform_logic"),
                status="done",
            )
            db.add(lineage)
            existing_pairs.add(pair)
            total_extracted += 1

    db.commit()
    _logger.info("Lineage extraction completed for kb=%s: %s edges", kb_id, total_extracted)
    return total_extracted


# ── Pipeline Orchestration ─────────────────────────────────────────────


async def run_semantic_pipeline(db: Session, kb_id: int, source_type: str | None = None, source_id: int | None = None, skip_if_running: bool = True) -> dict[str, Any]:
    """编排执行完整的语义清洗流水线。"""
    if skip_if_running:
        existing = db.execute(
            select(PipelineRun).where(
                PipelineRun.knowledge_base_id == kb_id,
                PipelineRun.status == "running",
            )
        ).scalars().first()
        if existing:
            from services.extraction.pipeline_status import (
                fail_stale_pipeline_run,
                is_pipeline_run_stale,
                pipeline_run_elapsed_seconds,
            )

            if is_pipeline_run_stale(existing):
                _logger.warning(
                    "PipelineRun %s stuck for %ss, auto-failing",
                    existing.id,
                    pipeline_run_elapsed_seconds(existing),
                )
                fail_stale_pipeline_run(existing)
                db.commit()
            else:
                _logger.info("Semantic pipeline already running for kb=%s (run_id=%s), skipping", kb_id, existing.id)
                return {"status": "skipped", "reason": "已有正在运行的流水线", "run_id": existing.id}

    run = _start_pipeline_run(db, kb_id, source_type, source_id)
    steps_status: dict[str, Any] = {}
    from services.extraction.pipeline_status import pipeline_execution_timeout_seconds

    _pipeline_timeout = pipeline_execution_timeout_seconds()

    async def _run_steps() -> dict[str, Any]:
        # Step 1: 术语提取
        term_count = await extract_terms_from_kb(db, kb_id)
        steps_status["term_extraction"] = {"status": "done", "count": term_count}
        run.steps = steps_status
        db.commit()

        # Step 2: 指标口径提取
        metric_count = await extract_metrics_from_kb(db, kb_id)
        steps_status["metric_extraction"] = {"status": "done", "count": metric_count}
        run.steps = steps_status
        db.commit()

        # Step 3: 数据血缘（仅 Git 源知识库）
        has_git = db.execute(
            select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id).limit(1)
        ).first()
        if has_git:
            lineage_count = await extract_lineage_from_kb(db, kb_id)
            steps_status["data_lineage"] = {"status": "done", "count": lineage_count}
        else:
            steps_status["data_lineage"] = {"status": "skipped", "reason": "非代码库知识库"}
        run.steps = steps_status
        db.commit()

        # Step 5: 本体建模 — 同步术语/指标/血缘/关联表 → Fuseki RDF
        try:
            from config import get_settings
            if get_settings().ontology_enabled:
                from services.ontology_sync_service import sync_knowledge_base_to_rdf

                sync_out = sync_knowledge_base_to_rdf(db, kb_id)
                steps_status["ontology_modeling"] = {
                    "status": "done",
                    "written": sync_out.get("written", 0),
                    "quarantined": sync_out.get("quarantined", 0),
                    "physical_tables": sync_out.get("physical_tables", {}),
                }
            else:
                rel_stats = sync_semantic_relations_for_kb(db, kb_id)
                steps_status["ontology_modeling"] = {"status": "skipped", "reason": "ontology_disabled", **rel_stats}
        except Exception:
            _logger.warning("Ontology modeling sync failed for kb=%s", kb_id, exc_info=True)
            steps_status["ontology_modeling"] = {"status": "failed", "reason": "sync_error"}
        run.steps = steps_status
        db.commit()
        return steps_status

    try:
        steps_status = await asyncio.wait_for(_run_steps(), timeout=_pipeline_timeout)
    except asyncio.TimeoutError:
        _logger.warning("Semantic pipeline timed out after %ss for kb=%s", _pipeline_timeout, kb_id)
        if not steps_status:
            steps_status = {
                "term_extraction": {"status": "failed", "count": 0, "reason": "pipeline_timeout"},
                "metric_extraction": {"status": "failed", "count": 0, "reason": "pipeline_timeout"},
                "data_lineage": {"status": "failed", "count": 0, "reason": "pipeline_timeout"},
            }
        for key in ("term_extraction", "metric_extraction", "data_lineage"):
            if key not in steps_status:
                steps_status[key] = {"status": "failed", "count": 0, "reason": "pipeline_timeout"}
        run.steps = steps_status
        _finish_pipeline_run(db, run, success=False)
        return {"status": "timeout", "steps": steps_status, "run_id": run.id}
    except Exception:
        _logger.warning("Semantic pipeline failed for kb=%s", kb_id, exc_info=True)
        for key in ("term_extraction", "metric_extraction", "data_lineage"):
            if key not in steps_status:
                steps_status[key] = {"status": "failed", "count": 0, "reason": "unexpected_error"}
        run.steps = steps_status
        _finish_pipeline_run(db, run, success=False)
        return {"status": "failed", "steps": steps_status, "run_id": run.id}

    success = not any(
        s.get("status") == "failed" for s in steps_status.values() if isinstance(s, dict)
    )
    _finish_pipeline_run(db, run, success)

    return {
        "status": "completed" if success else "completed_with_errors",
        "steps": steps_status,
        "run_id": run.id,
    }


def trigger_semantic_pipeline_background(
    kb_id: int,
    source_type: str = "auto",
    source_id: int | None = None,
    skip_if_running: bool = True,
    resume: bool = False,
    resume_from_run_id: int | None = None,
) -> None:
    """在后台线程中触发语义提取流水线（术语、指标、血缘）。

    可从任意上下文（文件导入、API 导入、Git 同步）调用，不阻塞调用方。
    内置去重：若该知识库已有 running 状态的 PipelineRun 则跳过（除非 skip_if_running=False）。
    """
    def _run():
        import traceback
        from database import SessionLocal
        db2 = SessionLocal()
        try:
            from services.extraction.orchestrator import run_extraction_pipeline
            asyncio.run(
                run_extraction_pipeline(
                    db2,
                    kb_id,
                    source_type=source_type,
                    source_id=source_id,
                    skip_if_running=skip_if_running,
                    resume=resume,
                    resume_from_run_id=resume_from_run_id,
                )
            )
        except Exception:
            _logger.exception("Background semantic pipeline failed for kb=%s", kb_id)
            # Mark any orphaned running runs as failed
            try:
                from models import PipelineRun
                from datetime import datetime, timezone
                orphaned = db2.execute(
                    __import__('sqlalchemy').select(PipelineRun).where(
                        PipelineRun.knowledge_base_id == kb_id,
                        PipelineRun.status == "running",
                    )
                ).scalars().all()
                for r in orphaned:
                    r.status = "failed"
                    r.completed_at = datetime.now(timezone.utc)
                    r.steps = {
                        k: (v if isinstance(v, dict) else {"status": "failed", "reason": traceback.format_exc()[-500:]})
                        for k, v in (r.steps or {}).items()
                    }
                db2.commit()
            except Exception:
                pass
        finally:
            db2.close()

    t = threading.Thread(target=_run, daemon=True, name=f"semantic-pipeline-kb-{kb_id}")
    t.start()
    _logger.info("Started background semantic pipeline for kb=%s (source=%s)", kb_id, source_type)


def cleanup_orphaned_pipeline_runs() -> int:
    """服务启动时清理所有因进程重启而遗留的 running 状态 PipelineRun。"""
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            runs = db.execute(
                select(PipelineRun).where(PipelineRun.status == "running")
            ).scalars().all()
            count = 0
            from services.extraction.pipeline_status import humanize_reason

            for run in runs:
                run.status = "failed"
                steps = dict(run.steps) if isinstance(run.steps, dict) else {}
                steps["_pipeline"] = {
                    "status": "failed",
                    "reason": "server_restart",
                    "message": humanize_reason("server_restart"),
                }
                for key, val in list(steps.items()):
                    if key.startswith("_"):
                        continue
                    if not isinstance(val, dict):
                        steps[key] = {"status": "failed", "reason": "server_restart"}
                run.steps = steps
                run.completed_at = datetime.now(timezone.utc)
                count += 1
                _logger.warning("Cleaned up orphaned PipelineRun id=%s kb=%s", run.id, run.knowledge_base_id)
            if count:
                db.commit()
            return count
        finally:
            db.close()
    except Exception:
        _logger.warning("Failed to clean up orphaned pipeline runs", exc_info=True)
        return 0


# 模块加载时自动清理因服务重启遗留的 running 流水线
_orphaned_cleaned = cleanup_orphaned_pipeline_runs()
if _orphaned_cleaned:
    _logger.info("Cleaned up %s orphaned pipeline runs on startup", _orphaned_cleaned)
