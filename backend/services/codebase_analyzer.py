"""从 Git 同步的代码文件中提取表引用、列枚举值、聚合方式，写入元数据。

设计原则：
- 预过滤（regex）减少 LLM 调用量
- LLM 分析结果持久化到 TableKnowledgeEntry / ColumnMeta.quality_metrics
- 一次分析，处处复用
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ColumnMeta, KnowledgeEntry, TableKnowledgeEntry, TableMeta
from prompts import load_prompt as _load_prompt

_logger = logging.getLogger(__name__)

# ── 预过滤器：快速判断文件是否可能包含数据表引用 ──────────────────────────

# 匹配 SQL 表引用模式
_RE_SQL_TABLE = re.compile(
    r"\b(FROM|JOIN|INTO|UPDATE|TABLE|INSERT\s+INTO|MERGE\s+INTO)\s+[`\"'\[\]]?(\w+)[`\"'\[\]]?",
    re.IGNORECASE,
)

# 匹配 ORM / Model 文件中的类名或表名引用
_RE_ORM_TABLE = re.compile(
    r"__(tablename__|table_args__)|class\s+\w+.*Base|db\.Table\(|\.table_name\s*=\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)

# 匹配 YAML/JSON 配置中的表名
_RE_CONFIG_TABLE = re.compile(
    r"(table|source_table|target_table|table_name|tablename)\s*:\s*['\"]?(\w+)['\"]?",
    re.IGNORECASE,
)

# 匹配 DBT / dataform 等数据工程工具的模型文件
_RE_DBT_MODEL = re.compile(
    r"(ref|source)\s*\(\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)

# 纯标记文件、证书、图片等（跳过分析）
_SKIP_EXTENSIONS = {
    ".lock", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".map", ".min.js", ".min.css", ".pdf", ".zip", ".tar",
    ".gz", ".whl", ".egg",
}

_MAX_INPUT_CHARS = 8000  # 发往 LLM 的最大字符数


def _should_skip_file(title: str, body: str) -> bool:
    """快速判断文件是否与数据表无关。"""
    lower_title = (title or "").lower()
    # 跳过二进制/资源文件
    for ext in _SKIP_EXTENSIONS:
        if lower_title.endswith(ext):
            return True
    # 跳过太短或太长的文件
    body_len = len(body or "")
    if body_len < 50 or body_len < 1:
        return True
    return False


def _likely_has_table_refs(body: str) -> bool:
    """预过滤：检查文件内容是否可能包含数据表引用。"""
    if _RE_SQL_TABLE.search(body):
        return True
    if _RE_ORM_TABLE.search(body):
        return True
    if _RE_CONFIG_TABLE.search(body):
        return True
    if _RE_DBT_MODEL.search(body):
        return True
    # 对 .sql / .py / .ts / .java / .go 等源文件放宽条件：
    # 只要提到了已知表名模式的词也视为候选
    return False


def _truncate_for_llm(body: str, max_chars: int = _MAX_INPUT_CHARS) -> str:
    """截断过长文件，保留开头和结尾各一半。"""
    b = (body or "").strip()
    if len(b) <= max_chars:
        return b
    half = max_chars // 2
    return b[:half] + "\n\n…（中间部分已省略）…\n\n" + b[-half:]


# ── LLM 分析 Prompt ──────────────────────────────────────────────────────

_CODE_ANALYSIS_SYSTEM = _load_prompt("code_analysis_system")


def _build_analysis_prompt(entry_title: str, body: str) -> str:
    return _load_prompt("code_analysis_user").format(
        entry_title=entry_title,
        truncated_body=_truncate_for_llm(body),
    )


# ── 主分析函数 ───────────────────────────────────────────────────────────

async def analyze_git_entry(
    entry: KnowledgeEntry,
    db: Session,
    *,
    semantic_model_ref: str,
    client_and_model: tuple[Any, str] | None = None,
) -> dict[str, Any]:
    """分析单条 git 知识条目，返回提取结果。如无 LLM 可用则仅做 regex 提取。"""
    title = (entry.title or "").strip()
    body = (entry.body or "").strip()

    if _should_skip_file(title, body):
        return {"table_references": [], "irrelevant": True, "skipped": True, "reason": "文件类型不支持分析"}

    if not _likely_has_table_refs(body):
        return {"table_references": [], "irrelevant": True, "skipped": True, "reason": "未检测到表引用模式"}

    if client_and_model is None:
        # 尝试获取 LLM 客户端
        try:
            from services.llm_models import has_any_llm_key, resolve_effective_model
            if not has_any_llm_key(db):
                return _regex_extract(title, body)
            model_ref = resolve_effective_model(semantic_model_ref, db)
            if not model_ref:
                return _regex_extract(title, body)
            from services.llm_service import _client_and_model_for_ref
            client, model_name = _client_and_model_for_ref(model_ref, db)
        except Exception:
            _logger.warning("No LLM available for codebase analysis, using regex fallback")
            return _regex_extract(title, body)
    else:
        client, model_name = client_and_model

    prompt = _build_analysis_prompt(title, body)
    try:
        result = await _call_llm_json(client, model_name, prompt)
    except Exception:
        _logger.warning("LLM codebase analysis failed for %s, using regex fallback", title, exc_info=True)
        return _regex_extract(title, body)

    result["skipped"] = False
    return result


async def _call_llm_json(client: Any, model_name: str, prompt: str) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 响应。"""
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _CODE_ANALYSIS_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试从 markdown 代码块中提取 JSON
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            return json.loads(m.group())
        return {"table_references": [], "irrelevant": True}


