"""Copilot 路由检索 bundle：单次 embed + 每 KB 一次 hybrid 查询（P1-4）。"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from services.embedding_service import _embed
from services.retrieval_service import search_kb_hybrid_unified
from services.routing.metric_router import search_metrics_and_terms
from services.routing_types import RoutingSearchBundle


def _merge_hit_key(hit: dict[str, Any]) -> str:
    if hit.get("source_type") == "entry":
        return f"entry:{int(hit['entry_id'])}"
    return f"chunk:{int(hit['chunk_id'])}"


async def build_routing_search_bundle(
    db: Session,
    question: str,
    business_domain_id: int | None,
    table_id: int | None,
    *,
    kb_top_k_table_route: int = 8,
    kb_top_k_knowledge: int = 6,
    load_metric_terms: bool = True,
    ontology_signal: str = "weak",
) -> RoutingSearchBundle:
    """构建共享路由 bundle；表路由与知识上下文共用同一份 KB 检索结果。

    ontology_signal 调节检索强度：
      - "rich": 本体已命中 ≥3 张表且有指标定义，KB hybrid 仅做轻量确认 (top_k=2)
      - "moderate": 本体命中 1-2 张表 (top_k=4)
      - "weak": 本体未命中，全量检索 (top_k=max(8,6))
    """
    from services.context_builder import kb_ids_for_business_domain, tables_from_business_domain

    q = (question or "").strip()
    bundle = RoutingSearchBundle(question=q)

    # Signal-gated retrieval intensity
    if ontology_signal == "rich":
        _kt = 2
    elif ontology_signal == "moderate":
        _kt = 4
    else:
        _kt = max(kb_top_k_table_route, kb_top_k_knowledge)
    bundle._ontology_signal = ontology_signal

    kb_ids: list[int] = []
    if business_domain_id:
        kb_ids = kb_ids_for_business_domain(db, business_domain_id)
        bundle.domain_tables = tables_from_business_domain(db, business_domain_id)
    bundle.kb_ids = kb_ids

    if q:
        bundle.query_vector = (await asyncio.to_thread(_embed, [q]))[0]
        bundle.embed_calls = 1

    top_k = _kt
    for kb_id in kb_ids:
        if not q:
            continue
        hits = search_kb_hybrid_unified(db, kb_id, q, top_k=top_k)
        bundle.kb_search_calls += 1
        bundle.unified_hits_by_kb[kb_id] = hits
        for hit in hits:
            bundle.merged_hits.setdefault(_merge_hit_key(hit), hit)

    if load_metric_terms and q and kb_ids and business_domain_id:
        bundle.metric_term_text, bundle.metric_bound_table_ids, bundle.metric_table_bonuses = (
            search_metrics_and_terms(
                db,
                q,
                kb_ids,
                bundle.domain_tables,
                query_vector=bundle.query_vector,
                embed_texts=_embed,
            )
        )
        # Ontology SPARQL supplement
        from config import get_settings
        from services.routing.ontology_router import search_ontology_metrics_and_terms

        if get_settings().ontology_enabled:
            onto_text, onto_tables, onto_bonuses = search_ontology_metrics_and_terms(
                db, q, kb_ids, query_vector=bundle.query_vector
            )
            if onto_text:
                bundle.metric_term_text = (bundle.metric_term_text + "\n" + onto_text).strip()
            bundle.metric_bound_table_ids |= onto_tables
            for tid, bonus in onto_bonuses.items():
                bundle.metric_table_bonuses[tid] = bundle.metric_table_bonuses.get(tid, 0) + bonus

    return bundle
