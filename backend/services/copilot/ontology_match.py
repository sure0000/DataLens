"""Copilot 本体知识匹配：将用户问题映射到 RDF 中的术语 / 指标 / 物理表。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from config import get_settings

# 会话级本体匹配结果缓存（同一问题 + 同一 KB 集合，5 分钟内复用）
_CACHE_MAX_SIZE = 128
_CACHE_TTL_SEC = 300
_cache: dict[str, tuple[float, OntologyMatchResult]] = {}


def _cache_key(question: str, kb_ids: list[int]) -> str:
    q = (question or "").strip().lower()
    return f"{hash(tuple(sorted(kb_ids)))}:{hash(q)}"


def _cache_get(question: str, kb_ids: list[int]) -> OntologyMatchResult | None:
    key = _cache_key(question, kb_ids)
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, result = entry
    if time.monotonic() - ts > _CACHE_TTL_SEC:
        del _cache[key]
        return None
    return result


def _cache_set(question: str, kb_ids: list[int], result: OntologyMatchResult) -> None:
    if len(_cache) >= _CACHE_MAX_SIZE:
        # lazy eviction: clear oldest quarter
        sorted_keys = sorted(_cache.keys(), key=lambda k: _cache[k][0])
        for k in sorted_keys[: _CACHE_MAX_SIZE // 4]:
            _cache.pop(k, None)
    key = _cache_key(question, kb_ids)
    _cache[key] = (time.monotonic(), result)


def clear_ontology_match_cache() -> None:
    """清空缓存（用于测试或知识库更新后）。"""
    _cache.clear()


@dataclass
class OntologyMatchResult:
    matched: bool = False
    """面向用户的本体映射说明。"""
    summary: str = ""
    """写入 pipeline_trace 的详细说明。"""
    detail: str = ""
    question: str = ""
    """逐条映射：问题侧表述 → 本体资产 → 物理表。"""
    mappings: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    ontology_trace: list[dict[str, Any]] = field(default_factory=list)
    ontology_context_text: str = ""
    concepts: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


def _resolve_kb_ids(db: Session, business_domain_id: int | None) -> list[int]:
    """Ontology 匹配始终搜索全部知识库，不按业务域过滤。

    因为本体指标/术语可能跨域共享，领域过滤在 SQL 生成/表路由阶段完成。
    """
    try:
        from models import KnowledgeBase
        from sqlalchemy import select

        return [int(x) for x in db.execute(select(KnowledgeBase.id)).scalars().all()]
    except Exception:
        return []


def _concept_kind(ctype: str) -> str:
    c = (ctype or "").lower()
    if "metric" in c:
        return "metric"
    if "term" in c or "business" in c:
        return "term"
    return "concept"


def _kind_label(kind: str) -> str:
    return {"metric": "指标", "term": "术语", "concept": "概念", "table": "物理表"}.get(kind, "概念")


def _build_mapping_sentence(
    question: str,
    *,
    kind: str,
    label: str,
    definition: str = "",
    maps_to: str = "",
    question_phrase: str = "",
) -> str:
    """Generate a compact, scannable mapping description.

    Format: 本体指标「label」：definition → 物理表：t1、t2
    No longer repeats the full question in every entry.
    """
    asset = f"本体{_kind_label(kind)}「{label}」"
    parts: list[str] = [asset]
    if definition:
        def_short = definition if len(definition) <= 80 else definition[:80] + "…"
        parts.append(f"：{def_short}")
    if maps_to:
        parts.append(f" → 物理表：{maps_to}")
    return "".join(parts)


def _format_mapping_item(concept: dict[str, Any], linked_tables: list[dict[str, Any]]) -> dict[str, Any]:
    label = str(concept.get("label") or "").strip()
    definition = str(concept.get("definition") or "").strip()
    kind = _concept_kind(str(concept.get("type") or ""))
    table_names = [
        str(t.get("name") or t.get("platform_id") or "").strip()
        for t in linked_tables
        if str(t.get("name") or t.get("platform_id") or "").strip()
    ]
    maps_to = "、".join(dict.fromkeys(table_names)) if table_names else ""
    return {
        "kind": kind,
        "label": label,
        "definition": definition,
        "maps_to": maps_to,
        "iri": concept.get("iri"),
        "type": concept.get("type"),
    }


def _deduplicate_concepts_for_display(
    concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse concepts whose labels are substrings of another matched label.

    Example: when both "电量" and "用电量" match, "电量" is fully contained
    within "用电量" — keep only "用电量" for display.  This prevents users from
    seeing a dozen near-identical "XXX电量" entries.

    This only affects the display set.  The full concept list is preserved
    for ontology_context_text (LLM SQL prompt context).
    """
    if len(concepts) <= 1:
        return list(concepts)

    # Process longest-label-first so containment checks are stable
    sorted_c = sorted(
        concepts,
        key=lambda c: (-len(str(c.get("label", ""))), -float(c.get("match_score", 0))),
    )

    keep: list[dict[str, Any]] = []
    keep_labels: list[str] = []

    for c in sorted_c:
        label = str(c.get("label", "")).strip().lower()
        if not label:
            keep.append(c)
            continue

        # Drop if this label is fully contained within a kept label
        if any(label in kept for kept in keep_labels):
            continue

        # If this label contains a previously-kept shorter label, replace it
        # (only if the score isn't drastically worse)
        replaced = False
        for i, kept_label in enumerate(keep_labels):
            if kept_label in label:
                old_score = float(keep[i].get("match_score", 0))
                new_score = float(c.get("match_score", 0))
                if new_score >= old_score * 0.7:
                    keep[i] = c
                    keep_labels[i] = label
                replaced = True
                break

        if not replaced:
            keep.append(c)
            keep_labels.append(label)

    # Restore score-descending order
    keep.sort(key=lambda c: -float(c.get("match_score", 0)))
    return keep


