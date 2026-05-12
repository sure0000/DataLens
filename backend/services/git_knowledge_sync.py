"""从 GitHub / GitLab 拉取仓库文本文件，写入知识库条目（kind=git_file）。"""

from __future__ import annotations

import base64
import fnmatch
import logging
import re
import threading
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import cast, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from models import KnowledgeEntry, KnowledgeGitSource
from services.embedding_service import (
    delete_embeddings_for_knowledge_entries,
    replace_knowledge_entry_embedding,
)

_HTTP_TIMEOUT = 120.0


_logger = logging.getLogger(__name__)


def _trigger_codebase_analysis(knowledge_base_id: int) -> None:
    """在后台线程中触发代码库分析（不阻塞同步响应）。"""
    import asyncio

    def _run():
        from database import SessionLocal

        db2 = SessionLocal()
        try:
            from services.codebase_analyzer import run_codebase_analysis_for_kb

            asyncio.run(run_codebase_analysis_for_kb(db2, knowledge_base_id))
        except Exception:
            _logger.warning("Codebase analysis failed after git sync for kb=%s", knowledge_base_id, exc_info=True)
        finally:
            db2.close()

    t = threading.Thread(target=_run, daemon=True, name=f"codebase-analysis-kb-{knowledge_base_id}")
    t.start()


def _format_sync_exception(exc: BaseException) -> str:
    """把同步过程中的异常整理成用户可读的具体原因（含远端 API 返回的 message）。"""
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        req = resp.request
        url = str(req.url) if req else ""
        code = resp.status_code
        head = f"HTTP {code}"
        if url and len(url) <= 220:
            head = f"{head} · {url}"
        elif url:
            head = f"{head} · {url[:200]}…"
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            api_msg = data.get("message")
            if isinstance(api_msg, str) and api_msg.strip():
                extra = api_msg.strip()
                if isinstance(data.get("errors"), list) and data["errors"]:
                    extra = f"{extra} · {data['errors']!s}"[:1200]
                return f"{head}：{extra}"[:2000]
            err = data.get("error") or data.get("error_description")
            if isinstance(err, str) and err.strip():
                return f"{head}：{err.strip()}"[:2000]
        body = (resp.text or "").strip()
        if body:
            return f"{head}：{body[:1200]}"[:2000]
        return f"{head}（响应体为空）"
    if isinstance(exc, httpx.RequestError):
        return f"网络请求失败：{exc!s}"[:2000]
    return (str(exc) or type(exc).__name__)[:2000]


def _plain_excerpt(body: str, max_len: int = 420) -> str:
    s = (body or "").strip()
    if not s:
        return ""
    s = re.sub(r"[\n\r\t]+", " ", s)
    s = re.sub(r" +", " ", s).strip()
    if len(s) <= max_len:
        return s
    return f"{s[: max_len - 1].rstrip()}…"


def _parse_globs(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p.strip()]


def _path_matches_globs(rel_path: str, globs: list[str]) -> bool:
    if not globs:
        return True
    basename = rel_path.split("/")[-1]
    return any(fnmatch.fnmatch(rel_path, g) or fnmatch.fnmatch(basename, g) for g in globs)


def _github_headers(token: str) -> dict[str, str]:
    """GitHub 要求合法 User-Agent；PAT 使用 Bearer（classic / fine-grained 均支持）。"""
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token.strip()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DataLens-KnowledgeSync/1.0",
    }


def _github_json(resp: httpx.Response, ctx: str) -> Any:
    """解析 GitHub JSON 响应；若非 JSON（代理/HTML/登录页）给出可读错误。"""
    ct = (resp.headers.get("content-type") or "").lower()
    raw = (resp.text or "")[:800]
    if "json" not in ct and raw.lstrip().startswith("<"):
        raise ValueError(f"{ctx}：GitHub 返回 HTML 而非 JSON（请检查 api_base 是否指向 GitHub REST，或是否被代理拦截）。正文开头: {raw[:280]}")
    try:
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{ctx}：无法解析 JSON（Content-Type: {ct or '无'}）。正文开头: {raw[:280]}") from exc


