"""SQLAlchemy ORM join and __tablename__ patterns."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import ExtractionHits, JoinEdge
from services.extraction.code_patterns.regex_common import (
    RE_TABLENAME_ASSIGN,
    is_valid_table_name,
    normalize_table_name,
)

_RE_QUERY_JOIN = re.compile(
    r"session\.query\s*\(\s*(\w+)\s*\)\.join\s*\(\s*(\w+)",
    re.IGNORECASE,
)
_RE_CLASS_TABLENAME = re.compile(
    r"class\s+(\w+).*?:.*?__tablename__\s*=\s*['\"](\w+)['\"]",
    re.IGNORECASE | re.DOTALL,
)


def _class_table_map(body: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for m in _RE_CLASS_TABLENAME.finditer(body):
        mapping[m.group(1)] = normalize_table_name(m.group(2))
    for m in RE_TABLENAME_ASSIGN.finditer(body):
        # standalone tablename without class context
        pass
    return mapping


def extract_orm_joins(body: str) -> tuple[list[JoinEdge], ExtractionHits]:
    hits = ExtractionHits()
    joins: list[JoinEdge] = []
    class_map = _class_table_map(body)

    for m in _RE_QUERY_JOIN.finditer(body):
        left_cls, right_cls = m.group(1), m.group(2)
        left = class_map.get(left_cls, normalize_table_name(left_cls))
        right = class_map.get(right_cls, normalize_table_name(right_cls))
        if not is_valid_table_name(left) or not is_valid_table_name(right):
            continue
        joins.append(
            JoinEdge(
                left_table=left,
                right_table=right,
                join_key=f"{left}.id = {right}.id",
                provenance="regex:orm_join",
                confidence=78.0,
            )
        )
        hits.orm_join += 1

    return joins, hits
