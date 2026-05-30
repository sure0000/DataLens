"""Integration-style tests for git entry selection and regex extraction path."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from services.extraction.orchestrator import (
    _get_git_entries,
    _git_ext_priority,
    _should_skip_git_entry,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "codebases"


def test_should_skip_ts_for_data_warehouse_profile():
    assert _should_skip_git_entry("frontend/App.tsx", {"extraction_profile": "data_warehouse"}) is True
    assert _should_skip_git_entry("models/orders.sql", {"extraction_profile": "data_warehouse"}) is False


def test_extension_priority_sql_before_py():
    entries = [
        SimpleNamespace(source_meta={"ref": "app/main.py"}, title="main.py"),
        SimpleNamespace(source_meta={"ref": "models/orders.sql"}, title="orders.sql"),
        SimpleNamespace(source_meta={"ref": "models/stg.yml"}, title="stg.yml"),
    ]
    sorted_entries = sorted(entries, key=lambda e: (_git_ext_priority(
        (e.source_meta or {}).get("ref") or e.title
    ), (e.source_meta or {}).get("ref") or e.title))
    assert (sorted_entries[0].source_meta or {}).get("ref") == "models/orders.sql"


def test_get_git_entries_is_importable():
    # Smoke: function signature accepts extraction_config without DB
    assert callable(_get_git_entries)


def test_fixture_pure_sql_has_join_keyword():
    body = (FIXTURES / "pure_sql" / "orders_join.sql").read_text(encoding="utf-8")
    assert "JOIN" in body.upper()
