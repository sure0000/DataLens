"""Pandas read_sql / merge / to_sql patterns."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import ExtractionHits, JoinEdge, LineageEdge
from services.extraction.code_patterns.regex_common import is_valid_table_name, normalize_table_name
from services.extraction.code_patterns.sql import extract_sql_lineage

_RE_READ_SQL = re.compile(
    r"(?:pd|pandas)\.read_sql\s*\(\s*(['\"]{3}.*?['\"]{3}|f?['\"].*?['\"]|[^,)]+)",
    re.IGNORECASE | re.DOTALL,
)
_RE_TO_SQL = re.compile(
    r"\.to_sql\s*\(\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)
_RE_MERGE = re.compile(
    r"(?:pd|pandas)\.merge\s*\(\s*(\w+)\s*,\s*(\w+)\s*,.*?on\s*=\s*(?:\[([^\]]+)\]|['\"](\w+)['\"]|(\w+))",
    re.IGNORECASE | re.DOTALL,
)
_RE_VAR_READ = re.compile(
    r"(\w+)\s*=\s*(?:pd|pandas)\.read_sql\s*\(\s*['\"]{3}(.*?)['\"]{3}",
    re.IGNORECASE | re.DOTALL,
)


def _var_to_table(body: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for m in _RE_VAR_READ.finditer(body):
        var_name = m.group(1)
        sql = m.group(2)
        for edge in extract_sql_lineage(sql, provenance="regex:pandas_read_sql"):
            mapping[var_name] = edge.source_table
            break
        if var_name not in mapping:
            from_match = re.search(r"\bFROM\s+(\w+)", sql, re.IGNORECASE)
            if from_match and is_valid_table_name(from_match.group(1)):
                mapping[var_name] = normalize_table_name(from_match.group(1))
    return mapping


def extract_pandas_lineage(body: str) -> tuple[list[LineageEdge], ExtractionHits]:
    hits = ExtractionHits()
    edges: list[LineageEdge] = []
    var_map = _var_to_table(body)

    read_tables: list[str] = []
    for m in _RE_READ_SQL.finditer(body):
        arg = m.group(1)
        if arg.startswith(("'''", '"""', "'", '"')):
            inner = arg.strip("'\"")
            for edge in extract_sql_lineage(inner, provenance="regex:pandas_read_sql"):
                read_tables.append(edge.source_table)
                hits.pandas_read_sql += 1
        else:
            tbl = normalize_table_name(arg)
            if is_valid_table_name(tbl):
                read_tables.append(tbl)
                hits.pandas_read_sql += 1

    write_tables = [normalize_table_name(m.group(1)) for m in _RE_TO_SQL.finditer(body)]
    for src in read_tables:
        for tgt in write_tables:
            if src and tgt and src != tgt:
                edges.append(
                    LineageEdge(
                        source_table=src,
                        target_table=tgt,
                        source_field=src,
                        target_field=tgt,
                        provenance="regex:pandas_read_sql",
                        confidence=85.0,
                    )
                )

    if read_tables and not write_tables:
        hits.single_table_refs += len(read_tables)

    return edges, hits


def extract_pandas_joins(body: str) -> tuple[list[JoinEdge], ExtractionHits]:
    hits = ExtractionHits()
    joins: list[JoinEdge] = []
    var_map = _var_to_table(body)

    for m in _RE_MERGE.finditer(body):
        left_var, right_var = m.group(1), m.group(2)
        on_cols = m.group(3) or m.group(4) or m.group(5) or ""
        left_table = var_map.get(left_var, left_var)
        right_table = var_map.get(right_var, right_var)
        if not is_valid_table_name(left_table) or not is_valid_table_name(right_table):
            continue
        join_key = on_cols.strip().strip("'\"") or f"{left_table}.{on_cols}"
        joins.append(
            JoinEdge(
                left_table=left_table,
                right_table=right_table,
                join_key=join_key,
                provenance="regex:pandas_merge",
                confidence=80.0,
            )
        )
        hits.pandas_merge += 1

    return joins, hits
