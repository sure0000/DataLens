"""Lightweight ingestion/modeling event bus (in-process)."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

_logger = logging.getLogger(__name__)

EventHandler = Callable[..., None]

_subscribers: dict[str, list[EventHandler]] = defaultdict(list)


def subscribe(event: str, handler: EventHandler) -> None:
    _subscribers[event].append(handler)


def emit(event: str, **payload: Any) -> None:
    for handler in list(_subscribers.get(event, [])):
        try:
            handler(**payload)
        except Exception:
            _logger.warning("Event handler failed for %s", event, exc_info=True)


def _on_document_indexed(**payload: Any) -> None:
    kb_id = payload.get("kb_id")
    document_id = payload.get("document_id")
    _logger.info(
        "document.indexed kb=%s doc=%s — scheduling extraction pipeline",
        kb_id,
        document_id,
    )
    if kb_id is None:
        return
    try:
        from services.extraction.orchestrator import trigger_extraction_pipeline_background

        trigger_extraction_pipeline_background(int(kb_id), source_type="document.indexed")
    except Exception:
        _logger.warning("Failed to trigger extraction after document.indexed", exc_info=True)


def _on_evidence_normalized(**payload: Any) -> None:
    kb_id = payload.get("kb_id")
    asset_kind = payload.get("asset_kind")
    _logger.info("evidence.normalized kb=%s asset=%s", kb_id, asset_kind)
    if kb_id is None:
        return
    if asset_kind == "physical_schema":
        return
    if asset_kind in ("semantic_doc", "processing_code", "relation_lineage", "ttl_bundle"):
        try:
            from services.extraction.orchestrator import trigger_extraction_pipeline_background

            trigger_extraction_pipeline_background(int(kb_id), source_type=f"evidence.{asset_kind}")
        except Exception:
            _logger.warning("Failed to trigger extraction after evidence.normalized", exc_info=True)


def _on_schema_analyzed(**payload: Any) -> None:
    table_id = payload.get("table_id")
    db = payload.get("db")
    if table_id is None or db is None:
        return
    try:
        from sqlalchemy import select

        from models import TableKnowledgeBase
        from services.ontology_population import sync_physical_table_to_ontology

        kb_ids = db.execute(
            select(TableKnowledgeBase.knowledge_base_id).where(
                TableKnowledgeBase.table_id == int(table_id)
            )
        ).scalars().all()
        for kb_id in kb_ids:
            sync_physical_table_to_ontology(db, int(table_id), int(kb_id))
            from services.extraction.orchestrator import trigger_extraction_pipeline_background

            trigger_extraction_pipeline_background(int(kb_id), source_type="schema.analyzed")
    except Exception:
        _logger.warning("schema.analyzed handler failed table=%s", table_id, exc_info=True)


def _on_git_sync_completed(**payload: Any) -> None:
    kb_id = payload.get("kb_id")
    if kb_id is None:
        return
    try:
        from services.extraction.orchestrator import trigger_extraction_pipeline_background

        trigger_extraction_pipeline_background(int(kb_id), source_type="git.sync.completed")
    except Exception:
        _logger.warning("git.sync.completed handler failed kb=%s", kb_id, exc_info=True)


def _on_assertion_promoted(**payload: Any) -> None:
    kb_id = payload.get("kb_id")
    if kb_id is None:
        return
    kid = int(kb_id)
    try:
        from services.ontology_reasoning import materialize_inferred_closure

        materialize_inferred_closure(0, kid)
    except Exception:
        _logger.warning("assertion.promoted inference refresh failed kb=%s", kb_id, exc_info=True)

    def _refresh_pg_cache() -> None:
        try:
            from database import SessionLocal
            from services.ontology_sync_service import refresh_kb_pg_semantic_cache

            db = SessionLocal()
            try:
                stats = refresh_kb_pg_semantic_cache(db, kid)
                _logger.info("assertion.promoted PG cache refreshed kb=%s stats=%s", kid, stats)
            finally:
                db.close()
        except Exception:
            _logger.warning("assertion.promoted PG cache refresh failed kb=%s", kid, exc_info=True)

    try:
        threading.Thread(target=_refresh_pg_cache, daemon=True, name=f"pg-cache-kb-{kid}").start()
    except Exception:
        _logger.warning("assertion.promoted PG cache thread failed kb=%s", kid, exc_info=True)


def register_default_handlers() -> None:
    subscribe("document.indexed", _on_document_indexed)
    subscribe("evidence.normalized", _on_evidence_normalized)
    subscribe("schema.analyzed", _on_schema_analyzed)
    subscribe("git.sync.completed", _on_git_sync_completed)
    subscribe("assertion.promoted", _on_assertion_promoted)


register_default_handlers()