def _regex_extract(title: str, body: str) -> dict[str, Any]:
    """用正则从代码文件中提取表名（LLM 不可用时的降级方案）。"""
    table_names: set[str] = set()
    content = f"{title}\n{body}"

    for pattern in [_RE_SQL_TABLE, _RE_CONFIG_TABLE, _RE_DBT_MODEL]:
        for m in pattern.finditer(content):
            name = m.group(2).strip().strip("`\"'[]")
            if name and len(name) >= 2 and not name.isdigit():
                table_names.add(name.lower())

    # ORM: __tablename__ = 'xxx' or table_name = 'xxx'
    for m in re.finditer(r"""__tablename__\s*=\s*['"](\w+)['"]""", content):
        table_names.add(m.group(1).lower())
    for m in re.finditer(r"""\.table_name\s*=\s*['"](\w+)['"]""", content):
        table_names.add(m.group(1).lower())

    refs = [{"table_name": t, "columns": [], "usage_summary": "由正则表达式提取（非 LLM 分析）"} for t in sorted(table_names)]
    return {"table_references": refs, "irrelevant": len(refs) == 0, "skipped": False, "regex_fallback": True}


# ── 持久化分析结果 ────────────────────────────────────────────────────────

def _resolve_table_meta(db: Session, table_name: str, knowledge_base_id: int) -> TableMeta | None:
    """将表名映射到 TableMeta 记录。

    查找策略：
    1. 精确匹配 table_name（大小写不敏感）
    2. 如果知识库关联了业务域，在业务域挂载的数据源范围内查找
    """
    tn = (table_name or "").strip().lower()
    if not tn or len(tn) < 2:
        return None

    # 先从关联业务域的数据源范围内查找
    from models import BusinessDomainKnowledgeBase, BusinessDomainSelection
    kb_domain_rows = (
        db.execute(
            select(BusinessDomainKnowledgeBase.domain_id).where(
                BusinessDomainKnowledgeBase.knowledge_base_id == knowledge_base_id
            )
        ).scalars().all()
    )
    if kb_domain_rows:
        datasource_ids: set[int] = set()
        for domain_id in kb_domain_rows:
            for sel in db.execute(
                select(BusinessDomainSelection).where(BusinessDomainSelection.domain_id == domain_id)
            ).scalars().all():
                if sel.datasource_id:
                    datasource_ids.add(sel.datasource_id)
        if datasource_ids:
            row = db.execute(
                select(TableMeta).where(
                    TableMeta.datasource_id.in_(datasource_ids),
                    TableMeta.table_name.ilike(tn),
                ).limit(1)
            ).scalars().first()
            if row:
                return row

    # 全局查找
    row = db.execute(
        select(TableMeta).where(TableMeta.table_name.ilike(tn)).limit(1)
    ).scalars().first()
    return row


def _fuzzy_match_table(db: Session, table_name: str) -> TableMeta | None:
    """宽松匹配：处理常见命名转换（下划线↔驼峰，复数↔单数）。"""
    tn = (table_name or "").strip()
    if not tn:
        return None
    # 直接精确匹配
    row = db.execute(
        select(TableMeta).where(TableMeta.table_name.ilike(tn)).limit(1)
    ).scalars().first()
    if row:
        return row
    # 尝试下划线→驼峰变体（在代码中常见）
    # 例如: "user_orders" → 尝试 "userOrders", "UserOrders"
    parts = tn.split("_")
    if len(parts) >= 2:
        camel = parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
        row = db.execute(
            select(TableMeta).where(TableMeta.table_name.ilike(camel)).limit(1)
        ).scalars().first()
        if row:
            return row
    # 尝试去复数 s/es
    if tn.endswith("s") and len(tn) > 3:
        singular = tn[:-1]
        row = db.execute(
            select(TableMeta).where(TableMeta.table_name.ilike(singular)).limit(1)
        ).scalars().first()
        if row:
            return row
    if tn.endswith("es") and len(tn) > 4:
        singular = tn[:-2]
        row = db.execute(
            select(TableMeta).where(TableMeta.table_name.ilike(singular)).limit(1)
        ).scalars().first()
        if row:
            return row
    return None