def _gitlab_headers(token: str) -> dict[str, str]:
    return {"PRIVATE-TOKEN": token.strip()}


def _github_repo_meta(client: httpx.Client, api_base: str, owner: str, repo: str, token: str) -> dict[str, Any]:
    base = (api_base or "https://api.github.com").rstrip("/")
    meta = client.get(f"{base}/repos/{owner}/{repo}", headers=_github_headers(token))
    meta.raise_for_status()
    data = _github_json(meta, f"读取仓库 {owner}/{repo} 元数据")
    if not isinstance(data, dict):
        raise ValueError(f"GitHub 仓库元数据返回非 JSON 对象: {type(data).__name__}")
    return data


def _github_resolve_branch_sha(
    client: httpx.Client, api_base: str, owner: str, repo: str, branch: str, token: str
) -> tuple[str, str]:
    """返回 (commit_sha, 实际使用的分支名)。branch 为空时使用仓库 default_branch。"""
    base = (api_base or "https://api.github.com").rstrip("/")
    br = (branch or "").strip()
    if not br:
        meta = _github_repo_meta(client, api_base, owner, repo, token)
        br = str(meta.get("default_branch") or "main")

    r = client.get(f"{base}/repos/{owner}/{repo}/branches/{quote(br, safe='')}", headers=_github_headers(token))
    if r.status_code == 404:
        meta = _github_repo_meta(client, api_base, owner, repo, token)
        default_b = str(meta.get("default_branch") or "main")
        r = client.get(
            f"{base}/repos/{owner}/{repo}/branches/{quote(default_b, safe='')}",
            headers=_github_headers(token),
        )
    r.raise_for_status()
    data = _github_json(r, f"读取分支 {br} 信息")
    if not isinstance(data, dict):
        raise ValueError(f"GitHub 分支接口返回非对象: {type(data).__name__}")
    sha = (data.get("commit") or {}).get("sha")
    if not sha:
        raise ValueError("GitHub 分支响应缺少 commit sha")
    used_branch = str(data.get("name") or br)
    return str(sha), used_branch


