"""P2-1 自动业务域路由：未选域时推荐 / 高置信自动绑定。"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import BusinessDomain, BusinessDomainDescription
from services.context_builder import latest_table_summaries, tables_from_business_domain


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower()))


def _domain_profile_text(db: Session, domain_id: int) -> str:
    dom = db.get(BusinessDomain, domain_id)
    if not dom:
        return ""
    desc_row = (
        db.execute(
            select(BusinessDomainDescription)
            .where(BusinessDomainDescription.domain_id == domain_id)
            .order_by(BusinessDomainDescription.created_at.desc())
        )
        .scalars()
        .first()
    )
    desc = (desc_row.content or "").strip() if desc_row else ""
    summaries = latest_table_summaries(db)
    table_bits: list[str] = []
    for t in tables_from_business_domain(db, domain_id)[:24]:
        s = summaries.get(t.id)
        if s and s.summary:
            table_bits.append(s.summary)
        table_bits.append(f"{t.database_name}.{t.table_name}")
    return " ".join([dom.name or "", desc, *table_bits])


def _score_domain_question(question: str, profile: str, domain_name: str) -> float:
    q = (question or "").strip().lower()
    if not q:
        return 0.0
    name_l = (domain_name or "").strip().lower()
    score = 0.0
    if name_l and name_l in q:
        score += 0.45
    q_tokens = _token_set(q)
    profile_tokens = _token_set(profile)
    if profile_tokens:
        overlap = len(q_tokens & profile_tokens) / max(len(q_tokens), 1)
        score += min(0.55, overlap * 0.9)
    return min(1.0, score)


def suggest_business_domains(
    db: Session,
    question: str,
    *,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """对全部业务域打分，返回 top-k 推荐（含 score / requires_confirmation）。"""
    q = (question or "").strip()
    if not q:
        return []

    settings = get_settings()
    domains = db.execute(select(BusinessDomain).order_by(BusinessDomain.created_at.desc())).scalars().all()
    ranked: list[dict[str, Any]] = []
    for dom in domains:
        profile = _domain_profile_text(db, dom.id)
        score = _score_domain_question(q, profile, dom.name or "")
        if score < settings.copilot_auto_domain_suggest_min_score:
            continue
        ranked.append(
            {
                "domain_id": dom.id,
                "domain_name": dom.name,
                "score": round(score, 4),
                "requires_confirmation": score < settings.copilot_auto_domain_apply_min_score,
                "auto_applicable": score >= settings.copilot_auto_domain_apply_min_score,
            }
        )
    ranked.sort(key=lambda x: (-float(x["score"]), int(x["domain_id"])))
    return ranked[:top_k]


def resolve_effective_business_domain_id(
    db: Session,
    question: str,
    business_domain_id: int | None,
    table_id: int | None,
) -> tuple[int | None, dict[str, Any] | None, bool]:
    """
    返回 (effective_domain_id, top_suggestion, auto_applied)。
    低置信仅返回 suggestion，不 silent 切换域。
    """
    if business_domain_id is not None or table_id is not None:
        return business_domain_id, None, False

    settings = get_settings()
    if not settings.copilot_auto_domain_enabled:
        return None, None, False

    suggestions = suggest_business_domains(db, question, top_k=1)
    if not suggestions:
        return None, None, False

    top = suggestions[0]
    if top.get("auto_applicable"):
        return int(top["domain_id"]), top, True
    return None, top, False