async def store_analysis_results(
    db: Session,
    entry: KnowledgeEntry,
    analysis: dict[str, Any],
    *,
    knowledge_base_id: int,
) -> dict[str, Any]:
    """将代码分析结果持久化：创建 TableKnowledgeEntry 链接，更新 ColumnMeta 提示。"""
    refs = analysis.get("table_references") or []
    if not refs:
        return {"linked_tables": 0, "updated_columns": 0, "table_details": []}

    linked = 0
    updated_cols = 0
    details: list[dict[str, Any]] = []

    for ref in refs:
        table_name = (ref.get("table_name") or "").strip()
        if not table_name:
            continue

        tm = _resolve_table_meta(db, table_name, knowledge_base_id)
        if not tm:
            # 表尚未登记，暂存到 source_meta 中供后续 catch-up
            _maybe_stash_pending_ref(db, entry.id, ref)
            continue

        # 创建 TableKnowledgeEntry 链接（如果尚未存在）
        existing = db.execute(
            select(TableKnowledgeEntry).where(
                TableKnowledgeEntry.table_id == tm.id,
                TableKnowledgeEntry.knowledge_entry_id == entry.id,
            )
        ).scalars().first()
        if not existing:
            db.add(TableKnowledgeEntry(table_id=tm.id, knowledge_entry_id=entry.id))
            linked += 1

        detail: dict[str, Any] = {"table_name": table_name, "table_id": tm.id, "columns_updated": []}

        # 更新列的枚举值和聚合提示
        enum_values = ref.get("enum_values") or {}
        agg_hints = ref.get("aggregation_hints") or {}
        all_cols = set(enum_values.keys()) | set(agg_hints.keys())

        for col_name in all_cols:
            col = db.execute(
                select(ColumnMeta).where(
                    ColumnMeta.table_id == tm.id,
                    ColumnMeta.column_name == col_name,
                ).limit(1)
            ).scalars().first()
            if not col:
                continue

            qm = dict(col.quality_metrics or {})
            modified = False

            # 合并枚举值
            code_enums = enum_values.get(col_name)
            if isinstance(code_enums, list) and len(code_enums) >= 2:
                existing_enum = qm.get("enum") if isinstance(qm.get("enum"), dict) else None
                if existing_enum and existing_enum.get("kind") == "mysql_enum":
                    pass  # MySQL ENUM 优先，不覆盖
                else:
                    existing_vals = set(existing_enum.get("values") or []) if existing_enum else set()
                    new_vals = set(str(v).strip() for v in code_enums if str(v).strip())
                    if new_vals - existing_vals:
                        merged = sorted((existing_vals | new_vals), key=str)
                        qm["enum"] = {
                            "kind": "code_observed" if not existing_enum else existing_enum.get("kind", "code_observed"),
                            "values": merged,
                            "note": "取值来自代码文件分析" + (f"（{existing_enum.get('note')}）" if existing_enum and existing_enum.get("note") else ""),
                        }
                        modified = True

            # 设置聚合提示
            code_agg = (agg_hints.get(col_name) or "").strip().lower()
            if code_agg in ("sum", "avg", "count", "max", "min", "latest"):
                if qm.get("aggregation_hint") != code_agg:
                    qm["aggregation_hint"] = code_agg
                    modified = True

            if modified:
                col.quality_metrics = qm
                updated_cols += 1
                detail["columns_updated"].append(col_name)

        details.append(detail)

    db.commit()
    return {"linked_tables": linked, "updated_columns": updated_cols, "table_details": details}


# 暂存未匹配的表引用（等表被分析后再处理）
_PENDING_REFS: dict[int, list[dict[str, Any]]] = {}  # entry_id → [ref, ...]


def _maybe_stash_pending_ref(db: Session, entry_id: int, ref: dict[str, Any]) -> None:
    """暂存未匹配的表引用。"""
    _PENDING_REFS.setdefault(entry_id, []).append(ref)
    # 也写到 KnowledgeEntry.source_meta 中持久化
    entry = db.get(KnowledgeEntry, entry_id)
    if entry:
        meta = dict(entry.source_meta or {})
        pending = list(meta.get("pending_table_refs") or [])
        pending.append({k: v for k, v in ref.items() if k != "usage_summary"})
        meta["pending_table_refs"] = pending[-20:]  # 最多保留 20 条
        entry.source_meta = meta
        db.commit()