def _github_list_blobs(
    client: httpx.Client,
    api_base: str,
    owner: str,
    repo: str,
    commit_sha: str,
    token: str,
    path_prefix: str,
    globs: list[str],
    max_file_bytes: int,
    max_files: int,
) -> list[tuple[str, str]]:
    base = (api_base or "https://api.github.com").rstrip("/")
    c = client.get(f"{base}/repos/{owner}/{repo}/git/commits/{commit_sha}", headers=_github_headers(token))
    c.raise_for_status()
    cj = _github_json(c, "读取 commit")
    tree_sha = (cj.get("tree") or {}).get("sha") if isinstance(cj, dict) else None
    if not tree_sha:
        raise ValueError("GitHub commit 缺少 tree sha")

    t = client.get(
        f"{base}/repos/{owner}/{repo}/git/trees/{tree_sha}",
        params={"recursive": "1"},
        headers=_github_headers(token),
    )
    t.raise_for_status()
    payload = _github_json(t, "读取目录树")
    if not isinstance(payload, dict):
        raise ValueError(f"GitHub tree 接口返回非对象: {type(payload).__name__}")
    if payload.get("truncated"):
        raise ValueError("GitHub 目录树过大已被截断，请缩小 path_prefix 或 include_globs")

    prefix = (path_prefix or "").strip().replace("\\", "/").lstrip("/")
    out: list[tuple[str, str]] = []
    for item in payload.get("tree") or []:
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        if prefix and not (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
            continue
        rel = path[len(prefix) :].lstrip("/") if prefix else path
        if not rel:
            rel = path.split("/")[-1]
        size = item.get("size")
        if isinstance(size, int) and size > max_file_bytes:
            continue
        if not _path_matches_globs(path, globs):
            continue
        blob_sha = item.get("sha")
        if not blob_sha:
            continue
        b = client.get(f"{base}/repos/{owner}/{repo}/git/blobs/{blob_sha}", headers=_github_headers(token))
        if b.status_code != 200:
            continue
        try:
            bj = b.json()
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(bj, dict):
            continue
        if bj.get("encoding") != "base64" or not bj.get("content"):
            continue
        raw = base64.b64decode(bj["content"].replace("\n", ""))
        if len(raw) > max_file_bytes:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text:
            continue
        out.append((path, text))
        if len(out) >= max_files:
            break
    return out


def _gitlab_project(client: httpx.Client, api_base: str, owner: str, repo: str, token: str) -> tuple[str, str]:
    base = (api_base or "https://gitlab.com/api/v4").rstrip("/")
    enc = quote(f"{owner}/{repo}", safe="")
    r = client.get(f"{base}/projects/{enc}", headers=_gitlab_headers(token))
    r.raise_for_status()
    j = r.json() or {}
    pid = j.get("id")
    if pid is None:
        raise ValueError("GitLab 项目响应异常")
    default_branch = str(j.get("default_branch") or "main")
    return str(pid), default_branch


def _gitlab_list_blobs(
    client: httpx.Client,
    api_base: str,
    project_id: str,
    branch: str,
    token: str,
    path_prefix: str,
    globs: list[str],
    max_file_bytes: int,
    max_files: int,
) -> list[tuple[str, str]]:
    base = (api_base or "https://gitlab.com/api/v4").rstrip("/")
    prefix = (path_prefix or "").strip().replace("\\", "/").lstrip("/")
    out: list[tuple[str, str]] = []
    page = 1
    per_page = 100

    while len(out) < max_files:
        r = client.get(
            f"{base}/projects/{quote(project_id, safe='')}/repository/tree",
            params={
                "ref": branch,
                "recursive": "true",
                "per_page": per_page,
                "page": page,
            },
            headers=_gitlab_headers(token),
        )
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            if item.get("type") != "blob":
                continue
            path = str(item.get("path") or "")
            if prefix and not (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
                continue
            if not _path_matches_globs(path, globs):
                continue
            enc_path = quote(path, safe="")
            raw_r = client.get(
                f"{base}/projects/{quote(project_id, safe='')}/repository/files/{enc_path}/raw",
                params={"ref": branch},
                headers=_gitlab_headers(token),
            )
            if raw_r.status_code != 200:
                continue
            raw = raw_r.content
            if len(raw) > max_file_bytes:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if "\x00" in text:
                continue
            out.append((path, text))
            if len(out) >= max_files:
                break
        if len(batch) < per_page:
            break
        page += 1
        if page > 200:
            raise ValueError("GitLab 仓库文件分页过多，请缩小 path_prefix 或 include_globs")
    return out


def _collect_files(src: KnowledgeGitSource) -> tuple[list[tuple[str, str]], str]:
    """返回 (文件列表, 本次实际使用的分支名)，用于来源链接与展示。"""
    globs = _parse_globs(src.include_globs or "")
    max_kb = max(1, int(src.max_file_kb or 512))
    max_bytes = max_kb * 1024
    max_files = max(1, min(int(src.max_files or 200), 5000))
    owner = (src.owner or "").strip().strip("/")
    repo = (src.repo or "").strip().strip("/")
    if not owner or not repo:
        raise ValueError("owner / repo 不能为空")

    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        if src.provider == "github":
            commit_sha, used_branch = _github_resolve_branch_sha(
                client, src.api_base or "", owner, repo, (src.branch or "").strip(), src.token
            )
            files = _github_list_blobs(
                client,
                src.api_base or "",
                owner,
                repo,
                commit_sha,
                src.token,
                src.path_prefix or "",
                globs,
                max_bytes,
                max_files,
            )
            return files, used_branch
        if src.provider == "gitlab":
            pid, default_branch = _gitlab_project(client, src.api_base or "", owner, repo, src.token)
            ref = (src.branch or "").strip() or default_branch
            files = _gitlab_list_blobs(
                client,
                src.api_base or "",
                pid,
                ref,
                src.token,
                src.path_prefix or "",
                globs,
                max_bytes,
                max_files,
            )
            return files, ref
    raise ValueError(f"不支持的 provider: {src.provider}")


def run_git_source_sync(db: Session, source_id: int) -> dict[str, Any]:
    """同步单个 Git 源：删除该源此前写入的条目，再写入当前文件列表。成功或失败都会更新 last_sync_*。"""
    src = db.get(KnowledgeGitSource, source_id)
    if not src:
        return {"ok": False, "error": "Git 源不存在"}

    kb_id = src.knowledge_base_id
    now = datetime.utcnow()

    try:
        files, resolved_branch = _collect_files(src)
    except Exception as exc:  # noqa: BLE001
        detail = _format_sync_exception(exc)
        src.last_sync_at = now
        src.last_sync_status = "error"
        src.last_error = detail
        src.updated_at = now
        db.commit()
        return {"ok": False, "error": detail, "files": 0}

    old_ids = list(
        db.scalars(
            select(KnowledgeEntry.id).where(
                KnowledgeEntry.knowledge_base_id == kb_id,
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
                cast(KnowledgeEntry.source_meta, JSONB)["git_source_id"].astext == str(source_id),
            )
        ).all()
    )
    delete_embeddings_for_knowledge_entries(db, old_ids)
    if old_ids:
        db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(old_ids)))
        db.flush()

    max_order = db.execute(
        select(KnowledgeEntry.sort_order)
        .where(KnowledgeEntry.knowledge_base_id == kb_id)
        .order_by(KnowledgeEntry.sort_order.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_order = (max_order or 0) + 1

    label = f"{'GitHub' if src.provider == 'github' else 'GitLab'} · {src.owner}/{src.repo}"
    base_url = ""
    br = resolved_branch
    if src.provider == "github":
        base_url = f"https://github.com/{src.owner}/{src.repo}/blob/{br}/"
    elif src.provider == "gitlab":
        root = (src.api_base or "https://gitlab.com").rstrip("/").replace("/api/v4", "")
        enc = quote(f"{src.owner}/{src.repo}", safe="")
        base_url = f"{root}/{enc}/-/blob/{br}/"

    created = 0
    try:
        for path, body in files:
            title = path.split("/")[-1] or path
            excerpt = _plain_excerpt(body)
            source_url = (base_url + quote(path, safe="/")) if base_url else None
            meta: dict[str, str] = {
                "kind": "git_file",
                "git_source_id": str(source_id),
                "ref": path,
                "label": label,
            }
            entry = KnowledgeEntry(
                knowledge_base_id=kb_id,
                title=title[:500],
                summary=excerpt,
                body=body,
                sort_order=next_order,
                source_url=source_url,
                source_meta=meta,
                updated_at=now,
            )
            db.add(entry)
            db.flush()
            replace_knowledge_entry_embedding(db, entry.id, entry.title, entry.body, entry.summary)
            next_order += 1
            created += 1

        src.last_sync_at = now
        src.last_sync_status = "success"
        src.last_error = None
        src.updated_at = now
        db.commit()
        if created == 0:
            msg = (
                "未发现可导入的文本文件：请检查 include_globs、path_prefix、分支与仓库内容，"
                "或放宽 glob / 提高 max_files / 确认默认分支上确有匹配后缀的源码或文档。"
            )
        else:
            msg = f"已同步 {created} 个文件为知识条目"
            _trigger_codebase_analysis(kb_id)
        return {"ok": True, "files": created, "message": msg}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        detail = _format_sync_exception(exc)
        src2 = db.get(KnowledgeGitSource, source_id)
        if src2:
            src2.last_sync_at = datetime.utcnow()
            src2.last_sync_status = "error"
            src2.last_error = detail
            src2.updated_at = datetime.utcnow()
            db.commit()
        return {"ok": False, "error": detail, "files": 0}

