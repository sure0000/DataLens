"""Assertion lifecycle — maps dl:approvalStatus to governance states and supports promote."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri
from services.triple_store import get_triple_store

_logger = logging.getLogger(__name__)

# approvalStatus (stored) → lifecycle phase (UI)
STATUS_TO_LIFECYCLE: dict[str, str] = {
    "draft": "draft",
    "pending_review": "linked",
    "approved": "production",
    "rejected": "rejected",
}

LIFECYCLE_TO_STATUS: dict[str, str] = {
    "draft": "draft",
    "linked": "pending_review",
    "shacl_passed": "pending_review",
    "production": "approved",
    "rejected": "rejected",
}

ALLOWED_STATUSES = frozenset(STATUS_TO_LIFECYCLE.keys())

# Valid promote transitions (from_status -> to_status)
PROMOTE_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pending_review", "approved", "rejected"}),
    "pending_review": frozenset({"approved", "rejected", "draft"}),
    "approved": frozenset({"pending_review", "draft", "rejected"}),
    "rejected": frozenset({"draft", "pending_review"}),
}


def lifecycle_phase(approval_status: str | None) -> str:
    return STATUS_TO_LIFECYCLE.get(approval_status or "draft", "draft")


def get_assertion_status(kb_id: int, subject: str) -> dict[str, Any]:
    graph = kb_graph_iri(kb_id)
    rows = get_triple_store().sparql_query(
        f"""
        PREFIX dl: <{NS}>
        SELECT ?status WHERE {{
          GRAPH <{graph}> {{
            <{subject}> dl:approvalStatus ?status .
          }}
        }}
        LIMIT 1
        """
    )
    status = str(rows[0].get("status", "draft")) if rows else None
    exists = bool(rows) or _subject_exists(kb_id, subject)
    return {
        "subject": subject,
        "exists": exists,
        "approval_status": status,
        "lifecycle": lifecycle_phase(status) if status else None,
    }


def _subject_exists(kb_id: int, subject: str) -> bool:
    graph = kb_graph_iri(kb_id)
    rows = get_triple_store().sparql_query(
        f"SELECT ?p WHERE {{ GRAPH <{graph}> {{ <{subject}> ?p ?o }} }} LIMIT 1"
    )
    return bool(rows)


def promote_assertion(
    kb_id: int,
    subject: str,
    *,
    target_status: str | None = None,
    target_lifecycle: str | None = None,
) -> dict[str, Any]:
    """Update dl:approvalStatus for a resource in the production graph."""
    if target_lifecycle and not target_status:
        target_status = LIFECYCLE_TO_STATUS.get(target_lifecycle)
    if not target_status:
        target_status = "approved"
    if target_status not in ALLOWED_STATUSES:
        return {"ok": False, "error": f"invalid status: {target_status}"}

    current = get_assertion_status(kb_id, subject)
    if not current["exists"]:
        return {"ok": False, "error": "subject not found in production graph"}

    from_status = current.get("approval_status") or "draft"
    if from_status not in PROMOTE_TRANSITIONS:
        from_status = "draft"
    if target_status not in PROMOTE_TRANSITIONS.get(from_status, ALLOWED_STATUSES):
        return {
            "ok": False,
            "error": f"transition {from_status} -> {target_status} not allowed",
            "from_status": from_status,
        }

    graph = kb_graph_iri(kb_id)
    store = get_triple_store()
    pred = f"{NS}approvalStatus"

    try:
        if store.use_fuseki_backend():
            store._sparql_update(
                f"""
                DELETE {{ GRAPH <{graph}> {{ <{subject}> <{pred}> ?old . }} }}
                WHERE  {{ GRAPH <{graph}> {{ <{subject}> <{pred}> ?old . }} }} ;
                INSERT {{ GRAPH <{graph}> {{ <{subject}> <{pred}> "{target_status}" . }} }}
                """
            )
        else:
            from rdflib import Literal, URIRef

            g = store.get_named_graph(graph)
            subj = URIRef(subject)
            p = URIRef(pred)
            for o in list(g.objects(subj, p)):
                g.remove((subj, p, o))
            g.add((subj, p, Literal(target_status)))
            store._persist_local_store()
    except Exception as exc:
        _logger.warning("promote_assertion failed kb=%s subject=%s: %s", kb_id, subject, exc)
        return {"ok": False, "error": str(exc)}

    try:
        from services.ingestion.events import emit

        emit(
            "assertion.promoted",
            kb_id=kb_id,
            subject=subject,
            from_status=from_status,
            to_status=target_status,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "kb_id": kb_id,
        "subject": subject,
        "from_status": from_status,
        "to_status": target_status,
        "from_lifecycle": lifecycle_phase(from_status),
        "to_lifecycle": lifecycle_phase(target_status),
    }
