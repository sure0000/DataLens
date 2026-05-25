"""Copilot 路由共享类型（避免 context_builder ↔ routing_bundle 循环依赖）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoutingSearchBundle:
    question: str
    kb_ids: list[int] = field(default_factory=list)
    unified_hits_by_kb: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    merged_hits: dict[str, dict[str, Any]] = field(default_factory=dict)
    metric_term_text: str = ""
    metric_bound_table_ids: set[int] = field(default_factory=set)
    metric_table_bonuses: dict[int, float] = field(default_factory=dict)
    query_vector: list[float] | None = None
    embed_calls: int = 0
    kb_search_calls: int = 0
    domain_tables: list[Any] = field(default_factory=list)


@dataclass
class CopilotRoutingTrace:
    """P2-3 路由可观测性：写入 pipeline_trace / API 响应。"""

    routing_mode: str = ""
    candidate_table_count: int = 0
    candidate_table_ids: list[int] = field(default_factory=list)
    candidate_sources: dict[str, list[str]] = field(default_factory=dict)
    fallback_reason: str = ""
    top_table_scores: list[dict[str, Any]] = field(default_factory=list)
    domain_suggestion: dict[str, Any] | None = None
    auto_domain_applied: bool = False
    embed_calls: int = 0
    kb_search_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing_mode": self.routing_mode,
            "candidate_table_count": self.candidate_table_count,
            "candidate_table_ids": self.candidate_table_ids,
            "candidate_sources": self.candidate_sources,
            "fallback_reason": self.fallback_reason,
            "top_table_scores": self.top_table_scores,
            "domain_suggestion": self.domain_suggestion,
            "auto_domain_applied": self.auto_domain_applied,
            "embed_calls": self.embed_calls,
            "kb_search_calls": self.kb_search_calls,
        }
