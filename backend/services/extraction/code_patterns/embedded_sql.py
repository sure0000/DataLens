"""Java @Select / Go backtick embedded SQL."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import ExtractionHits, JoinEdge, LineageEdge
from services.extraction.code_patterns.regex_common import RE_BACKTICK_SQL
from services.extraction.code_patterns.sql import extract_sql_joins, extract_sql_lineage

_RE_JAVA_SELECT = re.compile(
    r'@Select\s*\(\s*"((?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)


def _collect_sql_strings(body: str, path: str) -> list[str]:
    fragments: list[str] = []
    for m in _RE_JAVA_SELECT.finditer(body):
        fragments.append(m.group(1))
    if path.endswith(".go") or "`" in body:
        for m in RE_BACKTICK_SQL.finditer(body):
            text = m.group(1)
            if re.search(r"\b(SELECT|FROM|JOIN|INSERT)\b", text, re.IGNORECASE):
                fragments.append(text)
    return fragments


def extract_embedded_sql_lineage(body: str, path: str = "") -> tuple[list[LineageEdge], ExtractionHits]:
    hits = ExtractionHits()
    edges: list[LineageEdge] = []
    for sql in _collect_sql_strings(body, path):
        found = extract_sql_lineage(sql, provenance="regex:embedded_sql")
        if found:
            hits.embedded_sql += len(found)
            edges.extend(found)
    return edges, hits


def extract_embedded_sql_joins(body: str, path: str = "") -> tuple[list[JoinEdge], ExtractionHits]:
    hits = ExtractionHits()
    joins: list[JoinEdge] = []
    for sql in _collect_sql_strings(body, path):
        found = extract_sql_joins(sql, provenance="regex:embedded_sql")
        if found:
            hits.embedded_sql += len(found)
            joins.extend(found)
    return joins, hits