async def run_codebase_analysis_for_kb(
    db: Session,
    knowledge_base_id: int,
    *,
    semantic_model_ref: str = "auto",
    concurrency: int = 3,
) -> dict[str, Any]:
    """分析知识库中所有 git 条目（增量：skip 已分析过的条目）。"""
    from models import KnowledgeEntry
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    # 查所有 git_file 条目
    entries = list(
        db.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.knowledge_base_id == knowledge_base_id,
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
            )
        ).scalars().all()
    )

    if not entries:
        return {"ok": True, "total": 0, "analyzed": 0, "message": "知识库中没有 git 同步条目"}

    # 跳过已有分析结果的条目（source_meta 中有 last_codebase_analysis 标记）
    to_analyze: list[KnowledgeEntry] = []
    skipped = 0
    for e in entries:
        meta = e.source_meta or {}
        if meta.get("codebase_analyzed"):
            skipped += 1
        else:
            to_analyze.append(e)

    if not to_analyze:
        return {"ok": True, "total": len(entries), "analyzed": 0, "skipped": skipped, "message": "所有条目均已分析"}

    # 获取 LLM 客户端
    try:
        from services.llm_models import has_any_llm_key, resolve_effective_model
        if not has_any_llm_key(db):
            return _run_regex_only(db, to_analyze, knowledge_base_id)
        model_ref = resolve_effective_model(semantic_model_ref, db)
        if not model_ref:
            return _run_regex_only(db, to_analyze, knowledge_base_id)
        from services.llm_service import _client_and_model_for_ref
        client, model_name = _client_and_model_for_ref(model_ref, db)
    except Exception as exc:
        _logger.warning("LLM not available for codebase analysis: %s", exc)
        return _run_regex_only(db, to_analyze, knowledge_base_id)

    sem = asyncio.Semaphore(concurrency)

    async def worker(entry: KnowledgeEntry) -> tuple[KnowledgeEntry, dict[str, Any]]:
        async with sem:
            result = await analyze_git_entry(
                entry, db, semantic_model_ref=model_ref,
                client_and_model=(client, model_name),
            )
            return entry, result

    results = await asyncio.gather(*(worker(e) for e in to_analyze))

    total_linked = 0
    total_cols = 0
    for entry, analysis in results:
        # 标记已分析
        meta = dict(entry.source_meta or {})
        meta["codebase_analyzed"] = True
        entry.source_meta = meta
        db.commit()

        store_result = await store_analysis_results(db, entry, analysis, knowledge_base_id=knowledge_base_id)
        total_linked += store_result["linked_tables"]
        total_cols += store_result["updated_columns"]

    return {
        "ok": True,
        "total": len(entries),
        "analyzed": len(to_analyze),
        "skipped": skipped,
        "linked_tables": total_linked,
        "updated_columns": total_cols,
        "message": f"已分析 {len(to_analyze)} 个文件，关联 {total_linked} 张表，更新 {total_cols} 个列的提示信息",
    }


def _run_regex_only(db: Session, entries: list[KnowledgeEntry], knowledge_base_id: int) -> dict[str, Any]:
    """仅用正则提取（无 LLM 可用时的降级方案）。"""
    linked = 0
    for entry in entries:
        analysis = _regex_extract(entry.title or "", entry.body or "")
        meta = dict(entry.source_meta or {})
        meta["codebase_analyzed"] = True
        meta["codebase_analysis_method"] = "regex"
        entry.source_meta = meta
        db.commit()
        linked += _sync_store_refs(db, entry, analysis)

    return {
        "ok": True,
        "total": len(entries),
        "analyzed": len(entries),
        "linked_tables": linked,
        "method": "regex",
        "message": f"已用正则表达式分析 {len(entries)} 个文件（LLM 不可用）",
    }


def _sync_store_refs(db: Session, entry: KnowledgeEntry, analysis: dict[str, Any]) -> int:
    """同步存储表引用链接（regex fallback 用）。"""
    refs = analysis.get("table_references") or []
    linked = 0
    for ref in refs:
        table_name = (ref.get("table_name") or "").strip()
        if not table_name:
            continue
        rows = db.execute(
            select(TableMeta).where(TableMeta.table_name.ilike(table_name)).limit(1)
        ).scalars().all()
        for tm in rows:
            existing = db.execute(
                select(TableKnowledgeEntry).where(
                    TableKnowledgeEntry.table_id == tm.id,
                    TableKnowledgeEntry.knowledge_entry_id == entry.id,
                )
            ).scalars().first()
            if not existing:
                db.add(TableKnowledgeEntry(table_id=tm.id, knowledge_entry_id=entry.id))
                linked += 1
    db.commit()
    return linked


