"""Pipeline failure reason extraction tests."""

from types import SimpleNamespace

from services.extraction.pipeline_status import humanize_reason, pipeline_failure_reason


def test_humanize_no_eligible_chunks():
    assert "分块" in humanize_reason("no_eligible_chunks")


def test_pipeline_failure_reason_from_pipeline_meta():
    run = SimpleNamespace(
        status="failed",
        steps={"_pipeline": {"status": "skipped", "reason": "no_llm_available"}},
    )
    assert "大模型" in (pipeline_failure_reason(run) or "")


def test_pipeline_failure_reason_from_failed_step():
    run = SimpleNamespace(
        status="failed",
        steps={"term_extraction": {"status": "failed", "reason": "API rate limit"}},
    )
    reason = pipeline_failure_reason(run)
    assert reason is not None
    assert "术语" in reason
    assert "API rate limit" in reason


def test_fail_stale_pipeline_run_does_not_use_timeout_for_pending_steps():
    from datetime import datetime, timezone

    from models import PipelineRun
    from services.extraction.pipeline_status import fail_stale_pipeline_run, pipeline_failure_reason

    run = PipelineRun(
        knowledge_base_id=1,
        status="running",
        steps={
            "term_extraction": "pending",
            "metric_caliber": {"status": "done", "triples": 3},
        },
    )
    run.started_at = datetime.now(timezone.utc)
    fail_stale_pipeline_run(run)
    assert run.steps["term_extraction"]["reason"] == "stale_run"
    assert run.steps["_pipeline"]["reason"] == "pipeline_stale"
    reason = pipeline_failure_reason(run)
    assert reason is not None
    assert run.steps["term_extraction"]["reason"] != "timeout"
    assert "无进展" in reason or "未更新进度" in reason


def test_stale_uses_progress_at_not_total_runtime():
    from datetime import datetime, timedelta, timezone

    from models import PipelineRun
    from services.extraction.pipeline_status import is_pipeline_run_stale, touch_pipeline_progress

    run = PipelineRun(knowledge_base_id=1, status="running", steps={})
    run.started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    run.steps = touch_pipeline_progress({"term_extraction": {"status": "running"}})
    # Recent heartbeat despite old started_at → not stale
    assert is_pipeline_run_stale(run) is False

    old_progress = datetime.now(timezone.utc) - timedelta(minutes=20)
    run.steps = {
        **touch_pipeline_progress({}),
        "_pipeline": {
            "status": "running",
            "progress_at": old_progress.isoformat(),
        },
    }
    assert is_pipeline_run_stale(run) is True
