"""Extract embedded SQL from Python strings."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import ExtractionHits, JoinEdge, LineageEdge
from services.extraction.code_patterns.regex_common import RE_FSTRING_SQL, RE_TRIPLE_QUOTED
from services.extraction.code_patterns.sql import extract_sql_joins, extract_sql_lineage

_RE_SQL_HINT = re.compile(r"\b(SELECT|INSERT|FROM|JOIN|CREATE\s+TABLE)\b", re.IGNORECASE)


def _embedded_sql_fragments(body: str) -> list[str]:
    fragments: list[str] = []
    for pattern in (RE_TRIPLE_QUOTED, RE_FSTRING_SQL):
        for m in pattern.finditer(body):
            text = m.group(1)
            if _RE_SQL_HINT.search(text):
                fragments.append(text)
    return fragments


def extract_python_sql_lineage(body: str) -> tuple[list[LineageEdge], ExtractionHits]:
    hits = ExtractionHits()
    edges: list[LineageEdge] = []
    for frag in _embedded_sql_fragments(body):
        found = extract_sql_lineage(frag, provenance="regex:python_sql")
        if found:
            hits.sql += len(found)
            edges.extend(found)
    return edges, hits


def extract_python_sql_joins(body: str) -> tuple[list[JoinEdge], ExtractionHits]:
    hits = ExtractionHits()
    joins: list[JoinEdge] = []
    for frag in _embedded_sql_fragments(body):
        found = extract_sql_joins(frag, provenance="regex:python_sql")
        if found:
            hits.sql += len(found)
            joins.extend(found)
    return joins, hits
