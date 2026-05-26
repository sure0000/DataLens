"""Template-based suggested fixes for quarantined triples."""

from __future__ import annotations

import json
from typing import Any

from ontology import NS, table_iri

# reason code → human label + fix templates
REASON_LABELS: dict[str, str] = {
    "unresolved_table_ref": "无法解析物理表引用",
    "ambiguous_table_ref": "表引用存在歧义",
    "unknown_predicate": "谓词不在 TBox 白名单",
    "tbox_reject": "TBox 校验失败",
    "shacl_violation": "SHACL 约束未通过",
    "status_gate": "审批状态未满足",
}


def _parse_raw(raw: str | dict | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def suggest_templates(reason: str, raw_triple: dict[str, Any] | str | None = None) -> list[dict[str, Any]]:
    """Return actionable fix templates for UI."""
    data = _parse_raw(raw_triple if not isinstance(raw_triple, dict) else json.dumps(raw_triple))
    if isinstance(raw_triple, dict):
        data = raw_triple

    templates: list[dict[str, Any]] = []
    ref = data.get("ref") or data.get("object", "")

    if reason == "unresolved_table_ref":
        templates.append(
            {
                "id": "map_table_by_platform_id",
                "label": "绑定为 platformId 表 IRI",
                "description": "将客体替换为 https://datalens.local/data/table/{id}",
                "requires": {"platform_id": "number"},
            }
        )
        templates.append(
            {
                "id": "drop_triple",
                "label": "丢弃该三元组",
                "description": "从隔离区移除且不写入生产图",
            }
        )

    if reason == "ambiguous_table_ref":
        templates.append(
            {
                "id": "pick_first_table",
                "label": "使用第一个匹配表",
                "description": "自动选取最高分匹配的表 IRI（需传 table_id）",
                "requires": {"table_id": "number"},
            }
        )
        templates.append({"id": "drop_triple", "label": "丢弃该三元组", "description": "不写入生产图"})

    if reason == "unknown_predicate":
        templates.append(
            {
                "id": "strip_predicate",
                "label": "丢弃该三元组",
                "description": f"未知谓词：{data.get('predicate', '')[:80]}",
            }
        )

    if reason in ("shacl_violation", "tbox_reject", "status_gate"):
        templates.append(
            {
                "id": "force_approve",
                "label": "强制批准入图",
                "description": "跳过隔离（仍经 clean_triples + SHACL）",
            }
        )

    if not templates:
        templates.append(
            {
                "id": "force_approve",
                "label": "批准入图",
                "description": REASON_LABELS.get(reason, reason or "未知原因"),
            }
        )

    return templates


def apply_template(
    kb_id: int,
    *,
    reason: str,
    raw_triple: dict[str, Any],
    template_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a fix template and return triple ready for clean_triples."""
    params = params or {}
    subject = raw_triple.get("subject", "")
    predicate = raw_triple.get("predicate", "")
    obj = raw_triple.get("object", "")
    object_is_uri = bool(raw_triple.get("object_is_uri", False))

    if template_id == "drop_triple":
        return {"ok": True, "action": "drop"}

    if template_id == "map_table_by_platform_id":
        tid = params.get("platform_id") or params.get("table_id")
        if tid is None:
            return {"ok": False, "error": "需要 platform_id"}
        return {
            "ok": True,
            "action": "write",
            "triple": {
                "subject": subject,
                "predicate": predicate,
                "object": table_iri(int(tid)),
                "object_is_uri": True,
            },
        }

    if template_id == "pick_first_table":
        tid = params.get("table_id")
        if tid is None:
            return {"ok": False, "error": "需要 table_id"}
        return {
            "ok": True,
            "action": "write",
            "triple": {
                "subject": subject,
                "predicate": predicate,
                "object": table_iri(int(tid)),
                "object_is_uri": True,
            },
        }

    if template_id in ("force_approve", "strip_predicate"):
        if template_id == "strip_predicate":
            return {"ok": True, "action": "drop"}
        return {
            "ok": True,
            "action": "write",
            "triple": {
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "object_is_uri": object_is_uri,
            },
        }

    return {"ok": False, "error": f"未知模板: {template_id}"}
