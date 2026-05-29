"""DataSource deletion cascade cleanup."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from database import SessionLocal
from models import BusinessDomain, BusinessDomainSelection, DataSource, KnowledgeBase, KnowledgeDatabaseImport
from services.datasource_cleanup import delete_datasource_row


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_delete_datasource_clears_foreign_key_refs(db) -> None:
    domain = db.execute(select(BusinessDomain).limit(1)).scalars().first()
    if not domain:
        pytest.skip("no business domain in database")

    row = DataSource(
        name="__pytest_delete_ds__",
        source_type="mysql",
        host="127.0.0.1",
        port=3306,
        database="pytest_db",
        username="root",
        password="secret",
        business_domain_id=domain.id,
    )
    db.add(row)
    db.flush()

    db.add(
        BusinessDomainSelection(
            domain_id=domain.id,
            datasource_id=row.id,
            database_name="pytest_db",
            table_name="orders",
        )
    )

    kb = db.execute(select(KnowledgeBase).limit(1)).scalars().first()
    if kb:
        db.add(
            KnowledgeDatabaseImport(
                knowledge_base_id=kb.id,
                datasource_id=row.id,
                datasource_name=row.name,
                database_names=["pytest_db"],
            )
        )
    db.flush()

    result = delete_datasource_row(db, row)
    assert result["success"] is True
    assert result["domain_selections"] >= 1 or result["database_imports"] >= 1
    db.flush()
    assert db.get(DataSource, row.id) is None

    remaining_imports = db.execute(
        select(KnowledgeDatabaseImport).where(KnowledgeDatabaseImport.datasource_id == row.id)
    ).scalars().all()
    remaining_selections = db.execute(
        select(BusinessDomainSelection).where(BusinessDomainSelection.datasource_id == row.id)
    ).scalars().all()
    assert remaining_imports == []
    assert remaining_selections == []
