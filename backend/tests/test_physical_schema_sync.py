"""Physical schema sync → attribute layer visibility."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.ontology import modeling_layers as ml


@pytest.fixture
def memory_store(monkeypatch):
    import os

    from config import get_settings
    from services import ontology_store as osmod

    monkeypatch.setenv("FUSEKI_FALLBACK_MEMORY", "true")
    monkeypatch.delenv("FUSEKI_URL", raising=False)
    get_settings.cache_clear()
    osmod.reset_triple_store()
    yield
    osmod.reset_triple_store()
    get_settings.cache_clear()


def test_sync_physical_table_writes_attribute_layer(memory_store, monkeypatch):
    from models import ColumnMeta, TableMeta, TableSummary
    from services.ontology_population import sync_physical_table_to_ontology

    table = MagicMock(spec=TableMeta)
    table.id = 42
    table.table_name = "orders"
    table.database_name = "power"
    table.datasource_id = 3
    table.row_count = 1000

    col = MagicMock(spec=ColumnMeta)
    col.column_name = "user_id"
    col.data_type = "bigint"
    col.comment = "用户编号"
    col.semantic_desc = "订单所属用户"
    col.semantic_type = "id"

    summary = MagicMock(spec=TableSummary)
    summary.summary = "业务描述\n- 每行一条订单"

    db = MagicMock()
    db.get.return_value = table
    db.execute.return_value.scalars.return_value.all.side_effect = [
        [col],
    ]
    db.execute.return_value.scalars.return_value.first.return_value = summary

    monkeypatch.setattr(
        "services.ontology_population._purge_physical_table_subjects",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.ontology_validation.validate_ttl",
        lambda _ttl: {"conforms": True, "skipped": False},
    )

    out = sync_physical_table_to_ontology(db, 42, kb_id=501, datasource_id=3)
    assert out["written"] > 0
    assert out["literal_count"] > 0
    assert out["shacl_blocked"] is False

    counts = ml._count_queries(501)
    assert counts["attribute"] > 0
    items = ml._fetch_layer_items(501, "attribute")
    assert any("businessSummary" in (row.get("p") or "") for row in items)
    assert any(row.get("subjectLabel") == "orders" for row in items)
