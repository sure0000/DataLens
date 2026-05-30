"""Provenance chain: groundedBy → DocumentChunk → Document → EvidencePackage."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Document, DocumentChunk, EvidencePackage, KnowledgeBase
from ontology import NS, kb_graph_iri
from services.ontology_store import sparql_query

_logger = logging.getLogger(__name__)

_CHUNK_ID_RE = re.compile(r"/chunk/(\d+)$")


def _chunk_id_from_iri(iri: str) -> int | None:
    m = _CHUNK_ID_RE.search(iri)
    return int(m.group(1)) if m else None


def build_entity_origin(kb: KnowledgeBase, source: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {
        "knowledge_base_id": kb.id,
        "knowledge_base_name": kb.name,
    }
    if source:
        base.update(source)
    return base


def fetch_grounded_sources(db: Session, kb_id: int) -> dict[str, dict[str, Any]]:
    """Map entity IRI -> source_label / source_type from groundedBy → Document."""
    graph = kb_graph_iri(kb_id)
    ns = str(NS)
    subject_to_chunk: dict[str, str] = {}
    try:
        rows = sparql_query(
            f"""
            PREFIX dl: <{ns}>
            SELECT ?s ?chunk WHERE {{
              GRAPH <{graph}> {{
                ?s dl:groundedBy ?chunk .
              }}
            }}
            LIMIT 2000
            """
        )
        for row in rows:
            s = str(row.get("s", ""))
            chunk = str(row.get("chunk", ""))
            if s and chunk and s not in subject_to_chunk:
                subject_to_chunk[s] = chunk
    except Exception as exc:
        _logger.warning("groundedBy batch query failed kb=%s: %s", kb_id, exc)
        return {}

    chunk_ids: list[int] = []
    iri_for_chunk: dict[int, list[str]] = {}
    for subject, chunk_iri in subject_to_chunk.items():
        cid = _chunk_id_from_iri(chunk_iri)
        if cid is None:
            continue
        chunk_ids.append(cid)
        iri_for_chunk.setdefault(cid, []).append(subject)

    if not chunk_ids:
        return {}

    chunks = db.execute(select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))).scalars().all()
    doc_ids = {c.document_id for c in chunks if c.document_id}
    docs_by_id: dict[int, Document] = {}
    if doc_ids:
        docs = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        docs_by_id = {d.id: d for d in docs}

    out: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        doc = docs_by_id.get(chunk.document_id) if chunk.document_id else None
        source_label = (doc.title if doc else None) or "文档分块"
        source_type = doc.source_type if doc else None
        for subject in iri_for_chunk.get(chunk.id, []):
            out[subject] = {
                "source_label": source_label,
                "source_type": source_type,
            }
    return out


def get_provenance_chain(db: Session, kb_id: int, subject: str) -> dict[str, Any]:
    graph = kb_graph_iri(kb_id)
    ns = str(NS)
    chunk_iris: list[str] = []
    try:
        rows = sparql_query(
            f"""
            PREFIX dl: <{ns}>
            SELECT ?chunk WHERE {{
              GRAPH <{graph}> {{
                <{subject}> dl:groundedBy ?chunk .
              }}
            }}
            """
        )
        chunk_iris = [str(r.get("chunk", "")) for r in rows if r.get("chunk")]
    except Exception:
        chunk_iris = []

    chunks: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []
    seen_doc_ids: set[int] = set()

    for ci in chunk_iris:
        chunk_id = _chunk_id_from_iri(ci)
        if chunk_id is None:
            chunks.append({"iri": ci, "chunk_id": None, "content_preview": None})
            continue
        row = db.get(DocumentChunk, chunk_id)
        if not row:
            chunks.append({"iri": ci, "chunk_id": chunk_id, "content_preview": None})
            continue
        preview = (row.content or "")[:240]
        chunks.append(
            {
                "iri": ci,
                "chunk_id": chunk_id,
                "chunk_index": row.chunk_index,
                "document_id": row.document_id,
                "content_preview": preview,
            }
        )
        if row.document_id and row.document_id not in seen_doc_ids:
            seen_doc_ids.add(row.document_id)
            doc = db.get(Document, row.document_id)
            if doc and doc.knowledge_base_id == kb_id:
                documents.append(
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "status": doc.status,
                        "source_type": doc.source_type,
                    }
                )
                pkg_rows = db.execute(
                    select(EvidencePackage).where(
                        EvidencePackage.knowledge_base_id == kb_id,
                        EvidencePackage.linked_document_id == doc.id,
                    )
                ).scalars().all()
                for pkg in pkg_rows:
                    packages.append(
                        {
                            "id": pkg.id,
                            "display_id": f"EP-{1000 + pkg.id}",
                            "title": pkg.title,
                            "asset_kind": pkg.asset_kind,
                            "connector": pkg.connector,
                            "processing_state": pkg.processing_state,
                        }
                    )

    return {
        "ok": True,
        "kb_id": kb_id,
        "subject": subject,
        "chunks": chunks,
        "documents": documents,
        "evidence_packages": packages,
        "has_provenance": bool(chunks),
    }
