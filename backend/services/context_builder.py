"""Copilot 上下文组装：业务域定位、表选取、知识聚合、优先级上下文构建。"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import get_settings
from models import (
    BusinessDomain,
    BusinessDomainDescription,
    BusinessDomainKnowledgeBase,
    BusinessDomainSelection,
    ColumnMeta,
    DataSource,
    KnowledgeBase,
    KnowledgeEntry,
    TableKnowledgeBase,
    TableKnowledgeEntry,
    TableMeta,
    TableSummary,
)
from services.embedding_service import search_column_embeddings, search_table_embeddings, search_table_embeddings_global
from services.routing.graph_router import apply_graph_expansion
from services.routing_types import CopilotRoutingTrace, RoutingSearchBundle
from services.semantic_grounding import match_tables_from_grounding

_DIMENSION_SEMANTIC_TYPES = frozenset({"dimension", "enum", "category", "code"})

_SHORT_TABLE_NAME_LEN = 6


def latest_table_summaries(db: Session) -> dict[int, TableSummary]:
    subq = (
        select(
            TableSummary.table_id.label("tid"),
            func.max(TableSummary.generated_at).label("max_at"),
        )
        .group_by(TableSummary.table_id)
        .subquery()
    )
    stmt = (
        select(TableSummary)
        .join(subq, TableSummary.table_id == subq.c.tid)
        .where(TableSummary.generated_at == subq.c.max_at)
    )
    rows = db.execute(stmt).scalars().all()
    return {row.table_id: row for row in rows}


def tables_from_business_domain(db: Session, domain_id: int) -> list[TableMeta]:
    selections = db.execute(
        select(BusinessDomainSelection).where(BusinessDomainSelection.domain_id == domain_id)
    ).scalars().all()
    by_id: dict[int, TableMeta] = {}
    for sel in selections:
        ds_id = sel.datasource_id
        db_name = (sel.database_name or "").strip()
        if not db_name:
            continue
        raw_tn = sel.table_name
        tn = (raw_tn or "").strip() if raw_tn is not None else ""
        if not tn:
            rows = db.execute(
                select(TableMeta).where(TableMeta.datasource_id == ds_id, TableMeta.database_name == db_name)
            ).scalars().all()
            if not rows:
                rows = db.execute(
                    select(TableMeta).where(
                        TableMeta.datasource_id == ds_id,
                        func.lower(TableMeta.database_name) == db_name.lower(),
                    )
                ).scalars().all()
        else:
            rows = db.execute(
                select(TableMeta).where(
                    TableMeta.datasource_id == ds_id,
                    TableMeta.database_name == db_name,
                    TableMeta.table_name == tn,
                )
            ).scalars().all()
            if not rows:
                rows = db.execute(
                    select(TableMeta).where(
                        TableMeta.datasource_id == ds_id,
                        func.lower(TableMeta.database_name) == db_name.lower(),
                        func.lower(TableMeta.table_name) == tn.lower(),
                    )
                ).scalars().all()
        for t in rows:
            by_id[t.id] = t
    return sorted(by_id.values(), key=lambda t: (t.datasource_id or 0, (t.database_name or ""), (t.table_name or "")))


def kb_ids_for_business_domain(db: Session, business_domain_id: int) -> list[int]:
    """Return KB ids bound to a business domain.

    Supports both explicit M:N links (``business_domain_knowledge_bases``) and KBs
    owned via ``knowledge_bases.business_domain_id`` (current create/list API path).
    """
    out: list[int] = []
    seen: set[int] = set()

    def add(kid: int) -> None:
        if kid in seen:
            return
        seen.add(kid)
        out.append(kid)

    for kid in db.execute(
        select(BusinessDomainKnowledgeBase.knowledge_base_id).where(
            BusinessDomainKnowledgeBase.domain_id == business_domain_id
        )
    ).scalars().all():
        add(int(kid))

    for kid in db.execute(
        select(KnowledgeBase.id)
        .where(KnowledgeBase.business_domain_id == business_domain_id)
        .order_by(KnowledgeBase.id.asc())
    ).scalars().all():
        add(int(kid))

    return out


def _blob_tokens(blob: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", blob.lower()))


def _fq_table_name_in_blob(db_name: str, table_name: str, blob_lower: str) -> bool:
    fq = f"{(db_name or '').strip()}.{(table_name or '').strip()}".lower()
    if not fq or fq == ".":
        return False
    pattern = r"(?:^|(?<![\w\u4e00-\u9fff]))" + re.escape(fq) + r"(?:$|(?![\w\u4e00-\u9fff]))"
    return bool(re.search(pattern, blob_lower))


def match_tables_by_name_in_blob(
    domain_tables: list[TableMeta],
    blob: str,
    *,
    already_matched: set[int],
    allowed: set[int],
) -> list[int]:
    """知识正文表名锚定：优先全名词边界匹配；短表名不单独锚定。"""
    blob_lower = blob.lower()
    tokens = _blob_tokens(blob)
    matched: list[int] = []

    for t in domain_tables:
        if t.id in already_matched or t.id not in allowed:
            continue
        tn = (t.table_name or "").strip()
        if not tn:
            continue
        if _fq_table_name_in_blob(t.database_name or "", tn, blob_lower):
            matched.append(t.id)

    for t in domain_tables:
        if t.id in already_matched or t.id in matched or t.id not in allowed:
            continue
        tn = (t.table_name or "").strip()
        if len(tn) < _SHORT_TABLE_NAME_LEN:
            continue
        if tn.lower() in tokens:
            matched.append(t.id)

    return matched


def _knowledge_hit_blob(hit: dict[str, Any]) -> str:
    return f"{hit.get('title') or ''} {hit.get('summary') or ''} {hit.get('snippet') or ''}"


def candidate_table_ids_from_domain_knowledge(
    db: Session,
    question: str,
    business_domain_id: int,
    domain_tables: list[TableMeta],
    *,
    top_k_per_kb: int = 8,
    merged_hits: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[int], dict[int, set[str]]]:
    """域内知识混合检索间接锚表；返回有序 table_id 与各表信号来源。"""
    allowed = {t.id for t in domain_tables}
    if not allowed or not (question or "").strip():
        return [], {}

    hits_map = merged_hits
    if hits_map is None:
        kb_ids = kb_ids_for_business_domain(db, business_domain_id)
        if not kb_ids:
            return [], {}
        from services.retrieval_service import search_kb_hybrid_unified

        hits_map = {}
        for kb_id in kb_ids:
            for hit in search_kb_hybrid_unified(db, kb_id, question.strip(), top_k=top_k_per_kb):
                if hit.get("source_type") == "entry":
                    key = f"entry:{int(hit['entry_id'])}"
                else:
                    key = f"chunk:{int(hit['chunk_id'])}"
                hits_map.setdefault(key, hit)
    elif not hits_map:
        return [], {}

    candidate: list[int] = []
    sources: dict[int, set[str]] = {}
    seen_tid: set[int] = set()

    for key, hit in hits_map.items():
        if not key.startswith("entry:"):
            continue
        eid = int(key.split(":", 1)[1])
        for tid in db.execute(
            select(TableKnowledgeEntry.table_id).where(TableKnowledgeEntry.knowledge_entry_id == eid)
        ).scalars().all():
            tid = int(tid)
            if tid in allowed and tid not in seen_tid:
                seen_tid.add(tid)
                candidate.append(tid)
                sources.setdefault(tid, set()).add("explicit_link")
                sources[tid].add("knowledge")

    for hit in hits_map.values():
        grounding = hit.get("semantic_meta", {}).get("grounding") if isinstance(hit.get("semantic_meta"), dict) else None
        if grounding:
            for tid in match_tables_from_grounding(
                domain_tables,
                grounding,
                already_matched=seen_tid,
                allowed=allowed,
            ):
                seen_tid.add(tid)
                candidate.append(tid)
                sources.setdefault(tid, set()).add("semantic_grounding")
                if hit.get("source_type") == "chunk":
                    sources[tid].add("document_chunk")
                else:
                    sources[tid].add("knowledge")

    for hit in hits_map.values():
        blob = _knowledge_hit_blob(hit)
        for tid in match_tables_by_name_in_blob(
            domain_tables, blob, already_matched=seen_tid, allowed=allowed
        ):
            seen_tid.add(tid)
            candidate.append(tid)
            sources.setdefault(tid, set()).add("knowledge")
            if hit.get("source_type") == "chunk":
                sources[tid].add("document_chunk")

    return candidate, sources


def candidate_table_ids_from_table_embeddings(
    db: Session,
    question: str,
    allowed_table_ids: set[int] | list[int],
    top_k: int,
    *,
    query_vector: list[float] | None = None,
) -> list[tuple[int, float]]:
    """域内表摘要向量直搜，返回 (table_id, cosine_distance) 排名。"""
    return search_table_embeddings(
        db, question, allowed_table_ids, top_k=top_k, query_vector=query_vector
    )


def _tables_with_dimension_semantics(db: Session, table_ids: set[int]) -> set[int]:
    if not table_ids:
        return set()
    dim_tables: set[int] = set()
    for tid in table_ids:
        cols = db.execute(select(ColumnMeta.semantic_type).where(ColumnMeta.table_id == tid)).scalars().all()
        for st in cols:
            if (st or "").strip().lower() in _DIMENSION_SEMANTIC_TYPES:
                dim_tables.add(tid)
                break
    return dim_tables


def apply_column_dimension_expansion(
    db: Session,
    question: str,
    allowed_table_ids: set[int],
    scores: dict[int, float],
    sources: dict[int, set[str]],
    *,
    primary_table_id: int | None,
    query_vector: list[float] | None,
    top_k: int,
    weight: float,
    rrf_k: int,
) -> tuple[dict[int, float], dict[int, set[str]]]:
    """主表确定后，按列向量扩展维表/码表候选（权重低于主表）。"""
    if top_k <= 0 or not allowed_table_ids:
        return scores, sources
    exclude = {primary_table_id} if primary_table_id else set()
    col_hits = search_column_embeddings(
        db,
        question,
        allowed_table_ids,
        top_k=top_k + len(exclude),
        query_vector=query_vector,
    )
    dim_ok = _tables_with_dimension_semantics(db, allowed_table_ids)
    added = 0
    rank = 0
    for tid, _dist in col_hits:
        if tid in scores or tid in exclude or tid not in dim_ok:
            continue
        scores[tid] = scores.get(tid, 0.0) + weight / (rrf_k + rank + 1)
        sources.setdefault(tid, set()).add("column_embedding")
        rank += 1
        added += 1
        if added >= top_k:
            break
    return scores, sources


def compute_domain_table_scores(
    knowledge_ordered: list[int],
    knowledge_sources: dict[int, set[str]],
    embedding_hits: list[tuple[int, float]],
    *,
    weight_knowledge: float,
    weight_table_emb: float,
    explicit_link_bonus: float,
    rrf_k: int,
    metric_bound_bonus: dict[int, float] | None = None,
) -> tuple[dict[int, float], dict[int, set[str]]]:
    """综合分：w1·知识RRF + w2·表向量RRF + w3·显式链接加成。"""
    combined_sources: dict[int, set[str]] = {
        tid: set(src) for tid, src in knowledge_sources.items()
    }
    for tid, _dist in embedding_hits:
        combined_sources.setdefault(tid, set()).add("table_embedding")

    scores: dict[int, float] = {}
    for rank, tid in enumerate(knowledge_ordered):
        scores[tid] = scores.get(tid, 0.0) + weight_knowledge / (rrf_k + rank + 1)
    for rank, (tid, _dist) in enumerate(embedding_hits):
        scores[tid] = scores.get(tid, 0.0) + weight_table_emb / (rrf_k + rank + 1)
    for tid, src in knowledge_sources.items():
        if "explicit_link" in src:
            scores[tid] = scores.get(tid, 0.0) + explicit_link_bonus
    for tid, bonus in (metric_bound_bonus or {}).items():
        scores[tid] = scores.get(tid, 0.0) + bonus
        combined_sources.setdefault(tid, set()).add("metric_term")
    return scores, combined_sources


def select_candidates_with_gradient_fallback(
    scores: dict[int, float],
    sources: dict[int, set[str]],
    *,
    max_candidates: int,
    max_candidates_expanded: int,
    min_score: float,
    min_score_relaxed: float,
) -> tuple[list[int], dict[int, list[str]], str]:
    """梯度 fallback：高置信 top_k → 放宽阈值扩大 top_k → 域内全表。"""
    if not scores:
        return [], {}, "no_semantic_signals"

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))

    def pick(min_s: float, limit: int) -> list[int]:
        return [tid for tid, s in ranked if s >= min_s][:limit]

    ids = pick(min_score, max_candidates)
    if ids:
        return ids, {tid: sorted(sources.get(tid, set())) for tid in ids}, ""

    ids = pick(min_score_relaxed, max_candidates_expanded)
    if ids:
        return ids, {tid: sorted(sources.get(tid, set())) for tid in ids}, "low_confidence_expanded_top_k"

    return [], {}, "scores_below_threshold_domain_full"


def _aggregate_candidate_sources(sources: dict[int, set[str]]) -> dict[str, list[str]]:
    """按信号来源聚合表 id 列表，便于统计。"""
    agg: dict[str, list[str]] = {}
    for tid, srcs in sources.items():
        for s in srcs:
            agg.setdefault(s, []).append(str(tid))
    return agg


def _build_top_table_scores(
    scores: dict[int, float],
    sources: dict[int, set[str]],
    tables_by_id: dict[int, TableMeta],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:limit]
    out: list[dict[str, Any]] = []
    for tid, score in ranked:
        t = tables_by_id.get(tid)
        fq = f"{t.database_name}.{t.table_name}" if t else f"table_id={tid}"
        out.append(
            {
                "table_id": tid,
                "fq_name": fq,
                "score": round(score, 5),
                "sources": sorted(sources.get(tid, set())),
            }
        )
    return out


def merge_domain_candidate_table_ids(
    knowledge_ordered: list[int],
    knowledge_sources: dict[int, set[str]],
    embedding_hits: list[tuple[int, float]],
    *,
    max_candidates: int,
) -> tuple[list[int], dict[int, list[str]]]:
    """兼容旧接口：按默认权重打分并取 top_k（不含梯度 fallback）。"""
    settings = get_settings()
    scores, combined = compute_domain_table_scores(
        knowledge_ordered,
        knowledge_sources,
        embedding_hits,
        weight_knowledge=settings.copilot_routing_weight_knowledge,
        weight_table_emb=settings.copilot_routing_weight_table_emb,
        explicit_link_bonus=settings.copilot_routing_explicit_link_bonus,
        rrf_k=settings.rrf_k,
    )
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:max_candidates]
    ids = [tid for tid, _ in ranked]
    return ids, {tid: sorted(combined.get(tid, set())) for tid in ids}


def resolve_domain_candidate_tables(
    db: Session,
    question: str,
    business_domain_id: int,
    domain_tables: list[TableMeta],
    *,
    max_candidates: int,
    table_embed_top_k: int,
    routing_bundle: RoutingSearchBundle | None = None,
) -> tuple[list[int], dict[int, list[str]], str, dict[int, float]]:
    """域内候选表：知识路由 + 表向量直搜 + 列/血缘扩表，打分后梯度截断。"""
    q = (question or "").strip()
    if not q:
        return [], {}, "empty_question", {}

    settings = get_settings()
    allowed = {t.id for t in domain_tables}
    merged_hits = routing_bundle.merged_hits if routing_bundle else None
    query_vector = routing_bundle.query_vector if routing_bundle else None
    metric_bonus = routing_bundle.metric_table_bonuses if routing_bundle else None
    kb_ids = routing_bundle.kb_ids if routing_bundle else kb_ids_for_business_domain(db, business_domain_id)

    knowledge_ids, knowledge_sources = candidate_table_ids_from_domain_knowledge(
        db, q, business_domain_id, domain_tables, merged_hits=merged_hits
    )
    embedding_hits = candidate_table_ids_from_table_embeddings(
        db, q, allowed, table_embed_top_k, query_vector=query_vector
    )
    scores, combined_sources = compute_domain_table_scores(
        knowledge_ids,
        knowledge_sources,
        embedding_hits,
        weight_knowledge=settings.copilot_routing_weight_knowledge,
        weight_table_emb=settings.copilot_routing_weight_table_emb,
        explicit_link_bonus=settings.copilot_routing_explicit_link_bonus,
        rrf_k=settings.rrf_k,
        metric_bound_bonus=metric_bonus,
    )
    primary_tid = knowledge_ids[0] if knowledge_ids else (embedding_hits[0][0] if embedding_hits else None)
    scores, combined_sources = apply_column_dimension_expansion(
        db,
        q,
        allowed,
        scores,
        combined_sources,
        primary_table_id=primary_tid,
        query_vector=query_vector,
        top_k=settings.copilot_column_expand_top_k,
        weight=settings.copilot_routing_weight_column_expand,
        rrf_k=settings.rrf_k,
    )
    scores, combined_sources = apply_graph_expansion(
        db,
        kb_ids,
        domain_tables,
        primary_tid,
        scores,
        combined_sources,
        routing_bundle=routing_bundle,
    )
    ids, out_src, reason = select_candidates_with_gradient_fallback(
        scores,
        combined_sources,
        max_candidates=max_candidates,
        max_candidates_expanded=settings.copilot_max_candidate_tables_expanded,
        min_score=settings.copilot_routing_min_score,
        min_score_relaxed=settings.copilot_routing_min_score_relaxed,
    )
    return ids, out_src, reason, scores


def resolve_unscoped_candidate_tables(
    db: Session,
    question: str,
    *,
    max_candidates: int,
    table_embed_top_k: int,
    query_vector: list[float] | None = None,
) -> tuple[list[int], dict[int, list[str]], str]:
    """无域场景：全库表向量语义 top_k。"""
    q = (question or "").strip()
    if not q:
        return [], {}, "empty_question"

    settings = get_settings()
    embedding_hits = search_table_embeddings_global(
        db, q, top_k=table_embed_top_k, query_vector=query_vector
    )
    scores, combined_sources = compute_domain_table_scores(
        [],
        {},
        embedding_hits,
        weight_knowledge=settings.copilot_routing_weight_knowledge,
        weight_table_emb=settings.copilot_routing_weight_table_emb,
        explicit_link_bonus=settings.copilot_routing_explicit_link_bonus,
        rrf_k=settings.rrf_k,
    )
    ids, sources, reason = select_candidates_with_gradient_fallback(
        scores,
        combined_sources,
        max_candidates=max_candidates,
        max_candidates_expanded=max_candidates,
        min_score=settings.copilot_routing_min_score_relaxed,
        min_score_relaxed=settings.copilot_routing_min_score_relaxed / 2,
    )
    if ids:
        return ids, sources, reason or "unscoped_semantic_top_k"
    return [], {}, "unscoped_no_table_embedding_match"


def _format_candidate_sources_preview(
    tables: list[TableMeta], sources_map: dict[int, list[str]], *, limit: int = 10
) -> str:
    parts: list[str] = []
    for t in tables[:limit]:
        src = sources_map.get(t.id) or []
        src_label = "+".join(src) if src else "unknown"
        parts.append(f"{t.database_name}.{t.table_name}[{src_label}]")
    preview = "、".join(parts)
    if len(tables) > limit:
        preview += "…"
    return preview


def all_tables_for_copilot_fallback(
    db: Session, preferred_datasource_id: int | None, max_tables: int
) -> list[TableMeta]:
    table_rows = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().all()
    if preferred_datasource_id is not None:
        table_rows = [t for t in table_rows if t.datasource_id == preferred_datasource_id] + [
            t for t in table_rows if t.datasource_id != preferred_datasource_id
        ]
    seen_tables: set[tuple[int | None, str, str]] = set()
    selected_tables: list[TableMeta] = []
    for t in table_rows:
        key = (t.datasource_id, t.database_name, t.table_name)
        if key in seen_tables:
            continue
        seen_tables.add(key)
        selected_tables.append(t)
        if len(selected_tables) >= max_tables:
            break
    return selected_tables


def resolve_table_meta_for_trace(
    db: Session,
    *,
    datasource_id: int,
    default_database: str | None,
    db_part: str | None,
    table_name: str,
) -> TableMeta | None:
    schema = ((db_part or "").strip() or (default_database or "").strip()) or ""
    tbl = (table_name or "").strip()
    if not datasource_id or not schema or not tbl:
        return None
    row = db.execute(
        select(TableMeta)
        .where(
            TableMeta.datasource_id == datasource_id,
            TableMeta.database_name == schema,
            TableMeta.table_name == tbl,
        )
        .limit(1)
    ).scalars().first()
    if row:
        return row
    return db.execute(
        select(TableMeta)
        .where(
            TableMeta.datasource_id == datasource_id,
            func.lower(TableMeta.database_name) == schema.lower(),
            func.lower(TableMeta.table_name) == tbl.lower(),
        )
        .limit(1)
    ).scalars().first()


def reasoning3_basis_chain(
    db: Session,
    *,
    business_domain_id: int | None,
    tm: TableMeta | None,
    table_narrative: str,
    datasource_fallback: DataSource | None = None,
    database_name_fallback: str | None = None,
) -> str:
    parts: list[str] = []
    if business_domain_id:
        dom = db.get(BusinessDomain, business_domain_id)
        if dom:
            parts.append(f"业务域：会话绑定「{dom.name}」（id={dom.id}），用于关联知识库与域内表策略上下文。")
        else:
            parts.append(f"业务域：请求携带 domain_id={business_domain_id}，元数据中未找到对应业务域。")
    else:
        parts.append("业务域：未选择业务域，本链路未经过域级知识库路由。")

    if tm and tm.datasource_id:
        ds = db.get(DataSource, tm.datasource_id)
        if ds:
            dname = (ds.name or "").strip() or f"id={ds.id}"
            parts.append(f"数据库：数据源「{dname}」（类型 {ds.source_type}），逻辑库/命名空间为「{tm.database_name}」。")
        else:
            parts.append(f"数据库：表记录关联 datasource_id={tm.datasource_id}，但未检索到数据源实体。")
    elif datasource_fallback:
        dname = (datasource_fallback.name or "").strip() or f"id={datasource_fallback.id}"
        ns = (database_name_fallback or "").strip() or (datasource_fallback.database or "") or "默认"
        parts.append(f"数据库：当前解析锚定数据源「{dname}」（类型 {datasource_fallback.source_type}），命名空间「{ns}」。")
    elif tm:
        parts.append("数据库：表元数据缺少 datasource_id，无法下钻到连接配置。")
    else:
        parts.append("数据库：无表元数据锚点，无法解析到具体数据源与库名。")

    if tm:
        fq = f"{tm.database_name}.{tm.table_name}"
        parts.append(f"数据表：元数据登记「{fq}」（table_id={tm.id}）。{table_narrative}")
    else:
        parts.append(f"数据表：{table_narrative}")

    return "‖".join(parts)


def build_domain_context_block(db: Session, business_domain_id: int | None) -> str:
    if not business_domain_id:
        return ""
    dom = db.get(BusinessDomain, business_domain_id)
    if not dom:
        return ""
    dom_desc_row = (
        db.execute(
            select(BusinessDomainDescription)
            .where(BusinessDomainDescription.domain_id == business_domain_id)
            .order_by(BusinessDomainDescription.created_at.desc())
        )
        .scalars()
        .first()
    )
    dom_desc = (dom_desc_row.content or "").strip() if dom_desc_row else ""
    dom_block = f"## DOMAIN CONTEXT — 当前业务域「{dom.name}」"
    if dom_desc:
        dom_block += f"\n{dom_desc}"
    dom_block += "\n（以上为该业务域的全局语义约束与分析惯例，生成 SQL 和解释时必须优先遵守）"
    return dom_block


def build_priority_context(
    db: Session,
    table_id: int | None,
    business_domain_id: int | None = None,
    question: str | None = None,
    routing_bundle: RoutingSearchBundle | None = None,
    routing_trace: CopilotRoutingTrace | None = None,
) -> tuple[str, str, str, int | None, str, CopilotRoutingTrace]:
    settings = get_settings()
    max_unscoped = settings.copilot_max_tables_without_domain
    trace = routing_trace or CopilotRoutingTrace()
    if routing_bundle:
        trace.embed_calls = routing_bundle.embed_calls
        trace.kb_search_calls = routing_bundle.kb_search_calls

    latest_summaries = latest_table_summaries(db)
    preferred_table = db.get(TableMeta, table_id) if table_id else None
    preferred_datasource_id = preferred_table.datasource_id if preferred_table else None

    domain_header = ""
    table_scope_note = ""
    selected_tables: list[TableMeta] = []
    final_scores: dict[int, float] = {}
    cand_sources: dict[int, list[str]] = {}
    fallback_reason = ""
    routing_mode = "global_fallback"

    if table_id and preferred_table:
        selected_tables = [preferred_table]
        routing_mode = "locked_table"
        table_scope_note = (
            f"表定位：会话锁定单表 table_id={preferred_table.id}（{preferred_table.database_name}.{preferred_table.table_name}）。"
        )

    if not selected_tables and business_domain_id:
        domain_rows = tables_from_business_domain(db, business_domain_id)
        dom = db.get(BusinessDomain, business_domain_id)
        dom_label = (dom.name.strip() if dom and (dom.name or "").strip() else f"id={business_domain_id}")
        if domain_rows:
            q = (question or "").strip()
            cand_ids: list[int] = []
            cand_sources = {}
            fallback_reason = ""
            final_scores = {}
            if q:
                cand_ids, cand_sources, fallback_reason, final_scores = resolve_domain_candidate_tables(
                    db,
                    q,
                    business_domain_id,
                    domain_rows,
                    max_candidates=settings.copilot_max_candidate_tables,
                    table_embed_top_k=settings.copilot_table_embed_top_k,
                    routing_bundle=routing_bundle,
                )
            allowed_ids = {t.id for t in domain_rows}
            narrowed_metas: list[TableMeta] = []
            for tid in cand_ids:
                if tid not in allowed_ids:
                    continue
                tm = db.get(TableMeta, tid)
                if tm is not None:
                    narrowed_metas.append(tm)
            if narrowed_metas:
                selected_tables = narrowed_metas
                routing_mode = "domain_narrowed"
                preview = _format_candidate_sources_preview(narrowed_metas, cand_sources)
                conf_label = "高置信" if not fallback_reason else "中置信"
                domain_header = (
                    f"[业务域候选表 — 知识检索+表向量融合/{conf_label}] 会话绑定业务域「{dom_label}」（domain_id={business_domain_id}）。"
                    "已在业务域关联知识库中按用户问题做语义检索，并结合表摘要向量直搜、条目与表的显式关联及知识正文中的表名提及，"
                    f"得到下列 {len(narrowed_metas)} 张候选表的元数据与列语义；请先结合上方业务域知识理解业务，再于候选集合中确认最终使用的表并生成只读 SQL。\n\n"
                )
                table_scope_note = (
                    f"表定位（业务域）：知识+表向量融合筛得 {len(narrowed_metas)} 张候选表：{preview}。"
                )
                if fallback_reason:
                    table_scope_note += f" fallback_reason={fallback_reason}。"
            else:
                selected_tables = domain_rows
                routing_mode = "domain_full"
                fb = fallback_reason or "no_semantic_match_domain_full"
                domain_header = (
                    f"[业务域候选表 — 语义路由未缩窄] 会话绑定业务域「{dom_label}」（domain_id={business_domain_id}）。"
                    "知识/表向量均未达置信阈值或未产生有效信号，已加载本域挂载的全部"
                    f" {len(domain_rows)} 张已登记表元数据；请结合业务域知识后再确认表与 SQL。\n\n"
                )
                table_scope_note = (
                    f"表定位（业务域）：语义路由未缩窄，已加载域内全部 {len(domain_rows)} 张挂载表。"
                    f" fallback_reason={fb}。"
                )
                fallback_reason = fb
        else:
            selected_tables = all_tables_for_copilot_fallback(db, preferred_datasource_id, max_unscoped)
            routing_mode = "global_fallback"
            fallback_reason = "domain_has_no_mounted_tables"
            domain_header = (
                f"[提示] 业务域「{dom_label}」（domain_id={business_domain_id}）下暂无已解析的挂载表，或域不存在；"
                f"已退化为全局最近登记的数据表（至多 {max_unscoped} 张）。\n\n"
            )

    if not selected_tables:
        q = (question or "").strip()
        if not business_domain_id and q:
            unscoped_ids, unscoped_sources, unscoped_fb = resolve_unscoped_candidate_tables(
                db,
                q,
                max_candidates=max_unscoped,
                table_embed_top_k=settings.copilot_table_embed_top_k,
                query_vector=routing_bundle.query_vector if routing_bundle else None,
            )
            unscoped_metas: list[TableMeta] = []
            for tid in unscoped_ids:
                tm = db.get(TableMeta, tid)
                if tm is not None:
                    unscoped_metas.append(tm)
            if unscoped_metas:
                selected_tables = unscoped_metas
                routing_mode = "global_semantic"
                preview = _format_candidate_sources_preview(unscoped_metas, unscoped_sources)
                domain_header = (
                    f"[无域语义路由] 未指定业务域；按问题对全库表摘要向量检索，"
                    f"筛得 {len(unscoped_metas)} 张候选表（上限 {max_unscoped}）。\n\n"
                )
                table_scope_note = (
                    f"表定位（无域）：表向量语义筛得 {len(unscoped_metas)} 张候选表：{preview}。"
                )
                if unscoped_fb:
                    table_scope_note += f" fallback_reason={unscoped_fb}。"
                fallback_reason = unscoped_fb
                cand_sources = unscoped_sources
            else:
                selected_tables = all_tables_for_copilot_fallback(db, preferred_datasource_id, max_unscoped)
                routing_mode = "global_fallback"
                fb = unscoped_fb or "unscoped_recent_tables_fallback"
                fallback_reason = fb
                domain_header = (
                    f"[提示] 未指定业务域；表向量未筛中，已退化为最近登记的 {len(selected_tables)} 张表"
                    f"（上限 {max_unscoped}）。建议在 Copilot 中选择业务域。\n\n"
                )
                table_scope_note = f"表定位（无域）：语义未命中，已加载最近 {len(selected_tables)} 张表。 fallback_reason={fb}。"
        else:
            selected_tables = all_tables_for_copilot_fallback(db, preferred_datasource_id, max_unscoped)
            routing_mode = "global_fallback"
            if not business_domain_id and len(selected_tables) >= max_unscoped:
                domain_header = (
                    f"[提示] 未指定业务域；全局已登记表较多，当前上下文仅含最近 {max_unscoped} 张表。"
                    "建议在 Copilot 中选择业务域以加载该域内全部挂载表。\n\n"
                )

    datasource_ids = [t.datasource_id for t in selected_tables if t.datasource_id is not None]
    datasource_ids_unique = list(dict.fromkeys(datasource_ids))
    datasources = (
        db.execute(select(DataSource).where(DataSource.id.in_(datasource_ids_unique))).scalars().all()
        if datasource_ids_unique
        else []
    )
    context_lines = ["[优先上下文-数据源采集信息]"]
    if preferred_table:
        context_lines.append(
            f"当前指定表: {preferred_table.database_name}.{preferred_table.table_name} (table_id={preferred_table.id})"
        )
    for d in datasources:
        context_lines.append(
            f"- 数据源[{d.id}] {d.name} ({d.source_type}) 数据库={d.database} | 备注: {d.description or '无'}"
        )

    analysis_lines = ["[优先上下文-AI分析信息]"]
    merged_summary_parts: list[str] = []
    onto_table_ids = routing_bundle.metric_bound_table_ids if routing_bundle else set()
    for t in selected_tables:
        summary = latest_summaries.get(t.id)
        use_cases = summary.use_cases if summary and summary.use_cases else ""
        key_cols = summary.key_columns if summary and summary.key_columns else ""
        tag = " [本体]" if t.id in onto_table_ids else ""
        table_line = f"- {t.database_name}.{t.table_name} 状态={t.status}{tag}"
        if summary and summary.summary:
            table_line += f" | 摘要={summary.summary}"
            merged_summary_parts.append(summary.summary)
        if use_cases:
            table_line += f" | 场景={use_cases}"
        if key_cols:
            table_line += f" | 关键字段={key_cols}"
        analysis_lines.append(table_line)

    selected_table_ids = [t.id for t in selected_tables]
    if table_id:
        selected_table_ids = [table_id]
    cols = (
        db.execute(select(ColumnMeta).where(ColumnMeta.table_id.in_(selected_table_ids))).scalars().all()
        if selected_table_ids
        else []
    )
    schema_lines = []
    for c in cols:
        qm = c.quality_metrics if isinstance(c.quality_metrics, dict) else {}
        em = qm.get("enum") if isinstance(qm, dict) else None
        agg_hint = qm.get("aggregation_hint", "") if isinstance(qm, dict) else ""
        enum_tail = ""
        if isinstance(em, dict):
            vals = em.get("values")
            if isinstance(vals, list) and vals:
                joined = ",".join(str(v) for v in vals[:32])
                if len(vals) > 32:
                    joined += ",…"
                enum_tail = f" | enum_values={joined}"
        agg_tail = f" | aggregation={agg_hint}" if agg_hint else ""
        schema_lines.append(
            f"{c.table_id}.{c.column_name} | {c.data_type or ''} | semantic={c.semantic_type or ''} | desc={c.semantic_desc or ''}{enum_tail}{agg_tail}"
        )

    context_text = domain_header + "\n".join(context_lines)
    if onto_table_ids:
        onto_names = [f"{t.database_name}.{t.table_name}" for t in selected_tables if t.id in onto_table_ids]
        if onto_names:
            analysis_lines.append(f"\n本体映射推荐：下列表与用户问题中的业务概念直接对应，对比/环比查询必须优先使用：{'，'.join(onto_names)}")
    analysis_text = "\n".join(analysis_lines)
    schema_text = "\n".join(schema_lines)
    summary_text = "；".join(merged_summary_parts[:6])

    resolved_table_id = table_id
    if resolved_table_id is None and preferred_table:
        resolved_table_id = preferred_table.id
    if resolved_table_id is None and selected_tables:
        resolved_table_id = selected_tables[0].id

    tables_by_id = {t.id: t for t in selected_tables}
    trace.routing_mode = routing_mode
    trace.candidate_table_count = len(selected_tables)
    trace.candidate_table_ids = [t.id for t in selected_tables]
    trace.candidate_sources = _aggregate_candidate_sources(
        {tid: set(src) for tid, src in cand_sources.items()}
        if cand_sources
        else {t.id: {"locked_table"} if table_id else set() for t in selected_tables}
    )
    trace.fallback_reason = fallback_reason
    if final_scores:
        trace.top_table_scores = _build_top_table_scores(final_scores, {k: set(v) for k, v in cand_sources.items()}, tables_by_id)
        for row in trace.top_table_scores:
            sources = row.get("sources") or []
            if "ontology_graph" in sources:
                trace.ontology_trace.append({
                    "type": "table",
                    "iri": f"https://datalens.local/data/table/{row.get('table_id')}",
                    "label": row.get("fq_name"),
                    "source": "ontology_graph",
                })
    elif table_id and preferred_table:
        trace.top_table_scores = [{"table_id": preferred_table.id, "fq_name": f"{preferred_table.database_name}.{preferred_table.table_name}", "score": 1.0, "sources": ["locked_table"]}]

    return context_text + "\n" + analysis_text, schema_text, summary_text, resolved_table_id, table_scope_note, trace


def collect_knowledge_context_text(
    db: Session,
    question: str,
    business_domain_id: int | None,
    table_id: int | None,
    routing_bundle: RoutingSearchBundle | None = None,
) -> str:
    kb_ids: list[int] = []
    seen_kb: set[int] = set()

    def add_kb(kid: int) -> None:
        if kid in seen_kb:
            return
        seen_kb.add(kid)
        kb_ids.append(kid)

    if business_domain_id:
        for kid in kb_ids_for_business_domain(db, business_domain_id):
            add_kb(kid)

    pinned_ids: list[int] = []
    seen_ent: set[int] = set()
    if table_id:
        for kid in db.execute(
            select(TableKnowledgeBase.knowledge_base_id).where(TableKnowledgeBase.table_id == table_id)
        ).scalars().all():
            add_kb(int(kid))
        for eid in db.execute(
            select(TableKnowledgeEntry.knowledge_entry_id).where(TableKnowledgeEntry.table_id == table_id)
        ).scalars().all():
            eid = int(eid)
            if eid in seen_ent:
                continue
            seen_ent.add(eid)
            pinned_ids.append(eid)

    sections: list[str] = []
    max_total_chars = 120000
    pinned_set = set(pinned_ids)

    if routing_bundle and routing_bundle.metric_term_text.strip():
        sections.append(routing_bundle.metric_term_text.strip())

    if pinned_ids:
        entries = list(db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(pinned_ids))).scalars().all())
        entry_by_id = {e.id: e for e in entries}
        reserve_for_semantics = min(52000, max(16000, max_total_chars // 3))
        pin_budget = max(12000, max_total_chars - reserve_for_semantics - 900)
        per_pin_cap = min(96000, max(6144, pin_budget // len(pinned_ids)))
        pin_lines = ["[表关联知识条目 — 固定全文]"]
        for eid in pinned_ids:
            e = entry_by_id.get(eid)
            if not e:
                continue
            kb = db.get(KnowledgeBase, e.knowledge_base_id)
            kb_name = kb.name if kb else "?"
            summary = ((e.summary or "").strip()).replace("\r\n", "\n")
            body = ((e.body or "").strip()).replace("\r\n", "\n")
            preamble = ""
            if summary:
                preamble = f"简述：{summary}\n\n"
            room = max(512, per_pin_cap - len(preamble) - len(e.title))
            plain_body = body
            if len(plain_body) > room:
                plain_body = plain_body[: max(256, room)] + "\n…（以上为模型上下文中的截断；知识库条目内仍可查看完整正文。）"
            pin_lines.append(f"## {e.title}（知识库：{kb_name}，entry_id={e.id}）\n{preamble}{plain_body}")
        sections.append("\n".join(pin_lines))

    if kb_ids and question.strip():
        sem_lines = ["[知识库语义检索 — 与问题相关的片段（条目 + 文档分块）]"]
        merged_hits: dict[str, dict[str, Any]] = {}
        if routing_bundle and routing_bundle.merged_hits:
            for key, hit in routing_bundle.merged_hits.items():
                if key.startswith("entry:"):
                    eid = int(key.split(":", 1)[1])
                    if eid in pinned_set:
                        continue
                merged_hits.setdefault(key, hit)
        else:
            from services.retrieval_service import search_kb_hybrid_unified

            for kb_id in kb_ids:
                for hit in search_kb_hybrid_unified(db, kb_id, question.strip(), top_k=6):
                    if hit.get("source_type") == "entry":
                        eid = int(hit["entry_id"])
                        if eid in pinned_set:
                            continue
                        merged_hits.setdefault(f"entry:{eid}", hit)
                    else:
                        merged_hits.setdefault(f"chunk:{int(hit['chunk_id'])}", hit)
        for hit in list(merged_hits.values())[:20]:
            title = str(hit.get("title") or "")
            summary_hit = str(hit.get("summary") or "").strip().replace("\r\n", "\n")
            snippet = str(hit.get("snippet") or "").strip().replace("\r\n", "\n")
            if len(snippet) > 1200:
                snippet = snippet[:1200] + "…"
            src = hit.get("source_type") or "entry"
            role = ""
            if isinstance(hit.get("semantic_meta"), dict):
                role = str(hit["semantic_meta"].get("semantic_role") or "").strip()
            if src == "entry":
                block = f"- {title} (entry_id={hit['entry_id']}, source=entry)"
            else:
                block = f"- {title} (chunk_id={hit['chunk_id']}, document_id={hit.get('document_id')}, source=chunk"
                if role:
                    block += f", role={role}"
                block += ")"
            if summary_hit:
                sh = summary_hit if len(summary_hit) <= 480 else summary_hit[:480] + "…"
                block += f"\n  简述：{sh}"
            block += f"\n  {snippet}"
            sem_lines.append(block)
        if len(sem_lines) > 1:
            sections.append("\n".join(sem_lines))

    # Ontology SPARQL context supplement
    from config import get_settings
    if get_settings().ontology_enabled and kb_ids and routing_bundle and routing_bundle.metric_bound_table_ids:
        from services.routing.ontology_router import build_ontology_context_snippet

        onto_ctx = build_ontology_context_snippet(
            db, list(routing_bundle.metric_bound_table_ids), kb_ids
        )
        if onto_ctx.strip():
            sections.append("[本体语义层 — SPARQL 上下文]\n" + onto_ctx.strip())

    text = "\n\n".join(sections).strip()
    if len(text) > max_total_chars:
        return f"{text[:max_total_chars]}\n…（知识上下文总长度超限，尾部已省略；可把关键内容拆为多条条目或收窄检索范围）"
    return text
