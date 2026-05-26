"""Provenance chain: groundedBy → DocumentChunk → Document → EvidencePackage."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Document, DocumentChunk, EvidencePackage
from ontology import NS, kb_graph_iri
from services.ontology_store import sparql_query

_CHUNK_ID_RE = re.compile(r"/chunk/(\d+)$")


def _chunk_id_from_iri(iri: str) -> int | None:
    m = _CHUNK_ID_RE.search(iri)
    return int(m.group(1)) if m else None


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
