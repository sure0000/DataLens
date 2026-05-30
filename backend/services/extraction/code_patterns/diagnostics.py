"""Aggregate _git_diagnostics for orchestrator pipeline steps."""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.extraction.code_patterns.ir import ExtractionHits
from services.extraction.code_patterns.router import entry_path


class GitDiagnostics:
    """Collects git extraction statistics for pipeline failure diagnostics."""

    def __init__(self, *, total_entries: int = 0, processed_limit: int = 0) -> None:
        self.total_entries = total_entries
        self.processed_limit = processed_limit
        self.processed_entries = 0
        self.eligible_body_ge_min = 0
        self.by_ext: Counter[str] = Counter()
        self.regex_hits: ExtractionHits = ExtractionHits()
        self.llm_lineage_triples = 0
        self.llm_join_triples = 0
        self.regex_lineage_triples = 0
        self.regex_join_triples = 0
        self.domain_terms = 0
        self.sample_paths: list[str] = []
        self.single_table_refs = 0
        self.min_body_chars = 50

    def record_entry(self, entry: Any, body: str) -> None:
        self.processed_entries += 1
        path = entry_path(entry)
        ext = ""
        if "." in path.rsplit("/", 1)[-1]:
            ext = "." + path.rsplit(".", 1)[-1].lower()
        self.by_ext[ext or "(none)"] += 1
        if len(body) >= self.min_body_chars:
            self.eligible_body_ge_min += 1
        if len(self.sample_paths) < 5 and path:
            self.sample_paths.append(path)

    def record_regex_hits(self, hits: ExtractionHits) -> None:
        self.regex_hits.merge(hits)
        self.single_table_refs += hits.single_table_refs

    def record_llm_lineage(self, count: int) -> None:
        self.llm_lineage_triples += count

    def record_llm_join(self, count: int) -> None:
        self.llm_join_triples += count

    def record_regex_lineage(self, count: int) -> None:
        self.regex_lineage_triples += count

    def record_regex_join(self, count: int) -> None:
        self.regex_join_triples += count

    def record_domain_terms(self, count: int) -> None:
        self.domain_terms += count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "processed_entries": self.processed_entries,
            "processed_limit": self.processed_limit,
            "eligible_body_ge_min": self.eligible_body_ge_min,
            "min_body_chars": self.min_body_chars,
            "by_ext": dict(self.by_ext),
            "regex_hits": self.regex_hits.to_dict(),
            "llm_lineage_triples": self.llm_lineage_triples,
            "llm_join_triples": self.llm_join_triples,
            "regex_lineage_edges": self.regex_lineage_triples,
            "regex_join_edges": self.regex_join_triples,
            "domain_terms": self.domain_terms,
            "single_table_refs": self.single_table_refs,
            "sample_paths": self.sample_paths,
        }


def merge_git_diagnostics(existing: dict[str, Any] | None, diag: GitDiagnostics) -> dict[str, Any]:
    base = dict(existing) if isinstance(existing, dict) else {}
    base.update(diag.to_dict())
    return base
