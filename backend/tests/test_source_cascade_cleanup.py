"""Tests for import-source cascade cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.source_cascade_cleanup import _pipeline_binding_for_entry


def test_pipeline_binding_for_manual_entry():
    entry = MagicMock()
    entry.id = 42
    entry.source_meta = {"kind": "manual"}
    assert _pipeline_binding_for_entry(entry) == ("source:manual", 42)


def test_pipeline_binding_for_file_entry():
    entry = MagicMock()
    entry.id = 12
    entry.source_meta = {"kind": "file"}
    assert _pipeline_binding_for_entry(entry) == ("source:file", 12)


def test_pipeline_binding_for_api_entry():
    entry = MagicMock()
    entry.id = 7
    entry.source_meta = {"kind": "notion_api", "api_source_id": 99}
    assert _pipeline_binding_for_entry(entry) == ("source:api", 99)