def run_ontology_match(
    db: Session,
    question: str,
    business_domain_id: int | None,
) -> OntologyMatchResult:
    settings = get_settings()
    q = (question or "").strip()
    if not settings.ontology_enabled:
        return OntologyMatchResult(
            skipped=True,
            skip_reason="本体层未启用（ONTOLOGY_ENABLED=false）",
            summary="",
            detail="已跳过本体匹配：本体层未启用。",
        )

    kb_ids = _resolve_kb_ids(db, business_domain_id)
    if not kb_ids:
        return OntologyMatchResult(
            matched=False,
            question=q,
            summary=(
                "【问题 → 本体映射】\n"
                f"原问题：{q[:200] + ('…' if len(q) > 200 else '')}\n\n"
                "映射结果：当前未绑定业务域或未关联知识库，无法检索本体术语与指标。"
            ),
            detail="无可用知识库（kb_ids 为空），跳过 SPARQL 本体路由。",
        )

    if not q:
        return OntologyMatchResult(
            matched=False,
            summary="【本体映射】\n问题为空，无法进行本体匹配。",
            detail="用户问题为空。",
        )

    # 缓存命中直接返回
    cached = _cache_get(q, kb_ids)
    if cached is not None:
        return cached

    try:
        from services.triple_store import get_triple_store
        from services.copilot.router import OntologyRouter
        from services.nlp_helpers import extract_dimension_values

        store = get_triple_store()
        store_ready = store.probe_fuseki(timeout=2.0) or settings.ontology_local_store_enabled
        if not store_ready:
            return OntologyMatchResult(
                matched=False,
            question=q,
            summary=(
                "【问题 → 本体映射】\n"
                f"原问题：{q[:200] + ('…' if len(q) > 200 else '')}\n\n"
                "映射结果：本体存储暂不可用，无法检索已建模知识。请启动 Fuseki 或启用本地 Trig 存储。"
            ),
            detail=f"Fuseki 不可达：{settings.fuseki_url}",
        )

        from services.embedding_service import _embed

        # 预处理：提取并移除以维度值（人名、地名、ID 等），避免它们被误当作概念进行匹配
        dim_info = extract_dimension_values(q)
        dim_values_to_skip: list[str] = [dv["text"] for dv in dim_info.get("dimension_values", [])]
        q_for_routing = q
        if dim_values_to_skip:
            # 按长度降序排列，先替换长的避免短子串干扰
            for dv in sorted(dim_values_to_skip, key=len, reverse=True):
                q_for_routing = q_for_routing.replace(dv, " ")
            q_for_routing = " ".join(q_for_routing.split())  # 压缩多余空白

        query_vector: list[float] | None = None
        try:
            # Use q_for_routing (dimension values removed) so the embedding
            # search isn't skewed by person names, dates, IDs, etc.
            query_vector = _embed([q_for_routing])[0]
        except Exception:
            query_vector = None

        router = OntologyRouter(store)
        route = router.full_route(kb_ids, q_for_routing, top_k=12, db=db, query_vector=query_vector)
        concepts = route.get("concepts") or []
        tables = route.get("tables") or []
    except Exception as exc:
        return OntologyMatchResult(
            matched=False,
            summary=(
                "【本体映射】\n"
                f"本体检索失败，暂时无法展示问题与知识的映射关系（{exc}）。"
            ),
            detail=str(exc),
        )

    ontology_trace: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    q_preview = q if len(q) <= 200 else q[:200] + "…"

    concept_iris = [c.get("iri") for c in concepts if c.get("iri")]
    tables_by_concept: dict[str, list[dict[str, Any]]] = {}
    for t in tables:
        src_iri = str(t.get("source_concept_iri") or "")
        if src_iri and src_iri in concept_iris:
            tables_by_concept.setdefault(src_iri, []).append(t)

    # Fallback: ensure every concept has at least an empty list
    for iri in concept_iris:
        tables_by_concept.setdefault(iri, [])

    # ---- Pass 1: ontology_context_text from ALL concepts (for LLM) ----
    context_metric_lines: list[str] = []
    context_term_lines: list[str] = []

    for c in concepts:
        label = str(c.get("label") or "").strip()
        if not label:
            continue
        ctype = str(c.get("type") or "")
        definition = str(c.get("definition") or "").strip()
        kind = _concept_kind(ctype)
        iri = str(c.get("iri") or "")
        linked = tables_by_concept.get(iri, [])
        table_names = [
            str(t.get("name") or t.get("platform_id") or "").strip()
            for t in linked
            if str(t.get("name") or t.get("platform_id") or "").strip()
        ]
        maps_to = "、".join(dict.fromkeys(table_names)) if table_names else ""
        table_ref = f" → {maps_to}" if maps_to else ""
        if kind == "metric":
            context_metric_lines.append(
                f"- **{label}**" + (f"：{definition}" if definition else "") + table_ref
            )
        elif kind == "term":
            context_term_lines.append(
                f"- **{label}**" + (f"：{definition}" if definition else "") + table_ref
            )
        else:
            context_term_lines.append(
                f"- **{label}**" + (f"：{definition}" if definition else "")
            )

    context_table_lines: list[str] = []
    for t in tables:
        name = str(t.get("name") or t.get("platform_id") or "").strip()
        if not name:
            continue
        tbl_summary = str(t.get("summary") or "").strip()
        context_table_lines.append(
            f"- **{name}**" + (f"：{tbl_summary}" if tbl_summary else "")
        )

    context_blocks: list[str] = []
    if context_metric_lines:
        context_blocks.append("### 指标口径\n" + "\n".join(context_metric_lines))
    if context_term_lines:
        context_blocks.append("### 业务术语\n" + "\n".join(context_term_lines))
    if context_table_lines:
        context_blocks.append("### 关联物理表\n" + "\n".join(context_table_lines))
    ontology_context_text = "\n\n".join(context_blocks)[:12000]

    # ---- Pass 2: mappings and items from DEDUPED concepts (for display) ----
    display_concepts = _deduplicate_concepts_for_display(concepts)

    for c in display_concepts:
        iri = str(c.get("iri") or "")
        label = str(c.get("label") or "").strip()
        if not label:
            continue
        ctype = str(c.get("type") or "")
        linked = tables_by_concept.get(iri, [])
        item = _format_mapping_item(c, linked)
        items.append(item)
        definition = str(item.get("definition") or "").strip()

        # 概念归属验证：判定是精确匹配还是语义推断
        label_in_q = label.lower() in q.lower()
        alias_in_q = any(
            (a or "").lower() in q.lower()
            for a in [c.get("altLabel", ""), c.get("definition", "")]
        )
        match_type = "exact" if label_in_q or alias_in_q else "semantic"

        mapping_desc = _build_mapping_sentence(
            q,
            kind=item["kind"],
            label=label,
            definition=definition,
            maps_to=str(item.get("maps_to") or ""),
        )
        mappings.append({
            "question_phrase": q_preview,
            "target_kind": item["kind"],
            "target_label": label,
            "target_definition": definition,
            "physical_tables": item.get("maps_to") or "",
            "description": mapping_desc,
            "match_type": match_type,
        })
        ontology_trace.append({
            "iri": iri,
            "label": label,
            "type": _concept_kind(ctype),
            "source": str(c.get("match_source") or "sparql"),
            "match_score": c.get("match_score"),
            "maps_to": item.get("maps_to") or "",
            "match_type": match_type,
        })

    for t in tables:
        name = str(t.get("name") or t.get("platform_id") or "").strip()
        if not name:
            continue
        if not any(name in (x.get("maps_to") or "") for x in items):
            desc = _build_mapping_sentence(
                q,
                kind="table",
                label=name,
                maps_to=name,
            )
            mappings.append({
                "question_phrase": q_preview,
                "target_kind": "table",
                "target_label": name,
                "target_definition": "",
                "physical_tables": name,
                "description": desc,
            })
            ontology_trace.append({
                "iri": str(t.get("iri") or ""),
                "label": name,
                "type": "table",
                "source": "sparql",
            })

    matched = bool(items or tables)
    if matched:
        mapping_lines = [
            "【问题 → 本体映射】",
            f"原问题：{q_preview}",
            "",
            "映射说明（问题语义如何对应到已建模知识）：",
        ]
        for i, mp in enumerate(mappings[:10], start=1):
            mapping_lines.append(f"{i}. {mp.get('description') or ''}")
        if len(mappings) > 10:
            mapping_lines.append(f"… 另有 {len(mappings) - 10} 条映射未展开")
        summary = "\n".join(mapping_lines)
        sources = ", ".join(sorted({str(c.get("match_source") or "unknown") for c in concepts}))
        detail = "混合路由命中概念 {} 个（{}）、关联物理表 {} 个。".format(
            len(concepts), sources or "—", len(tables)
        )
    else:
        summary = (
            "【问题 → 本体映射】\n"
            f"原问题：{q_preview}\n\n"
            "映射结果：未在本体知识库中找到与问题语义匹配的术语、指标或物理表。\n"
            "建议：在知识库完成语义清洗与本体建模后重试，或在提问中直接使用已建模的指标/术语名称。"
        )
        detail = "混合路由未命中概念（kb_ids={}，策略=substring+embedding+keyword）。".format(kb_ids)

    result = OntologyMatchResult(
        matched=matched,
        summary=summary,
        detail=detail,
        question=q,
        mappings=mappings,
        items=items,
        ontology_trace=ontology_trace,
        ontology_context_text=ontology_context_text,
        concepts=concepts,
        tables=tables,
    )
    _cache_set(q, kb_ids, result)
    return result
