"""Git evidence package synthesis and cleaning-key linkage."""

from __future__ import annotations

from services.ingestion.evidence import (
    _git_processing_state,
    _git_sync_ok,
)


def test_git_sync_ok_accepts_success_and_ok():
    assert _git_sync_ok("success") is True
    assert _git_sync_ok("ok") is True
    assert _git_sync_ok("error") is False


def test_git_processing_state_after_successful_sync():
    assert _git_processing_state("success", None) == "normalized"
    assert _git_processing_state("success", "running") == "ready_for_extraction"
    assert _git_processing_state("success", "completed") == "ready_for_extraction"
    assert _git_processing_state("pending", None) == "registered"
