"""PySpark sql() and DataFrame.join patterns."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import ExtractionHits, JoinEdge, LineageEdge
from services.extraction.code_patterns.regex_common import is_valid_table_name, normalize_table_name
from services.extraction.code_patterns.sql import extract_sql_joins, extract_sql_lineage

_RE_SPARK_SQL = re.compile(
    r"spark\.sql\s*\(\s*(['\"]{3}.*?['\"]{3}|f?['\"].*?['\"])",
    re.IGNORECASE | re.DOTALL,
)
_RE_DF_JOIN = re.compile(
    r"\.join\s*\(\s*(\w+)\s*,\s*(?:on\s*=\s*)?['\"]?(\w+)['\"]?",
    re.IGNORECASE,
)
_RE_CREATE_VIEW = re.compile(
    r"createOrReplaceTempView\s*\(\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)


def extract_spark_lineage(body: str) -> tuple[list[LineageEdge], ExtractionHits]:
    hits = ExtractionHits()
    edges: list[LineageEdge] = []
    views: list[str] = []

    for m in _RE_SPARK_SQL.finditer(body):
        sql = m.group(1).strip("'\"")
        found = extract_sql_lineage(sql, provenance="regex:pyspark_sql")
        if found:
            hits.pyspark_sql += len(found)
            edges.extend(found)

    for m in _RE_CREATE_VIEW.finditer(body):
        views.append(normalize_table_name(m.group(1)))

    return edges, hits


def extract_spark_joins(body: str) -> tuple[list[JoinEdge], ExtractionHits]:
    hits = ExtractionHits()
    joins: list[JoinEdge] = []

    for m in _RE_SPARK_SQL.finditer(body):
        sql = m.group(1).strip("'\"")
        found = extract_sql_joins(sql, provenance="regex:pyspark_sql")
        if found:
            hits.pyspark_sql += len(found)
            joins.extend(found)

    for m in _RE_DF_JOIN.finditer(body):
        right_var, on_col = m.group(1), m.group(2)
        right = normalize_table_name(right_var)
        if is_valid_table_name(right):
            joins.append(
                JoinEdge(
                    left_table="unknown",
                    right_table=right,
                    join_key=on_col,
                    provenance="regex:pyspark_join",
                    confidence=75.0,
                )
            )
            hits.pyspark_join += 1

    return [j for j in joins if j.left_table != "unknown" or j.confidence >= 75], hits
