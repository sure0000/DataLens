"""Git sync should trigger per-source extraction with source:git binding."""

from __future__ import annotations

from unittest.mock import patch

from services.ingestion.events import _on_git_sync_completed


def test_git_sync_completed_triggers_source_scoped_extraction():
    with patch("services.extraction.orchestrator.trigger_extraction_pipeline_background") as trigger:
        _on_git_sync_completed(kb_id=1, source_id=42, files=3)
        trigger.assert_called_once_with(1, source_type="source:git", source_id=42)


def test_git_sync_completed_skips_without_source_id():
    with patch("services.extraction.orchestrator.trigger_extraction_pipeline_background") as trigger:
        _on_git_sync_completed(kb_id=1, files=3)
        trigger.assert_not_called()
