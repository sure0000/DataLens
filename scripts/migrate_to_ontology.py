#!/usr/bin/env python3
"""One-shot ETL: PostgreSQL semantic tables → Fuseki / in-memory RDF."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from config import get_settings
from models import BusinessDomainKnowledgeBase, KnowledgeBase
from services.ontology_loader import init_ontology
from services.ontology_population import migrate_legacy_entities_to_triples, sync_physical_table_to_ontology
from services.ontology_triple_cleaner import clean_triples, persist_clean_result
from services.ontology_store import graph_stats


def migrate_kb(db: Session, kb_id: int, domain_id: int = 0) -> dict:
    raw = migrate_legacy_entities_to_triples(db, kb_id, domain_id=domain_id)
    result = clean_triples(raw, kb_id=kb_id, domain_tables=[])
    return persist_clean_result(result, kb_id)


def migrate_all(db: Session) -> dict:
    init_ontology()
    summary: dict = {"kbs": [], "tables": 0}
    kbs = db.execute(select(KnowledgeBase)).scalars().all()
    for kb in kbs:
        domain_row = db.execute(
            select(BusinessDomainKnowledgeBase.domain_id).where(
                BusinessDomainKnowledgeBase.knowledge_base_id == kb.id
            )
        ).first()
        domain_id = int(domain_row[0]) if domain_row else 0
        kb_result = migrate_kb(db, kb.id, domain_id)
        summary["kbs"].append({"kb_id": kb.id, **kb_result})

    from models import TableMeta

    for table in db.execute(select(TableMeta)).scalars().all():
        # Attach to first linked KB if any
        from models import TableKnowledgeBase

        link = db.execute(
            select(TableKnowledgeBase.knowledge_base_id).where(TableKnowledgeBase.table_id == table.id)
        ).first()
        if link:
            sync_physical_table_to_ontology(db, table.id, int(link[0]))
            summary["tables"] += 1

    summary["store"] = graph_stats()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate DataLens semantic data to RDF")
    parser.add_argument("--kb-id", type=int, help="Migrate single knowledge base")
    parser.add_argument("--domain-id", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        if args.kb_id:
            init_ontology()
            result = migrate_kb(db, args.kb_id, args.domain_id)
            print(result)
        else:
            result = migrate_all(db)
            print(result)


if __name__ == "__main__":
    main()
