"""Copilot validation → quarantine feedback loop (§4.4)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from ontology import kb_graph_iri, table_iri
from services.ontology.quarantine import QuarantineManager
from services.ontology.quarantine_templates import REASON_LABELS, apply_template, suggest_templates
from services.ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result
from services.triple_store import get_triple_store

_logger = logging.getLogger(__name__)

_TABLE_ID_RE = re.compile(r"/table/(\d+)(?:/|$)")


def _quarantine_items_payload(kb_id: int) -> list[dict[str, Any]]:
    mgr = QuarantineManager(get_triple_store())
    result = mgr.list_items(kb_id)
    items: list[dict[str, Any]] = []
    for item in result.items:
        raw = item.raw_triple or {}
        m = re.search(r"/item/(\d+)$", item.subject)
        item_idx = int(m.group(1)) if m else item.index
        reason = item.reason or "unknown"
        items.append(
            {
                "item_idx": item_idx,
                "q": item.subject,
                "reason": reason,
                "reason_label": REASON_LABELS.get(reason, reason),
                "raw": json.dumps(raw, ensure_ascii=False) if raw else item.suggested_fix,
                "subject": raw.get("subject"),
                "predicate": raw.get("predicate"),
                "object": raw.get("object"),
                "object_is_uri": raw.get("object_is_uri", False),
                "suggested_fix": item.suggested_fix,
                "fix_templates": suggest_templates(reason, raw),
            }
        )
    return items


def _platform_ids_from_routing(routing: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for key in ("tables", "expanded_tables"):
        for row in routing.get(key) or []:
            pid = row.get("platform_id")
            if pid not in (None, ""):
                try:
                    ids.append(int(pid))
                except (TypeError, ValueError):
                    pass
            iri = str(row.get("iri") or "")
            m = _TABLE_ID_RE.search(iri)
            if m:
                ids.append(int(m.group(1)))
    return list(dict.fromkeys(ids))


def _match_quarantine_items(
    items: list[dict[str, Any]],
    *,
    subject_iri: str | None = None,
    table_id: int | None = None,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    table_iri_str = table_iri(table_id) if table_id is not None else None
    for item in items:
        raw_subject = str(item.get("subject") or "")
        if subject_iri and raw_subject == subject_iri:
            matched.append(item)
            continue
        if subject_iri and subject_iri in raw_subject:
            matched.append(item)
            continue
        reason = item.get("reason") or ""
        if table_id is not None and reason in ("unresolved_table_ref", "ambiguous_table_ref"):
            obj = str(item.get("object") or "")
            ref = str(item.get("ref") or obj)
            if table_iri_str and table_iri_str in obj:
                matched.append(item)
            elif str(table_id) in ref:
                matched.append(item)
    return matched


def _suggest_fixes(
    matched_items: list[dict[str, Any]],
    platform_ids: list[int],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    primary_table_id = platform_ids[0] if platform_ids else None
    for item in matched_items:
        reason = item.get("reason") or ""
        suggestion: dict[str, Any] = {
            "item_idx": item["item_idx"],
            "reason": reason,
            "reason_label": item.get("reason_label", reason),
            "subject": item.get("subject"),
            "object": item.get("object"),
            "recommended_template": None,
            "recommended_params": {},
            "routing_table_ids": platform_ids,
        }
        if reason in ("unresolved_table_ref", "ambiguous_table_ref") and primary_table_id is not None:
            suggestion["recommended_template"] = (
                "map_table_by_platform_id" if reason == "unresolved_table_ref" else "pick_first_table"
            )
            suggestion["recommended_params"] = {"platform_id": primary_table_id, "table_id": primary_table_id}
        suggestions.append(suggestion)
    return suggestions


def _apply_quarantine_fix(
    kb_id: int,
    item: dict[str, Any],
    *,
    template_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "subject": item.get("subject") or "",
        "predicate": item.get("predicate") or "",
        "object": item.get("object") or "",
        "object_is_uri": bool(item.get("object_is_uri", False)),
    }
    if not raw["subject"] and item.get("raw"):
        try:
            raw = json.loads(item["raw"])
        except json.JSONDecodeError:
            pass

    fix = apply_template(
        kb_id,
        reason=item.get("reason") or "",
        raw_triple=raw,
        template_id=template_id,
        params=params or {},
    )
    if not fix.get("ok"):
        return {"ok": False, "item_idx": item["item_idx"], "error": fix.get("error", "修复失败")}

    mgr = QuarantineManager(get_triple_store())
    item_idx = int(item["item_idx"])
    if fix.get("action") == "drop":
        mgr.resolve(kb_id, item_idx, approved=False)
        return {"ok": True, "item_idx": item_idx, "action": "dropped"}

    tdata = fix["triple"]
    triple = RawTriple(
        tdata["subject"],
        tdata["predicate"],
        tdata["object"],
        tdata.get("object_is_uri", False),
        graph=kb_graph_iri(kb_id),
        confidence=90.0,
    )
    result = clean_triples([triple], kb_id=kb_id)
    out = persist_clean_result(result, kb_id)
    mgr.resolve(kb_id, item_idx, approved=False)
    return {"ok": True, "item_idx": item_idx, "action": "applied", **out}


def run_copilot_validation(
    db: Session,
    kb_id: int,
    *,
    question: str | None = None,
    subject_iri: str | None = None,
    table_id: int | None = None,
    entity_name: str | None = None,
    auto_apply: bool = False,
) -> dict[str, Any]:
    """Run Copilot ontology routing and match quarantine items for feedback."""
    q = (question or "").strip()
    if not q and entity_name:
        q = f"查询与「{entity_name}」相关的业务定义、指标口径及关联数据表"
    if not q and table_id is not None:
        q = f"分析 platformId={table_id} 数据表的业务含义、关联指标与上下游血缘"
    if not q:
        return {"ok": False, "error": "需要提供 question、entity_name 或 table_id"}

    from services.copilot.pipeline import CopilotPipeline

    pipeline = CopilotPipeline(get_triple_store(), db)
    routing = pipeline.route(q, kb_ids=[kb_id])
    platform_ids = _platform_ids_from_routing(routing)

    all_quarantine = _quarantine_items_payload(kb_id)
    matched = _match_quarantine_items(
        all_quarantine,
        subject_iri=subject_iri,
        table_id=table_id,
    )
    suggestions = _suggest_fixes(matched, platform_ids)

    applied: list[dict[str, Any]] = []
    if auto_apply:
        for item, suggestion in zip(matched, suggestions):
            template_id = suggestion.get("recommended_template")
            if not template_id:
                continue
            try:
                out = _apply_quarantine_fix(
                    kb_id,
                    item,
                    template_id=template_id,
                    params=suggestion.get("recommended_params") or {},
                )
                applied.append(out)
            except Exception as exc:
                _logger.warning(
                    "Copilot validation auto-apply failed kb=%s item=%s: %s",
                    kb_id,
                    item.get("item_idx"),
                    exc,
                    exc_info=True,
                )
                applied.append({"ok": False, "item_idx": item.get("item_idx"), "error": str(exc)})

    return {
        "ok": True,
        "kb_id": kb_id,
        "question": q,
        "routing_trace": {
            "concepts": routing.get("concepts") or [],
            "tables": routing.get("tables") or [],
            "expanded_tables": routing.get("expanded_tables") or [],
            "strategy": routing.get("strategy"),
            "candidate_table_ids": platform_ids,
        },
        "quarantine_total": len(all_quarantine),
        "matched_quarantine": matched,
        "fix_suggestions": suggestions,
        "auto_applied": applied if auto_apply else [],
    }
