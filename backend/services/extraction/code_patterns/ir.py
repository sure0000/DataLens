"""Intermediate representation for rule-based code extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LineageEdge:
    source_table: str
    target_table: str
    source_field: str = ""
    target_field: str = ""
    layer: str = "DWD"
    transform_logic: str = ""
    confidence: float = 90.0
    provenance: str = "regex:sql"


@dataclass
class JoinEdge:
    left_table: str
    right_table: str
    join_key: str
    join_type: str = "inner"
    confidence: float = 85.0
    provenance: str = "regex:sql"


@dataclass
class DomainTerm:
    """Business concept extracted from Python domain models (Enum / dataclass)."""

    name: str
    definition: str
    code_name: str = ""
    term_type: str = "entity"
    related_fields: list[str] = field(default_factory=list)
    confidence: float = 88.0
    provenance: str = "ast:python_domain"


@dataclass
class ExtractionHits:
    """Per-entry regex hit counters for diagnostics."""

    sql: int = 0
    pandas_merge: int = 0
    pandas_read_sql: int = 0
    pyspark_join: int = 0
    pyspark_sql: int = 0
    orm_join: int = 0
    dbt_ref: int = 0
    embedded_sql: int = 0
    single_table_refs: int = 0

    def merge(self, other: ExtractionHits) -> None:
        for key in self.__dataclass_fields__:
            setattr(self, key, getattr(self, key) + getattr(other, key))

    def to_dict(self) -> dict[str, int]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__ if getattr(self, k)}