async def catch_up_pending_refs(
    db: Session,
    table_id: int | None = None,
    *,
    semantic_model_ref: str = "auto",
) -> dict[str, Any]:
    """当新表被分析后调用：尝试匹配之前暂存的未解析表引用，并补填 ColumnMeta 提示。

    如果指定 table_id，仅处理该表；否则处理所有已分析表中仍有 pending refs 的。
    """
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    if table_id:
        tm = db.get(TableMeta, table_id)
        if not tm:
            return {"ok": False, "error": "表不存在"}
        table_names = [tm.table_name]
    else:
        table_names = []

    # 查找所有有 pending_table_refs 的 git 条目
    entries = list(
        db.execute(
            select(KnowledgeEntry).where(
                cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
                cast(KnowledgeEntry.source_meta, JSONB)["pending_table_refs"].isnot(None),
            )
        ).scalars().all()
    )

    if not entries:
        return {"ok": True, "matched": 0, "message": "没有待处理的暂存引用"}

    matched = 0
    updated_cols = 0
    for entry in entries:
        meta = dict(entry.source_meta or {})
        pending: list[dict[str, Any]] = list(meta.get("pending_table_refs") or [])
        remaining: list[dict[str, Any]] = []

        for ref in pending:
            tn = (ref.get("table_name") or "").strip()
            if not tn:
                continue

            # 如果指定了 table_id，只处理匹配该表名的
            if table_names and tn.lower() not in [t.lower() for t in table_names]:
                remaining.append(ref)
                continue

            tm = db.execute(
                select(TableMeta).where(TableMeta.table_name.ilike(tn)).limit(1)
            ).scalars().first()

            if not tm:
                tm = _fuzzy_match_table(db, tn)

            if tm:
                # 创建 TableKnowledgeEntry 链接
                existing = db.execute(
                    select(TableKnowledgeEntry).where(
                        TableKnowledgeEntry.table_id == tm.id,
                        TableKnowledgeEntry.knowledge_entry_id == entry.id,
                    )
                ).scalars().first()
                if not existing:
                    db.add(TableKnowledgeEntry(table_id=tm.id, knowledge_entry_id=entry.id))
                    matched += 1

                # 补填 ColumnMeta 的枚举值和聚合提示
                enum_values = ref.get("enum_values") or {}
                agg_hints = ref.get("aggregation_hints") or {}
                for col_name in set(enum_values.keys()) | set(agg_hints.keys()):
                    col = db.execute(
                        select(ColumnMeta).where(
                            ColumnMeta.table_id == tm.id,
                            ColumnMeta.column_name == col_name,
                        ).limit(1)
                    ).scalars().first()
                    if not col:
                        continue
                    qm = dict(col.quality_metrics or {})
                    modified = False

                    code_enums = enum_values.get(col_name)
                    if isinstance(code_enums, list) and len(code_enums) >= 2:
                        existing_enum = qm.get("enum") if isinstance(qm.get("enum"), dict) else None
                        if not (existing_enum and existing_enum.get("kind") == "mysql_enum"):
                            existing_vals = set(existing_enum.get("values") or []) if existing_enum else set()
                            new_vals = set(str(v).strip() for v in code_enums if str(v).strip())
                            if new_vals - existing_vals:
                                merged = sorted((existing_vals | new_vals), key=str)
                                qm["enum"] = {
                                    "kind": "code_observed",
                                    "values": merged,
                                    "note": "取值来自代码文件分析",
                                }
                                modified = True

                    code_agg = (agg_hints.get(col_name) or "").strip().lower()
                    if code_agg in ("sum", "avg", "count", "max", "min", "latest"):
                        if qm.get("aggregation_hint") != code_agg:
                            qm["aggregation_hint"] = code_agg
                            modified = True

                    if modified:
                        col.quality_metrics = qm
                        updated_cols += 1
            else:
                remaining.append(ref)

        if remaining:
            meta["pending_table_refs"] = remaining
        else:
            meta.pop("pending_table_refs", None)
        entry.source_meta = meta

    db.commit()
    return {"ok": True, "matched": matched, "updated_columns": updated_cols, "message": f"已匹配 {matched} 条暂存引用，更新 {updated_cols} 个列提示"}
