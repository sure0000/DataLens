"""Shared regex patterns for table/SQL detection — used by codebase_analyzer and code_patterns."""

from __future__ import annotations

import re

RE_SQL_TABLE = re.compile(
    r"\b(FROM|JOIN|INTO|UPDATE|TABLE|INSERT\s+INTO|MERGE\s+INTO)\s+[`\"'\[\]]?(\w+)[`\"'\[\]]?",
    re.IGNORECASE,
)

RE_ORM_TABLE = re.compile(
    r"__(tablename__|table_args__)|class\s+\w+.*Base|db\.Table\(|\.table_name\s*=\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)

RE_CONFIG_TABLE = re.compile(
    r"(table|source_table|target_table|table_name|tablename)\s*:\s*['\"]?(\w+)['\"]?",
    re.IGNORECASE,
)

RE_DBT_MODEL = re.compile(
    r"(ref|source)\s*\(\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)

RE_TABLENAME_ASSIGN = re.compile(r"""__tablename__\s*=\s*['"](\w+)['"]""", re.IGNORECASE)
RE_TABLE_NAME_ASSIGN = re.compile(r"""\.table_name\s*=\s*['"](\w+)['"]""", re.IGNORECASE)

# SQL fragments inside Python / Java / Go strings
RE_TRIPLE_QUOTED = re.compile(r'(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', re.DOTALL)
RE_FSTRING_SQL = re.compile(r'f["\'](.*?)["\']', re.DOTALL)
RE_BACKTICK_SQL = re.compile(r"`([^`]+)`", re.DOTALL)

SKIP_EXTENSIONS = frozenset({
    ".lock", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".map", ".min.js", ".min.css", ".pdf", ".zip", ".tar",
    ".gz", ".whl", ".egg",
})


def normalize_table_name(name: str) -> str:
    n = (name or "").strip().strip('`"\'[]')
    if "." in n:
        n = n.rsplit(".", 1)[-1]
    return n.lower() if n else ""


def is_valid_table_name(name: str) -> bool:
    n = normalize_table_name(name)
    if not n or len(n) < 2 or n.isdigit():
        return False
    if n in {"select", "where", "from", "join", "on", "as", "and", "or", "set", "values"}:
        return False
    return True
