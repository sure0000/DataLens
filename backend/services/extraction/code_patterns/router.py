"""Route code entries to language-specific extractors."""

from __future__ import annotations

from typing import Any

from services.extraction.code_patterns.dbt_yaml import extract_dbt_lineage
from services.extraction.code_patterns.embedded_sql import extract_embedded_sql_joins, extract_embedded_sql_lineage
from services.extraction.code_patterns.ir import ExtractionHits, JoinEdge, LineageEdge
from services.extraction.code_patterns.python_orm import extract_orm_joins
from services.extraction.code_patterns.python_pandas import extract_pandas_joins, extract_pandas_lineage
from services.extraction.code_patterns.python_spark import extract_spark_joins, extract_spark_lineage
from services.extraction.code_patterns.python_sql import extract_python_sql_joins, extract_python_sql_lineage
from services.extraction.code_patterns.sql import extract_sql_joins, extract_sql_lineage


def entry_path(entry: Any) -> str:
    meta = getattr(entry, "source_meta", None) or {}
    if isinstance(meta, dict):
        ref = str(meta.get("ref") or "").strip()
        if ref:
            return ref
    return str(getattr(entry, "title", "") or "")


def entry_body(entry: Any) -> str:
    return (getattr(entry, "body", None) or "").strip()


def _ext(path: str) -> str:
    lower = path.lower()
    for candidate in (".sql", ".hql", ".py", ".yml", ".yaml", ".java", ".go", ".scala"):
        if lower.endswith(candidate):
            return candidate
    if "." in lower.rsplit("/", 1)[-1]:
        return "." + lower.rsplit(".", 1)[-1]
    return ""


def extract_lineage_from_entry(entry: Any) -> tuple[list[LineageEdge], ExtractionHits]:
    path = entry_path(entry)
    body = entry_body(entry)
    ext = _ext(path)
    hits = ExtractionHits()
    edges: list[LineageEdge] = []

    def _merge(found: list[LineageEdge], h: ExtractionHits) -> None:
        edges.extend(found)
        hits.merge(h)

    if ext in (".sql", ".hql"):
        found = extract_sql_lineage(body)
        hits.sql = len(found)
        edges.extend(found)
    elif ext == ".py":
        for fn in (extract_python_sql_lineage, extract_pandas_lineage, extract_spark_lineage):
            found, h = fn(body)
            _merge(found, h)
    elif ext in (".yml", ".yaml"):
        found, h = extract_dbt_lineage(body, path)
        _merge(found, h)
    elif ext in (".java", ".go", ".scala"):
        found, h = extract_embedded_sql_lineage(body, path)
        _merge(found, h)
        if ext == ".scala":
            found2, h2 = extract_spark_lineage(body)
            _merge(found2, h2)
    else:
        if "SELECT" in body.upper() or "JOIN" in body.upper():
            found = extract_sql_lineage(body)
            hits.sql = len(found)
            edges.extend(found)

    return _dedupe_lineage(edges), hits


def extract_joins_from_entry(entry: Any) -> tuple[list[JoinEdge], ExtractionHits]:
    path = entry_path(entry)
    body = entry_body(entry)
    ext = _ext(path)
    hits = ExtractionHits()
    joins: list[JoinEdge] = []

    def _merge(found: list[JoinEdge], h: ExtractionHits) -> None:
        joins.extend(found)
        hits.merge(h)

    if ext in (".sql", ".hql"):
        found = extract_sql_joins(body)
        hits.sql = len(found)
        joins.extend(found)
    elif ext == ".py":
        for fn in (extract_python_sql_joins, extract_pandas_joins, extract_spark_joins, extract_orm_joins):
            found, h = fn(body)
            _merge(found, h)
    elif ext in (".java", ".go", ".scala"):
        found, h = extract_embedded_sql_joins(body, path)
        _merge(found, h)
        if ext == ".scala":
            found2, h2 = extract_spark_joins(body)
            _merge(found2, h2)
    else:
        if "JOIN" in body.upper():
            found = extract_sql_joins(body)
            hits.sql = len(found)
            joins.extend(found)

    return _dedupe_joins(joins), hits


def _dedupe_lineage(edges: list[LineageEdge]) -> list[LineageEdge]:
    seen: set[tuple[str, str]] = set()
    out: list[LineageEdge] = []
    for e in edges:
        pair = (e.source_table, e.target_table)
        if pair in seen:
            continue
        seen.add(pair)
        out.append(e)
    return out


def _dedupe_joins(joins: list[JoinEdge]) -> list[JoinEdge]:
    seen: set[tuple[str, str, str]] = set()
    out: list[JoinEdge] = []
    for j in joins:
        sig = (j.left_table, j.right_table, j.join_key.lower())
        if sig in seen:
            continue
        seen.add(sig)
        out.append(j)
    return out
