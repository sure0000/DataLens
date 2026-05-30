"""dbt YAML ref/source lineage."""

from __future__ import annotations

import re

from services.extraction.code_patterns.ir import ExtractionHits, LineageEdge
from services.extraction.code_patterns.regex_common import RE_DBT_MODEL, is_valid_table_name, normalize_table_name

_RE_DBT_REF_ITEM = re.compile(r"^\s*-\s*(\w+)\s*$", re.MULTILINE)
_RE_MODEL_NAME = re.compile(r"^[\s-]*name\s*:\s*['\"]?(\w+)['\"]?", re.MULTILINE)


def extract_dbt_lineage(body: str, path: str = "") -> tuple[list[LineageEdge], ExtractionHits]:
    hits = ExtractionHits()
    edges: list[LineageEdge] = []
    target = ""

    name_m = _RE_MODEL_NAME.search(body)
    if name_m:
        target = normalize_table_name(name_m.group(1))
    elif path:
        stem = path.rsplit("/", 1)[-1]
        for ext in (".yml", ".yaml", ".sql"):
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        target = normalize_table_name(stem)

    for m in RE_DBT_MODEL.finditer(body):
        src = normalize_table_name(m.group(2))
        if is_valid_table_name(src) and target and src != target:
            edges.append(
                LineageEdge(source_table=src, target_table=target, provenance="regex:dbt_ref", confidence=88.0)
            )
            hits.dbt_ref += 1

    in_depends = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("depends_on"):
            in_depends = True
            continue
        if in_depends:
            if stripped and not stripped.startswith("-") and ":" in stripped and not stripped.startswith("ref"):
                in_depends = False
                continue
            m_item = _RE_DBT_REF_ITEM.match(line)
            if m_item and target:
                src = normalize_table_name(m_item.group(1))
                if is_valid_table_name(src) and src != target:
                    edges.append(
                        LineageEdge(source_table=src, target_table=target, provenance="regex:dbt_ref", confidence=88.0)
                    )
                    hits.dbt_ref += 1

    return edges, hits
