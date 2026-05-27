"""Copilot 本体知识匹配：将用户问题映射到 RDF 中的术语 / 指标 / 物理表。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from config import get_settings


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
    from services.context_builder import kb_ids_for_business_domain

    if business_domain_id:
        return kb_ids_for_business_domain(db, business_domain_id)
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
    """生成一条可读映射说明。"""
    qbit = (question_phrase or question or "").strip()
    if len(qbit) > 80:
        qbit = qbit[:80] + "…"
    asset = f"本体{_kind_label(kind)}「{label}」"
    parts: list[str] = []
    if qbit:
        parts.append(f"您的问题「{qbit}」")
    else:
        parts.append("您的问题")
    parts.append(f"对应到{asset}")
    if definition:
        def_short = definition if len(definition) <= 120 else definition[:120] + "…"
        parts.append(f"（{def_short}）")
    if maps_to:
        parts.append(f"，并关联物理表：{maps_to}")
    else:
        parts.append("；当前未登记到具体物理表")
    return "".join(parts) + "。"


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

    try:
        from services.triple_store import get_triple_store
        from services.copilot.router import OntologyRouter

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

        router = OntologyRouter(store)
        route = router.full_route(kb_ids, q, top_k=12)
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
    context_parts: list[str] = []
    q_preview = q if len(q) <= 200 else q[:200] + "…"

    concept_iris = [c.get("iri") for c in concepts if c.get("iri")]
    tables_by_concept: dict[str, list[dict[str, Any]]] = {iri: [] for iri in concept_iris if iri}
    for t in tables:
        # tables from route_tables are linked to any matched concept; attach to all for display
        for iri in concept_iris:
            tables_by_concept.setdefault(iri, []).append(t)

    for c in concepts:
        iri = str(c.get("iri") or "")
        label = str(c.get("label") or "").strip()
        if not label:
            continue
        ctype = str(c.get("type") or "")
        linked = tables_by_concept.get(iri, tables) if iri else tables
        item = _format_mapping_item(c, linked)
        items.append(item)
        definition = str(item.get("definition") or "").strip()
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
        })
        ontology_trace.append({
            "iri": iri,
            "label": label,
            "type": _concept_kind(ctype),
            "source": "sparql",
            "maps_to": item.get("maps_to") or "",
        })
        if item["kind"] == "metric":
            line = f"指标「{label}」"
            if definition:
                line += f"：{definition}"
            if item.get("maps_to"):
                line += f" → 物理表 {item['maps_to']}"
            context_parts.append(line)
        elif item["kind"] == "term":
            line = f"术语「{label}」"
            if definition:
                line += f"：{definition}"
            if item.get("maps_to"):
                line += f" → 物理表 {item['maps_to']}"
            context_parts.append(line)
        else:
            context_parts.append(f"概念「{label}」" + (f"：{definition}" if definition else ""))

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
            context_parts.append(f"物理表「{name}」")

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
        detail = "SPARQL 命中概念 {} 个、关联物理表 {} 个。".format(len(concepts), len(tables))
    else:
        summary = (
            "【问题 → 本体映射】\n"
            f"原问题：{q_preview}\n\n"
            "映射结果：未在本体知识库中找到与问题语义匹配的术语、指标或物理表。\n"
            "建议：在知识库完成语义清洗与本体建模后重试，或在提问中直接使用已建模的指标/术语名称。"
        )
        detail = "SPARQL 未命中概念（kb_ids={}）。".format(kb_ids)

    return OntologyMatchResult(
        matched=matched,
        summary=summary,
        detail=detail,
        question=q,
        mappings=mappings,
        items=items,
        ontology_trace=ontology_trace,
        ontology_context_text="\n".join(dict.fromkeys(context_parts))[:12000],
        concepts=concepts,
        tables=tables,
    )
