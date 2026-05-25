"""语义 Grounding：从结构化 table_refs / column_refs 解析域内 TableMeta。"""
from __future__ import annotations

import re
import re
from typing import Any

from models import TableMeta

_SHORT_TABLE_NAME_LEN = 6


def _blob_tokens(blob: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", blob.lower()))


def _fq_table_name_in_blob(db_name: str, table_name: str, blob_lower: str) -> bool:
    fq = f"{(db_name or '').strip()}.{(table_name or '').strip()}".lower()
    if not fq or fq == ".":
        return False
    pattern = r"(?:^|(?<![\w\u4e00-\u9fff]))" + re.escape(fq) + r"(?:$|(?![\w\u4e00-\u9fff]))"
    return bool(re.search(pattern, blob_lower))


def _resolve_table_ref(ref: str, domain_tables: list[TableMeta]) -> int | None:
    ref_l = (ref or "").strip().lower()
    if not ref_l:
        return None
    for t in domain_tables:
        fq = f"{t.database_name}.{t.table_name}".lower()
        tn = (t.table_name or "").lower()
        db = (t.database_name or "").lower()
        if ref_l == fq or ref_l == tn or ref_l == db:
            return t.id
        if "." in ref_l:
            parts = ref_l.split(".")
            if len(parts) >= 2 and parts[-1] == tn and parts[-2] == db:
                return t.id
            if parts[-1] == tn:
                return t.id
    return None


def match_tables_from_grounding(
    domain_tables: list[TableMeta],
    grounding: dict[str, Any] | None,
    *,
    already_matched: set[int],
    allowed: set[int],
) -> list[int]:
    """从 semantic_meta.grounding 解析 table_id；优先于正文子串匹配。"""
    if not grounding or not domain_tables:
        return []

    matched: list[int] = []
    seen: set[int] = set(already_matched)

    for raw in grounding.get("table_refs") or []:
        ref = str(raw or "").strip()
        if not ref:
            continue
        tid = _resolve_table_ref(ref, domain_tables)
        if tid is not None and tid in allowed and tid not in seen:
            seen.add(tid)
            matched.append(tid)

    for raw in grounding.get("column_refs") or []:
        field = str(raw or "").strip()
        if not field or "." not in field:
            continue
        table_part = field.rsplit(".", 1)[0].strip()
        tid = _resolve_table_ref(table_part, domain_tables)
        if tid is not None and tid in allowed and tid not in seen:
            seen.add(tid)
            matched.append(tid)

    blob = " ".join(
        str(x)
        for x in (grounding.get("table_refs") or []) + (grounding.get("column_refs") or [])
    ).lower()
    if not blob:
        return matched

    tokens = _blob_tokens(blob)
    for t in domain_tables:
        if t.id in seen or t.id not in allowed:
            continue
        tn = (t.table_name or "").strip()
        if not tn:
            continue
        if _fq_table_name_in_blob(t.database_name or "", tn, blob):
            seen.add(t.id)
            matched.append(t.id)

    for t in domain_tables:
        if t.id in seen or t.id not in allowed:
            continue
        tn = (t.table_name or "").strip()
        if len(tn) < _SHORT_TABLE_NAME_LEN:
            continue
        if tn.lower() in tokens:
            seen.add(t.id)
            matched.append(t.id)

    return matched


def dominant_semantic_role(chunk_metas: list[dict[str, Any] | None]) -> str | None:
    """按 confidence 加权聚合 chunk semantic_role。"""
    weights: dict[str, float] = {}
    for meta in chunk_metas:
        if not meta:
            continue
        role = (meta.get("semantic_role") or "").strip()
        if not role:
            continue
        try:
            conf = float(meta.get("confidence", 50))
        except (TypeError, ValueError):
            conf = 50.0
        weights[role] = weights.get(role, 0.0) + max(conf, 1.0)
    if not weights:
        return None
    return max(weights, key=weights.get)


_ROLE_HINT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("join_guide", re.compile(r"join|关联|连接|left\s+join|inner\s+join", re.I)),
    ("business_metric", re.compile(r"指标|口径|gmv|营收|转化|客单价|复购|留存", re.I)),
    ("column_glossary", re.compile(r"字段|列名|含义|字典", re.I)),
    ("query_pattern", re.compile(r"sql|查询|示例|怎么查", re.I)),
]


def infer_semantic_role_hints(question: str) -> set[str]:
    """从问句推断优先检索的 semantic_role。"""
    q = (question or "").strip()
    if not q:
        return set()
    hints: set[str] = set()
    for role, pattern in _ROLE_HINT_PATTERNS:
        if pattern.search(q):
            hints.add(role)
    return hints


def table_ids_from_bound_refs(
    domain_tables: list[TableMeta],
    refs: list[Any] | None,
    *,
    allowed: set[int],
) -> set[int]:
    grounding = {"table_refs": [str(x) for x in (refs or []) if str(x or "").strip()], "column_refs": []}
    return set(
        match_tables_from_grounding(
            domain_tables,
            grounding,
            already_matched=set(),
            allowed=allowed,
        )
    )
