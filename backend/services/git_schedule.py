"""按 cron 表达式调度知识库 Git 源同步（APScheduler）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from database import SessionLocal
from models import KnowledgeGitSource

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="UTC")


def _run_sync_job(source_id: int) -> None:
    db = SessionLocal()
    try:
        from services.git_knowledge_sync import run_git_source_sync

        run_git_source_sync(db, source_id)
    except Exception:  # noqa: BLE001
        logger.exception("定时 Git 同步失败 source_id=%s", source_id)
    finally:
        db.close()


def refresh_git_sync_schedules() -> None:
    """根据数据库中的 enabled + cron_expression 重建全部定时任务。"""
    if not _scheduler.running:
        return
    for j in list(_scheduler.get_jobs()):
        jid = getattr(j, "id", None) or ""
        if isinstance(jid, str) and jid.startswith("git_sync_"):
            try:
                _scheduler.remove_job(jid)
            except JobLookupError:
                pass

    db = SessionLocal()
    try:
        rows = db.scalars(select(KnowledgeGitSource).where(KnowledgeGitSource.enabled.is_(True))).all()
        for r in rows:
            cron = (r.cron_expression or "").strip()
            if not cron:
                continue
            try:
                trigger = CronTrigger.from_crontab(cron)
            except Exception as exc:  # noqa: BLE001
                logger.warning("跳过无效 cron source_id=%s expr=%r: %s", r.id, cron, exc)
                continue
            job_id = f"git_sync_{r.id}"
            _scheduler.add_job(
                _run_sync_job,
                trigger,
                id=job_id,
                args=[r.id],
                replace_existing=True,
            )
    finally:
        db.close()


def start_git_sync_scheduler() -> None:
    if not _scheduler.running:
        _scheduler.start()
    refresh_git_sync_schedules()


def stop_git_sync_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
