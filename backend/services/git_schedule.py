"""按 cron 表达式调度知识库 Git / MCP 源同步（APScheduler）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from database import SessionLocal
from models import KnowledgeGitSource
from services.background import schedule_sync

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="UTC")


def _run_git_sync_job(source_id: int) -> None:
    schedule_sync(_run_git_sync_job_sync, source_id)


def _run_git_sync_job_sync(source_id: int) -> None:
    db = SessionLocal()
    try:
        from services.git_knowledge_sync import run_git_source_sync

        run_git_source_sync(db, source_id)
    except Exception:  # noqa: BLE001
        logger.exception("定时 Git 同步失败 source_id=%s", source_id)
    finally:
        db.close()


def _refresh_schedules_for_model(
    model: type, job_prefix: str, job_func: callable
) -> None:
    if not _scheduler.running:
        return
    for j in list(_scheduler.get_jobs()):
        jid = getattr(j, "id", None) or ""
        if isinstance(jid, str) and jid.startswith(job_prefix):
            try:
                _scheduler.remove_job(jid)
            except JobLookupError:
                pass

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(model).where(model.enabled.is_(True))
        ).all()
        for r in rows:
            cron = (r.cron_expression or "").strip()
            if not cron:
                continue
            try:
                trigger = CronTrigger.from_crontab(cron)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "跳过无效 cron source_id=%s expr=%r: %s", r.id, cron, exc
                )
                continue
            job_id = f"{job_prefix}{r.id}"
            _scheduler.add_job(
                job_func,
                trigger,
                id=job_id,
                args=[r.id],
                replace_existing=True,
            )
    finally:
        db.close()


def refresh_git_sync_schedules() -> None:
    _refresh_schedules_for_model(
        KnowledgeGitSource, "git_sync_", _run_git_sync_job
    )


def start_git_sync_scheduler() -> None:
    if not _scheduler.running:
        _scheduler.start()
    refresh_git_sync_schedules()


def stop_git_sync_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
