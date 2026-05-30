"""Pure SQL file / fragment extraction."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import JoinEdge, LineageEdge
from services.extraction.code_patterns.regex_common import is_valid_table_name, normalize_table_name

_RE_INSERT_SELECT = re.compile(
    r"INSERT\s+INTO\s+[`\"'\[]?(\w+)[`\"'\]]?\s+.*?FROM\s+[`\"'\[]?(\w+)[`\"'\]]?",
    re.IGNORECASE | re.DOTALL,
)
_RE_CREATE_AS = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+[`\"'\[]?(\w+)[`\"'\]]?\s+.*?AS\s+SELECT.*?FROM\s+[`\"'\[]?(\w+)[`\"'\]]?",
    re.IGNORECASE | re.DOTALL,
)
_RE_JOIN = re.compile(
    r"\b(INNER\s+JOIN|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|FULL\s+(?:OUTER\s+)?JOIN|JOIN)\s+"
    r"[`\"'\[]?(\w+)[`\"'\]]?\s+(?:\w+\s+)?ON\s+([^;\n]+)",
    re.IGNORECASE,
)
_RE_FROM_TABLE = re.compile(
    r"\bFROM\s+[`\"'\[]?(\w+)[`\"'\]]?",
    re.IGNORECASE,
)


def _join_type_from_keyword(kw: str) -> str:
    k = kw.upper()
    if "LEFT" in k:
        return "left"
    if "RIGHT" in k:
        return "right"
    if "FULL" in k:
        return "full"
    return "inner"


def extract_sql_lineage(sql_text: str, *, provenance: str = "regex:sql") -> list[LineageEdge]:
    edges: list[LineageEdge] = []
    seen: set[tuple[str, str]] = set()

    for pattern in (_RE_INSERT_SELECT, _RE_CREATE_AS):
        for m in pattern.finditer(sql_text):
            tgt, src = normalize_table_name(m.group(1)), normalize_table_name(m.group(2))
            if not is_valid_table_name(tgt) or not is_valid_table_name(src) or tgt == src:
                continue
            pair = (src, tgt)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(
                LineageEdge(
                    source_table=src,
                    target_table=tgt,
                    source_field=src,
                    target_field=tgt,
                    provenance=provenance,
                )
            )

    # Fallback: first FROM + INSERT INTO in same script
    inserts = re.findall(r"INSERT\s+INTO\s+[`\"'\[]?(\w+)", sql_text, re.IGNORECASE)
    froms = _RE_FROM_TABLE.findall(sql_text)
    if inserts and froms:
        tgt = normalize_table_name(inserts[-1])
        src = normalize_table_name(froms[0])
        pair = (src, tgt)
        if is_valid_table_name(tgt) and is_valid_table_name(src) and tgt != src and pair not in seen:
            edges.append(
                LineageEdge(source_table=src, target_table=tgt, source_field=src, target_field=tgt, provenance=provenance)
            )

    return edges


def extract_sql_joins(sql_text: str, *, provenance: str = "regex:sql") -> list[JoinEdge]:
    joins: list[JoinEdge] = []
    seen: set[tuple[str, str, str]] = set()

    from_tables = [normalize_table_name(t) for t in _RE_FROM_TABLE.findall(sql_text)]
    left_default = from_tables[0] if from_tables else ""

    for m in _RE_JOIN.finditer(sql_text):
        join_kw, right_table, condition = m.group(1), m.group(2), m.group(3)
        join_key = condition.strip()[:200]
        left = left_default if is_valid_table_name(left_default) else ""
        right = normalize_table_name(right_table)

        cond_match = re.search(r"(\w+)\.\w+\s*=\s*(\w+)\.\w+", condition)
        if cond_match:
            left_alias = normalize_table_name(cond_match.group(1))
            right_alias = normalize_table_name(cond_match.group(2))
            if is_valid_table_name(left_alias) and len(left_alias) > 2:
                left = left_alias
            if is_valid_table_name(right_alias) and len(right_alias) > 2:
                right = right_alias

        if not is_valid_table_name(left) and is_valid_table_name(left_default):
            left = left_default
        if not is_valid_table_name(left) or not is_valid_table_name(right):
            continue
        sig = (left, right, join_key.lower())
        if sig in seen:
            continue
        seen.add(sig)
        joins.append(
            JoinEdge(
                left_table=left,
                right_table=right,
                join_key=join_key,
                join_type=_join_type_from_keyword(join_kw),
                provenance=provenance,
            )
        )

    return joins
