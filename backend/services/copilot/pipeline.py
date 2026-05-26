"""Copilot query pipeline — ontology-driven query orchestration (Phase 4).

Pipeline flow:
  1. Intent classification
  2. SPARQL concept routing (OntologyRouter)
  3. Graph expansion (lineage/join)
  4. Context assembly (ContextAssembler)
  5. SQL generation (delegates to existing sql_gen)
  6. SQL review (delegates to existing sql_review)
  7. Execute + auto-fix

Replaces the old routing_bundle / context_builder / domain_router pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

_logger = logging.getLogger(__name__)


class CopilotPipeline:
    """Ontology-driven copilot query pipeline.

    All semantic routing uses SPARQL against the RDF knowledge graph.
    Schema and table metadata still come from PostgreSQL (tables/columns are
    infrastructure, not semantics).
    """

    def __init__(self, store: Any, db: Session):
        from services.copilot.router import OntologyRouter
        from services.copilot.context import ContextAssembler

        self._store = store
        self._db = db
        self._router = OntologyRouter(store)
        self._assembler = ContextAssembler(store)

    def route(
        self,
        question: str,
        kb_ids: list[int] | None = None,
        *,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Run the ontology routing stage only.

        Returns concepts, candidate tables, and expanded tables.
        """
        if not kb_ids:
            kb_ids = self._get_default_kb_ids()

        route_result = self._router.full_route(kb_ids, question, top_k=top_k)
        return route_result

    def build_context(
        self,
        question: str,
        kb_ids: list[int] | None = None,
        *,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Run full routing + context assembly.

        Returns structured context ready for LLM prompt injection.
        """
        if not kb_ids:
            kb_ids = self._get_default_kb_ids()

        route_result = self._router.full_route(kb_ids, question, top_k=top_k)
        context = self._assembler.build_context(kb_ids, route_result)

        return {
            "routing": route_result,
            "context": context,
            "kb_ids": kb_ids,
        }

    def _get_default_kb_ids(self) -> list[int]:
        """Get KB IDs from configured business domain KBs, or all active KBs."""
        try:
            from models import KnowledgeBase
            from sqlalchemy import select

            kbs = self._db.execute(
                select(KnowledgeBase.id)
            ).scalars().all()
            return [int(k) for k in kbs]
        except Exception:
            return []


# ── Convenience function ─────────────────────────────────────────────────


def route_question(
    db: Session,
    question: str,
    kb_ids: list[int] | None = None,
    domain_id: int | None = None,
) -> dict[str, Any]:
    """Route a user question through the ontology graph and return context.

    This is the main entry point for the copilot query pipeline.
    """
    from services.triple_store import get_triple_store

    store = get_triple_store()

    if domain_id and not kb_ids:
        try:
            from models import BusinessDomainKnowledgeBase
            from sqlalchemy import select

            rows = db.execute(
                select(BusinessDomainKnowledgeBase.knowledge_base_id).where(
                    BusinessDomainKnowledgeBase.domain_id == domain_id
                )
            ).scalars().all()
            kb_ids = [int(r) for r in rows]
        except Exception:
            pass

    pipeline = CopilotPipeline(store, db)
    return pipeline.build_context(question, kb_ids)
