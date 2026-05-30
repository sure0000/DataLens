"""Pipeline run status helpers — human-readable failure reasons."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import get_settings
from models import PipelineRun

REASON_LABELS: dict[str, str] = {
    "no_eligible_chunks": "没有可抽取的文档分块（文档需完成索引且分块质量分≥0.4）",
    "no_git_entries": "该 Git 源暂无已同步文件，请先在源详情页执行「同步仓库」",
    "no_document_chunks": "无可抽取的正文内容（文档分块或 Git 文件正文为空/过短）",
    "no_llm_available": "未配置可用的大模型，请在设置中填写 API Key",
    "no_analyzed_tables": "导入库中的表尚未完成 AI 分析，请先在数据源中分析表",
    "no_tables_found": "未找到数据源中的表，请确认导入的数据库名称正确",
    "database_import_not_found": "数据库导入记录不存在",
    "partial_step_failures": "部分抽取步骤失败",
    "pipeline_timeout": "抽取超时（整体执行时间超过上限）",
    "pipeline_stale": "流水线运行超时（长时间无进展，已自动中止）",
    "stale_run": "步骤未执行（流水线被提前中止）",
    "server_restart": "服务重启导致流水线中断",
    "timeout": "抽取超时（超过 10 分钟）",
    "unexpected_error": "流水线异常终止",
    "already_running": "已有正在运行的抽取任务",
    "shacl_blocked": "入图被 SHACL 校验拦截，请查看建模与质量页",
    "no_triples_written": "入图未写入任何三元组",
    "no_triples": (
        "抽取已完成但未产生可入图三元组。请确认仓库含表间依赖或 JOIN 类逻辑"
        "（SQL/dbt/Python/Spark 等），且单文件正文≥50 字符；可在流水线步骤中查看 _git_diagnostics"
    ),
    "unknown": "未知错误",
    "failed": "抽取流水线失败",
    "json_query_error": "导入源筛选条件解析失败（JSON 字段查询异常），请重试或联系管理员",
}

_GENERIC_STATUS_TOKENS = frozenset({"failed", "skipped", "completed", "running", "pending", "timeout"})
_GENERIC_PIPELINE_MESSAGES = frozenset({
    "failed",
    "抽取流水线失败",
    "抽取失败，详见服务端日志",
    "unknown",
})

STEP_LABELS: dict[str, str] = {
    "term_extraction": "术语",
    "metric_caliber": "指标",
    "dimension_extraction": "维度",
    "rule_extraction": "规则",
    "relation_extraction": "关系",
    "hierarchy_building": "层级",
    "data_lineage": "血缘",
    "join_extraction": "JOIN",
    "domain_term_extraction": "领域术语",
    "ontology_write": "入图",
    "physical_schema": "物理 Schema",
}


def humanize_reason(code: str | None) -> str:
    if not code:
        return REASON_LABELS["unknown"]
    normalized = str(code).strip()
    if not normalized:
        return REASON_LABELS["unknown"]
    if normalized.lower() in _GENERIC_STATUS_TOKENS:
        return REASON_LABELS.get(normalized.lower(), REASON_LABELS["unexpected_error"])
    text = REASON_LABELS.get(normalized)
    if text:
        if normalized == "pipeline_stale":
            minutes = max(1, get_settings().pipeline_run_timeout_seconds // 60)
            return f"流水线长时间无进展（超过 {minutes} 分钟未更新进度，已自动中止）"
        return text
    lower = normalized.lower()
    if "astext" in lower and ("binaryexpression" in lower or "comparator" in lower):
        return REASON_LABELS["json_query_error"]
    if len(normalized) > 120:
        return normalized[:117] + "..."
    return normalized


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def pipeline_run_elapsed_seconds(run: PipelineRun) -> float | None:
    if not run.started_at:
        return None
    return (_utc_now() - _coerce_utc(run.started_at)).total_seconds()


def progress_at_from_steps(steps: dict[str, Any] | None) -> datetime | None:
    if not isinstance(steps, dict):
        return None
    meta = steps.get("_pipeline")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("progress_at")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return _coerce_utc(raw)
    try:
        text = str(raw).replace("Z", "+00:00")
        return _coerce_utc(datetime.fromisoformat(text))
    except (TypeError, ValueError):
        return None


def touch_pipeline_progress(steps: dict[str, Any], *, status: str = "running") -> dict[str, Any]:
    """Record a heartbeat on the in-flight pipeline (used for stale detection)."""
    meta = steps.get("_pipeline")
    if not isinstance(meta, dict):
        meta = {}
    merged = {
        **meta,
        "status": status,
        "progress_at": _utc_now().isoformat(),
    }
    return {**steps, "_pipeline": merged}


def pipeline_stale_threshold_seconds() -> int:
    """Idle time without progress_at update before a run is considered stuck."""
    return get_settings().pipeline_run_timeout_seconds


def pipeline_execution_timeout_seconds() -> int:
    """Hard cap for asyncio.wait_for — generous enough for all extraction steps."""
    stale = pipeline_stale_threshold_seconds()
    return max(stale * 3, 1800)


def pipeline_run_idle_seconds(run: PipelineRun) -> float | None:
    """Seconds since last recorded progress; falls back to total run time."""
    steps = run.steps if isinstance(run.steps, dict) else {}
    progress_at = progress_at_from_steps(steps)
    if progress_at is not None:
        return (_utc_now() - progress_at).total_seconds()
    return pipeline_run_elapsed_seconds(run)


def is_pipeline_run_stale(run: PipelineRun) -> bool:
    idle = pipeline_run_idle_seconds(run)
    if idle is None:
        return False
    steps = run.steps if isinstance(run.steps, dict) else {}
    if progress_at_from_steps(steps) is None:
        # No heartbeat yet: only fail after the full execution budget (first LLM step can be slow).
        return idle > pipeline_execution_timeout_seconds()
    return idle > pipeline_stale_threshold_seconds()


def pipeline_active_step(steps: dict[str, Any] | None) -> str | None:
    """Return the step key that was running when the pipeline stalled or timed out."""
    if not isinstance(steps, dict):
        return None
    meta = steps.get("_pipeline")
    if isinstance(meta, dict):
        active = meta.get("active_step")
        if active:
            return str(active)
    for key, val in steps.items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        if val.get("status") == "running":
            return key
    return None


def fail_stale_pipeline_run(run: PipelineRun) -> None:
    """Mark a stuck running pipeline as failed without labeling every pending step as timeout."""
    steps: dict[str, Any] = dict(run.steps) if isinstance(run.steps, dict) else {}
    active = pipeline_active_step(steps)
    stale_message = humanize_reason("pipeline_stale")
    if active:
        stale_message = f"{stale_message}（停留在步骤：{step_label(active)}）"
    steps["_pipeline"] = {
        "status": "failed",
        "reason": "pipeline_stale",
        "message": stale_message,
        "active_step": active,
    }
    for key, val in list(steps.items()):
        if key.startswith("_"):
            continue
        if isinstance(val, dict):
            if val.get("status") in (None, "pending", "running"):
                reason = "pipeline_stale" if key == active else (val.get("reason") or "stale_run")
                steps[key] = {**val, "status": "failed", "reason": reason}
        else:
            steps[key] = {"status": "failed", "reason": "stale_run"}
    run.steps = steps
    run.status = "failed"
    run.completed_at = datetime.now(timezone.utc)


def step_label(step_key: str) -> str:
    return STEP_LABELS.get(step_key, step_key)


def pipeline_failure_reason(run: PipelineRun | None) -> str | None:
    """Return a user-facing failure/skip reason for a pipeline run."""
    if run is None or run.status not in ("failed",):
        return None

    steps: dict[str, Any] = run.steps if isinstance(run.steps, dict) else {}

    failed: list[str] = []
    for key, val in steps.items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        if val.get("status") != "failed":
            continue
        step_message = val.get("message")
        if isinstance(step_message, str) and step_message.strip():
            msg = step_message.strip()
            if msg not in _GENERIC_PIPELINE_MESSAGES:
                failed.append(f"{step_label(key)}：{msg}" if key in STEP_LABELS else msg)
                continue
        reason = val.get("reason")
        if reason:
            detail = humanize_reason(str(reason))
            if detail and detail not in _GENERIC_PIPELINE_MESSAGES:
                failed.append(f"{step_label(key)}：{detail}" if key in STEP_LABELS else detail)

    if failed:
        return "；".join(failed[:3])

    pipeline_meta = steps.get("_pipeline")
    if isinstance(pipeline_meta, dict):
        message = pipeline_meta.get("message")
        reason = pipeline_meta.get("reason")
        if message:
            msg = str(message).strip()
            if msg not in _GENERIC_PIPELINE_MESSAGES and msg.lower() not in _GENERIC_STATUS_TOKENS:
                return msg
        if reason:
            return humanize_reason(str(reason))

    return "抽取失败，详见服务端日志"


def source_cleaning_stat_key(source_type: str | None, source_id: int | None) -> str | None:
    """Normalize PipelineRun source to frontend cleaning key (source:{kind}:{id})."""
    if source_type is None or source_id is None:
        return None
    st = str(source_type).strip()
    if not st:
        return None
    bare = st.removeprefix("source:")
    if bare == "api_entry":
        bare = "api"
    if bare in ("git", "api", "database", "file", "manual"):
        return f"source:{bare}:{source_id}"
    if st.startswith("source:"):
        return f"{st}:{source_id}"
    return None
