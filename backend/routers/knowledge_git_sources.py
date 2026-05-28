"""知识库 GitHub / GitLab 代码源：配置、手动同步、定时任务注册。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import cast, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from database import get_db
from models import Document, KnowledgeBase, KnowledgeEntry, KnowledgeGitSource
from services.embedding_service import delete_embeddings_for_knowledge_entries
from services.git_knowledge_sync import run_git_source_sync
from services.git_schedule import refresh_git_sync_schedules

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-git-sources"])
_logger = logging.getLogger(__name__)


def _validate_cron(expr: str | None) -> None:
    if not expr or not str(expr).strip():
        return
    try:
        CronTrigger.from_crontab(str(expr).strip())
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cron 表达式无效（需 5 段：分 时 日 月 周）：{exc}") from exc


def _mask_row(r: KnowledgeGitSource) -> dict:
    return {
        "id": r.id,
        "knowledge_base_id": r.knowledge_base_id,
        "name": r.name,
        "provider": r.provider,
        "api_base": (r.api_base or "").strip() or None,
        "owner": r.owner,
        "repo": r.repo,
        "branch": r.branch or "",
        "uses_default_branch": not (r.branch or "").strip(),
        "path_prefix": r.path_prefix or "",
        "has_token": bool((r.token or "").strip()),
        "token": "",  # 列表接口永远不返回原始 token，仅通过 has_token 标识是否已配置
        "include_globs": r.include_globs,
        "max_file_kb": r.max_file_kb,
        "max_files": r.max_files,
        "cron_expression": (r.cron_expression or "").strip() or None,
        "enabled": bool(r.enabled),
        "tags": r.tags if isinstance(r.tags, list) else [],
        "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
        "last_sync_status": r.last_sync_status,
        "last_error": r.last_error,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
    }


class GitSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(..., description="github | gitlab")
    api_base: str | None = Field(default=None, max_length=500)
    owner: str = Field(min_length=1, max_length=500)
    repo: str = Field(min_length=1, max_length=500)
    branch: str = Field(
        default="",
        max_length=500,
        description="留空则每次同步使用仓库默认分支；填写则固定该分支",
    )
    path_prefix: str = Field(default="", max_length=500)
    token: str = Field(min_length=1, max_length=4000)
    include_globs: str = Field(
        default="*.md,*.sql,*.py,*.ts,*.tsx,*.java,*.go,*.rs,*.yml,*.yaml,*.json",
        max_length=2000,
    )
    max_file_kb: int = Field(default=512, ge=8, le=4096)
    max_files: int = Field(default=200, ge=1, le=5000)
    cron_expression: str | None = Field(default=None, max_length=120)
    enabled: bool = True
    tags: list[str] | None = None

    @field_validator("provider")
    @classmethod
    def _v_provider(cls, v: str) -> str:
        k = (v or "").strip().lower()
        if k not in {"github", "gitlab"}:
            raise ValueError("provider 仅支持 github、gitlab")
        return k


class GitSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = None
    api_base: str | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=500)
    repo: str | None = Field(default=None, min_length=1, max_length=500)
    branch: str | None = Field(default=None, max_length=500)
    path_prefix: str | None = Field(default=None, max_length=500)
    token: str | None = Field(default=None, max_length=4000)
    include_globs: str | None = Field(default=None, max_length=2000)
    max_file_kb: int | None = Field(default=None, ge=8, le=4096)
    max_files: int | None = Field(default=None, ge=1, le=5000)
    cron_expression: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    tags: list[str] | None = None

    @field_validator("provider")
    @classmethod
    def _v_provider(cls, v: str | None) -> str | None:
        if v is None:
            return None
        k = v.strip().lower()
        if k not in {"github", "gitlab"}:
            raise ValueError("provider 仅支持 github、gitlab")
        return k


def _get_kb(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@router.get("/git-sources")
def list_all_git_sources(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.execute(
            select(KnowledgeGitSource).order_by(KnowledgeGitSource.knowledge_base_id.asc(), KnowledgeGitSource.id.asc())
        )
        .scalars()
        .all()
    )
    return {"git_sources": [_mask_row(r) for r in rows]}


@router.get("/{kb_id}/git-sources")
def list_git_sources(kb_id: int, db: Session = Depends(get_db)) -> dict:
    _get_kb(db, kb_id)
    rows = (
        db.execute(
            select(KnowledgeGitSource)
            .where(KnowledgeGitSource.knowledge_base_id == kb_id)
            .order_by(KnowledgeGitSource.id.asc())
        )
        .scalars()
        .all()
    )
    return {"git_sources": [_mask_row(r) for r in rows]}


@router.post("/{kb_id}/git-sources")
def create_git_source(kb_id: int, body: GitSourceCreate, db: Session = Depends(get_db)) -> dict:
    _get_kb(db, kb_id)
    try:
        _validate_cron(body.cron_expression)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = KnowledgeGitSource(
        knowledge_base_id=kb_id,
        name=body.name.strip(),
        provider=body.provider,
        api_base=(body.api_base or "").strip() or None,
        owner=body.owner.strip(),
        repo=body.repo.strip(),
        branch=(body.branch or "").strip(),
        path_prefix=(body.path_prefix or "").strip(),
        token=body.token.strip(),
        include_globs=(body.include_globs or "").strip(),
        max_file_kb=body.max_file_kb,
        max_files=body.max_files,
        cron_expression=(body.cron_expression or "").strip() or None,
        enabled=body.enabled,
        tags=body.tags if isinstance(body.tags, list) else None,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        from services.ingestion.connectors import register_evidence_from_import

        register_evidence_from_import(
            db,
            kb_id,
            title=f"[Git] {row.name}",
            route_key="git-sources",
            source_ref={
                "git_source_id": row.id,
                "provider": row.provider,
                "owner": row.owner,
                "repo": row.repo,
                "branch": row.branch or "",
            },
            processing_state="registered",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        refresh_git_sync_schedules()
    except Exception:  # noqa: BLE001
        pass
    return {"git_source": _mask_row(row)}


@router.put("/{kb_id}/git-sources/{source_id}")
def update_git_source(
    kb_id: int, source_id: int, body: GitSourceUpdate, db: Session = Depends(get_db)
) -> dict:
    _get_kb(db, kb_id)
    row = db.get(KnowledgeGitSource, source_id)
    if not row or row.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Git 源不存在")

    if body.cron_expression is not None:
        try:
            _validate_cron(body.cron_expression)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.name is not None:
        row.name = body.name.strip()
    if body.provider is not None:
        row.provider = body.provider
    if body.api_base is not None:
        row.api_base = (body.api_base or "").strip() or None
    if body.owner is not None:
        row.owner = body.owner.strip()
    if body.repo is not None:
        row.repo = body.repo.strip()
    if body.branch is not None:
        row.branch = (body.branch or "").strip()
    if body.path_prefix is not None:
        row.path_prefix = (body.path_prefix or "").strip()
    if body.token is not None and str(body.token).strip():
        row.token = str(body.token).strip()
    if body.include_globs is not None:
        row.include_globs = (body.include_globs or "").strip()
    if body.max_file_kb is not None:
        row.max_file_kb = body.max_file_kb
    if body.max_files is not None:
        row.max_files = body.max_files
    if body.cron_expression is not None:
        row.cron_expression = (body.cron_expression or "").strip() or None
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.tags is not None:
        row.tags = body.tags if isinstance(body.tags, list) else None
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    try:
        refresh_git_sync_schedules()
    except Exception:  # noqa: BLE001
        pass
    return {"git_source": _mask_row(row)}


@router.delete("/{kb_id}/git-sources/{source_id}")
def delete_git_source(kb_id: int, source_id: int, db: Session = Depends(get_db)) -> dict:
    _get_kb(db, kb_id)
    row = db.get(KnowledgeGitSource, source_id)
    if not row or row.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Git 源不存在")
    entry_ids = list(
        db.scalars(
            select(KnowledgeEntry.id).where(
                KnowledgeEntry.knowledge_base_id == kb_id,
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
                cast(KnowledgeEntry.source_meta, JSONB)["git_source_id"].astext == str(source_id),
            )
        ).all()
    )
    delete_embeddings_for_knowledge_entries(db, entry_ids)
    if entry_ids:
        db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids)))
        db.flush()
    db.delete(row)
    db.commit()
    try:
        refresh_git_sync_schedules()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


def _entries_for_git_source(db: Session, kb_id: int, source_id: int) -> list[KnowledgeEntry]:
    return list(
        db.scalars(
            select(KnowledgeEntry).where(
                KnowledgeEntry.knowledge_base_id == kb_id,
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
                cast(KnowledgeEntry.source_meta, JSONB)["git_source_id"].astext == str(source_id),
            )
        ).all()
    )


def _document_meta_for_git_entry(src: KnowledgeGitSource, entry: KnowledgeEntry) -> dict[str, Any]:
    meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
    ref = str(meta.get("ref") or "").strip()
    label = str(meta.get("label") or "").strip() or f"{src.owner}/{src.repo}"
    return {
        "kind": "git_file",
        "git_source_id": str(src.id),
        "ref": ref,
        "label": label,
    }


def _spawn_git_document_pipelines(
    kb_id: int,
    src: KnowledgeGitSource,
    items: list[dict[str, Any]],
) -> None:
    if not items:
        return

    def _bg() -> None:
        from database import SessionLocal
        from services.knowledge_pipeline_service import create_document, run_pipeline

        bg_db = SessionLocal()
        try:
            for item in items:
                entry = bg_db.get(KnowledgeEntry, item["entry_id"])
                if not entry:
                    continue
                doc = create_document(
                    bg_db,
                    kb_id,
                    item["title"],
                    source_type="git",
                    source_meta=_document_meta_for_git_entry(src, entry),
                    knowledge_entry_id=item["entry_id"],
                )
                bg_db.commit()
                bg_doc = bg_db.get(Document, doc.id)
                if bg_doc:
                    run_pipeline(bg_db, bg_doc, item["text"])
        except Exception:
            _logger.exception("Background git reindex pipeline failed for kb=%d source=%d", kb_id, src.id)
        finally:
            bg_db.close()

    threading.Thread(target=_bg, daemon=True).start()


@router.post("/{kb_id}/git-sources/{source_id}/reindex-entries")
def reindex_git_source_entries(kb_id: int, source_id: int, db: Session = Depends(get_db)) -> dict:
    """为已同步但缺少 Document/分块的 Git 文件条目重建文档索引（不重新拉取仓库）。"""
    _get_kb(db, kb_id)
    src = db.get(KnowledgeGitSource, source_id)
    if not src or src.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Git 源不存在")

    entries = _entries_for_git_source(db, kb_id, source_id)
    if not entries:
        raise HTTPException(status_code=404, detail="未找到与该 Git 源关联的知识条目")

    items: list[dict[str, Any]] = []
    skipped = 0
    for entry in entries:
        body = (entry.body or "").strip()
        if not body:
            skipped += 1
            continue
        existing = db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id == entry.id,
                Document.status.in_(("pending", "extracting", "cleaning", "chunking", "embedding", "ontology_assertion", "indexed")),
            )
        ).scalars().first()
        if existing:
            skipped += 1
            continue
        items.append({"entry_id": entry.id, "title": entry.title or "Git 文件", "text": body})

    if not items:
        return {
            "ok": True,
            "queued": 0,
            "skipped": skipped,
            "message": "关联条目均已存在进行中的文档，或正文为空",
        }

    _spawn_git_document_pipelines(kb_id, src, items)
    return {"ok": True, "queued": len(items), "skipped": skipped}


@router.post("/{kb_id}/git-sources/{source_id}/sync")
def sync_git_source_now(kb_id: int, source_id: int, db: Session = Depends(get_db)) -> dict:
    _get_kb(db, kb_id)
    row = db.get(KnowledgeGitSource, source_id)
    if not row or row.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Git 源不存在")
    if not row.enabled:
        raise HTTPException(status_code=400, detail="该 Git 源已禁用，请先启用再同步")
    if not (row.token or "").strip():
        raise HTTPException(status_code=400, detail="缺少访问令牌，请编辑并保存 token")
    out = run_git_source_sync(db, source_id)
    if not out.get("ok"):
        raw = out.get("error")
        detail = (str(raw).strip() if raw is not None else "") or "同步失败（服务端未返回具体原因）"
        raise HTTPException(status_code=502, detail=detail)
    return out


@router.post("/{kb_id}/analyze-codebase")
def analyze_codebase(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """触发代码库分析：扫描知识库中所有 git 同步条目，提取表引用并关联。"""
    import asyncio
    import threading
    import logging

    _get_kb(db, kb_id)

    # 检查是否有 git 条目
    has_entries = db.execute(
        select(KnowledgeEntry.id).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
        ).limit(1)
    ).scalars().first()
    if not has_entries:
        return {"ok": True, "total": 0, "analyzed": 0, "message": "该知识库没有 git 同步条目"}

    result_holder: dict = {}

    def _run():
        _log = logging.getLogger(__name__)
        from database import SessionLocal
        db2 = SessionLocal()
        try:
            from services.codebase_analyzer import run_codebase_analysis_for_kb
            r = asyncio.run(run_codebase_analysis_for_kb(db2, kb_id))
            result_holder.update(r)
        except Exception as exc:
            _log.exception("代码库分析后台任务失败 kb=%d", kb_id)
            result_holder["ok"] = False
            result_holder["error"] = str(exc)
        finally:
            db2.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=3.0)
    if t.is_alive():
        return {"ok": True, "processing": True, "message": "代码库分析正在后台运行，完成后会自动关联表引用"}
    return result_holder
