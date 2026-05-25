"""Sync PostgreSQL semantic layer + linked tables into RDF (Fuseki named graphs)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BusinessDomainKnowledgeBase, TableKnowledgeBase
from services.context_builder import tables_from_business_domain
from services.ontology_population import migrate_legacy_entities_to_triples, sync_physical_table_to_ontology
from services.ontology_reasoning import materialize_inferred_closure
from services.ontology_store import delete_graph
from services.ontology_triple_cleaner import clean_triples, persist_clean_result
from ontology import kb_graph_iri

_logger = logging.getLogger(__name__)


def _domain_tables_for_kb(db: Session, kb_id: int) -> list:
    row = db.execute(
        select(BusinessDomainKnowledgeBase.domain_id).where(
            BusinessDomainKnowledgeBase.knowledge_base_id == kb_id
        )
    ).first()
    if not row:
        return []
    return tables_from_business_domain(db, int(row[0]))


def sync_linked_physical_tables(db: Session, kb_id: int) -> dict[str, int]:
    table_ids = list(
        db.execute(
            select(TableKnowledgeBase.table_id).where(TableKnowledgeBase.knowledge_base_id == kb_id)
        ).scalars().all()
    )
    lines = 0
    for tid in table_ids:
        try:
            lines += sync_physical_table_to_ontology(db, int(tid), kb_id)
        except Exception:
            _logger.warning("Physical table ontology sync failed table=%s kb=%s", tid, kb_id, exc_info=True)
    return {"tables": len(table_ids), "triple_lines": lines}


def sync_knowledge_base_to_rdf(
    db: Session,
    kb_id: int,
    *,
    clear_production_graph: bool = True,
    sync_physical_tables: bool = True,
) -> dict[str, Any]:
    """Full KB → RDF production graph sync (pipeline final step)."""
    domain_tables = _domain_tables_for_kb(db, kb_id)
    raw = migrate_legacy_entities_to_triples(db, kb_id)
    cleaned = clean_triples(raw, kb_id=kb_id, domain_tables=domain_tables)
    if clear_production_graph:
        delete_graph(kb_graph_iri(kb_id))
    out = persist_clean_result(cleaned, kb_id)
    materialize_inferred_closure(0, kb_id)
    table_stats: dict[str, int] = {"tables": 0, "triple_lines": 0}
    if sync_physical_tables:
        table_stats = sync_linked_physical_tables(db, kb_id)
    return {
        **out,
        "physical_tables": table_stats,
        "domain_table_count": len(domain_tables),
    }
