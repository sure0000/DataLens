"""统一导入日志服务：记录并查询所有来源的导入事件。"""

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from models import ImportLog


def start_import(
    db: Session,
    kb_id: int,
    source_type: str,
    *,
    source_id: int | None = None,
    source_name: str | None = None,
) -> ImportLog:
    """创建一条 status='running' 的导入日志，返回它供后续更新。"""
    log = ImportLog(
        knowledge_base_id=kb_id,
        source_type=source_type,
        source_id=source_id,
        source_name=source_name,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    db.flush()
    return log


def complete_import(
    db: Session,
    log: ImportLog,
    *,
    entries_created: int = 0,
    entries_updated: int = 0,
    entries_deleted: int = 0,
    error_message: str | None = None,
) -> ImportLog:
    """标记导入完成（成功或失败）。"""
    log.status = "failed" if error_message else "success"
    log.entries_created = entries_created
    log.entries_updated = entries_updated
    log.entries_deleted = entries_deleted
    log.error_message = error_message
    log.completed_at = datetime.utcnow()
    db.flush()
    return log


def recent_logs(db: Session, kb_id: int, limit: int = 20) -> list[ImportLog]:
    return list(
        db.execute(
            select(ImportLog)
            .where(ImportLog.knowledge_base_id == kb_id)
            .order_by(desc(ImportLog.started_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
