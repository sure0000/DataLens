"""Source deletion cascade cleanup helpers.

Scope:
- remove source-bound evidence packages
- remove source-bound documents / entries
- remove RDF assertions grounded by affected document chunks
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from rdflib import URIRef
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from models import (
    Document,
    DocumentChunk,
    EvidencePackage,
    KnowledgeApiSource,
    KnowledgeDatabaseImport,
    KnowledgeEntry,
    KnowledgeGitSource,
)
from ontology import NS, chunk_iri, kb_graph_iri
from services.embedding_service import delete_embeddings_for_knowledge_entries
from services.triple_store import get_triple_store

_DL_GROUNDED_BY = URIRef(f"{NS}groundedBy")
_DL_SOURCE_CHUNK = URIRef(f"{NS}sourceChunk")


@dataclass
class CleanupStats:
    entry_count: int = 0
    document_count: int = 0
    package_count: int = 0
    assertion_subject_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "entries_deleted": self.entry_count,
            "documents_deleted": self.document_count,
            "evidence_packages_deleted": self.package_count,
            "assertions_deleted": self.assertion_subject_count,
        }


def _as_int_list(values: list[Any]) -> list[int]:
    out: list[int] = []
    for value in values:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def _delete_evidence_packages(
    db: Session,
    *,
    kb_id: int,
    source_matcher: Callable[[dict[str, Any]], bool],
    linked_entry_ids: set[int],
    linked_document_ids: set[int],
) -> int:
    rows = db.execute(
        select(EvidencePackage).where(EvidencePackage.knowledge_base_id == kb_id)
    ).scalars().all()
    to_delete: list[EvidencePackage] = []
    for row in rows:
        src_ref = row.source_ref if isinstance(row.source_ref, dict) else {}
        linked_entries = set(_as_int_list(row.linked_entry_ids if isinstance(row.linked_entry_ids, list) else []))
        if source_matcher(src_ref):
            to_delete.append(row)
            continue
        if row.linked_document_id is not None and int(row.linked_document_id) in linked_document_ids:
            to_delete.append(row)
            continue
        if linked_entries and (linked_entries & linked_entry_ids):
            to_delete.append(row)
            continue
    for row in to_delete:
        db.delete(row)
    return len(to_delete)


def _purge_rdf_assertions_for_chunk_ids(kb_id: int, chunk_ids: list[int]) -> int:
    if not chunk_ids:
        return 0
    chunk_iris = [chunk_iri(cid) for cid in chunk_ids]
    graph = kb_graph_iri(kb_id)
    store = get_triple_store()
    if store.use_fuseki_backend():
        values = " ".join(f"<{iri}>" for iri in chunk_iris)
        rows = store.sparql_query(
            f"""
            PREFIX dl: <{NS}>
            SELECT DISTINCT ?s WHERE {{
              GRAPH <{graph}> {{
                VALUES ?chunk {{ {values} }}
                ?s ?rel ?chunk .
                FILTER(?rel IN (dl:groundedBy, dl:sourceChunk))
              }}
            }}
            """
        )
        subjects = [str(r.get("s", "")).strip() for r in rows if str(r.get("s", "")).strip()]
        if subjects:
            subject_values = " ".join(f"<{s}>" for s in subjects)
            store._sparql_update(  # noqa: SLF001
                f"""
                DELETE {{
                  GRAPH <{graph}> {{
                    ?s ?p ?o .
                    ?x ?xp ?s .
                  }}
                }}
                WHERE {{
                  GRAPH <{graph}> {{
                    VALUES ?s {{ {subject_values} }}
                    ?s ?p ?o .
                    OPTIONAL {{ ?x ?xp ?s . }}
                  }}
                }}
                """
            )
        store._sparql_update(  # noqa: SLF001
            f"""
            DELETE {{
              GRAPH <{graph}> {{
                ?s ?p ?chunk .
              }}
            }}
            WHERE {{
              GRAPH <{graph}> {{
                VALUES ?chunk {{ {values} }}
                ?s ?p ?chunk .
              }}
            }}
            """
        )
        return len(subjects)

    g = store.get_named_graph(graph)
    chunk_refs = [URIRef(iri) for iri in chunk_iris]
    subjects: set[URIRef] = set()
    for cref in chunk_refs:
        for pred in (_DL_GROUNDED_BY, _DL_SOURCE_CHUNK):
            for subj in g.subjects(pred, cref):
                if isinstance(subj, URIRef):
                    subjects.add(subj)

    for subj in list(subjects):
        for triple in list(g.triples((subj, None, None))):
            g.remove(triple)
        for triple in list(g.triples((None, None, subj))):
            g.remove(triple)

    for cref in chunk_refs:
        for triple in list(g.triples((None, None, cref))):
            g.remove(triple)

    store._persist_local_store()  # noqa: SLF001
    return len(subjects)


def _collect_source_documents(
    db: Session,
    *,
    kb_id: int,
    entry_ids: list[int],
    source_kind: str | None,
    source_id_field: str,
    source_id: int,
) -> list[int]:
    where_clauses = [
        Document.knowledge_base_id == kb_id,
        cast(Document.source_meta, JSONB)[source_id_field].astext == str(source_id),
    ]
    if source_kind:
        where_clauses.append(cast(Document.source_meta, JSONB)["kind"].astext == source_kind)
    direct = db.execute(
        select(Document.id).where(*where_clauses)
    ).scalars().all()
    via_entry = []
    if entry_ids:
        via_entry = db.execute(
            select(Document.id).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id.in_(entry_ids),
            )
        ).scalars().all()
    return sorted({int(x) for x in [*direct, *via_entry]})


def cleanup_git_source(
    db: Session,
    *,
    kb_id: int,
    source_id: int,
    hard_delete: bool,
    source_row: Any,
) -> CleanupStats:
    entry_ids = db.execute(
        select(KnowledgeEntry.id).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
            cast(KnowledgeEntry.source_meta, JSONB)["git_source_id"].astext == str(source_id),
        )
    ).scalars().all()
    doc_ids = _collect_source_documents(
        db,
        kb_id=kb_id,
        entry_ids=[int(x) for x in entry_ids],
        source_kind="git_file",
        source_id_field="git_source_id",
        source_id=source_id,
    )
    chunk_ids = db.execute(
        select(DocumentChunk.id).where(DocumentChunk.document_id.in_(doc_ids))
    ).scalars().all() if doc_ids else []

    stats = CleanupStats()
    source_owner = str(getattr(source_row, "owner", "") or "").strip().lower()
    source_repo = str(getattr(source_row, "repo", "") or "").strip().lower()
    source_branch = str(getattr(source_row, "branch", "") or "").strip()

    def _git_matcher(src: dict[str, Any]) -> bool:
        if str(src.get("git_source_id") or "") == str(source_id):
            return True
        owner = str(src.get("owner") or "").strip().lower()
        repo = str(src.get("repo") or "").strip().lower()
        if owner and repo and owner == source_owner and repo == source_repo:
            branch = str(src.get("branch") or "").strip()
            if not source_branch or not branch or branch == source_branch:
                return True
        return False

    stats.package_count = _delete_evidence_packages(
        db,
        kb_id=kb_id,
        source_matcher=_git_matcher,
        linked_entry_ids={int(x) for x in entry_ids},
        linked_document_ids=set(doc_ids),
    )
    if doc_ids:
        docs = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        for doc in docs:
            db.delete(doc)
        stats.document_count = len(docs)
    if entry_ids:
        delete_embeddings_for_knowledge_entries(db, [int(x) for x in entry_ids])
        entries = db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids))).scalars().all()
        for entry in entries:
            db.delete(entry)
        stats.entry_count = len(entries)

    stats.assertion_subject_count = _purge_rdf_assertions_for_chunk_ids(
        kb_id,
        [int(x) for x in chunk_ids],
    )
    if hard_delete:
        db.delete(source_row)
    else:
        source_row.enabled = False
        source_row.updated_at = datetime.utcnow()
    return stats


def collect_api_source_kb_ids(db: Session, source_id: int, source_row: Any) -> list[int]:
    kb_ids: set[int] = set()
    if getattr(source_row, "knowledge_base_id", None) is not None:
        kb_ids.add(int(source_row.knowledge_base_id))

    entry_kb = db.execute(
        select(KnowledgeEntry.knowledge_base_id).where(
            cast(KnowledgeEntry.source_meta, JSONB)["api_source_id"].astext == str(source_id)
        )
    ).scalars().all()
    doc_kb = db.execute(
        select(Document.knowledge_base_id).where(
            cast(Document.source_meta, JSONB)["api_source_id"].astext == str(source_id)
        )
    ).scalars().all()
    pkg_rows = db.execute(
        select(EvidencePackage).where(EvidencePackage.connector == "api")
    ).scalars().all()
    kb_ids.update(int(x) for x in entry_kb if x is not None)
    kb_ids.update(int(x) for x in doc_kb if x is not None)
    for row in pkg_rows:
        src = row.source_ref if isinstance(row.source_ref, dict) else {}
        if str(src.get("source_id") or src.get("api_source_id") or "") == str(source_id):
            kb_ids.add(int(row.knowledge_base_id))
    return sorted(kb_ids)


def cleanup_api_source_in_kb(
    db: Session,
    *,
    kb_id: int,
    source_id: int,
) -> CleanupStats:
    entry_ids = db.execute(
        select(KnowledgeEntry.id).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["api_source_id"].astext == str(source_id),
        )
    ).scalars().all()
    doc_ids = _collect_source_documents(
        db,
        kb_id=kb_id,
        entry_ids=[int(x) for x in entry_ids],
        source_kind=None,
        source_id_field="api_source_id",
        source_id=source_id,
    )

    chunk_ids = db.execute(
        select(DocumentChunk.id).where(DocumentChunk.document_id.in_(doc_ids))
    ).scalars().all() if doc_ids else []

    stats = CleanupStats()
    stats.package_count = _delete_evidence_packages(
        db,
        kb_id=kb_id,
        source_matcher=lambda src: str(src.get("source_id") or src.get("api_source_id") or "") == str(source_id),
        linked_entry_ids={int(x) for x in entry_ids},
        linked_document_ids=set(doc_ids),
    )
    if doc_ids:
        docs = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        for doc in docs:
            db.delete(doc)
        stats.document_count = len(docs)
    if entry_ids:
        delete_embeddings_for_knowledge_entries(db, [int(x) for x in entry_ids])
        entries = db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids))).scalars().all()
        for entry in entries:
            db.delete(entry)
        stats.entry_count = len(entries)
    stats.assertion_subject_count = _purge_rdf_assertions_for_chunk_ids(
        kb_id,
        [int(x) for x in chunk_ids],
    )
    return stats


def cleanup_database_import(
    db: Session,
    *,
    kb_id: int,
    import_id: int,
) -> CleanupStats:
    entry_ids = db.execute(
        select(KnowledgeEntry.id).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "database",
            cast(KnowledgeEntry.source_meta, JSONB)["import_id"].astext == str(import_id),
        )
    ).scalars().all()
    doc_ids = _collect_source_documents(
        db,
        kb_id=kb_id,
        entry_ids=[int(x) for x in entry_ids],
        source_kind=None,
        source_id_field="import_id",
        source_id=import_id,
    )
    chunk_ids = db.execute(
        select(DocumentChunk.id).where(DocumentChunk.document_id.in_(doc_ids))
    ).scalars().all() if doc_ids else []

    stats = CleanupStats()
    stats.package_count = _delete_evidence_packages(
        db,
        kb_id=kb_id,
        source_matcher=lambda src: str(src.get("import_id") or "") == str(import_id),
        linked_entry_ids={int(x) for x in entry_ids},
        linked_document_ids=set(doc_ids),
    )
    if doc_ids:
        docs = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        for doc in docs:
            db.delete(doc)
        stats.document_count = len(docs)
    if entry_ids:
        delete_embeddings_for_knowledge_entries(db, [int(x) for x in entry_ids])
        entries = db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids))).scalars().all()
        for entry in entries:
            db.delete(entry)
        stats.entry_count = len(entries)
    stats.assertion_subject_count = _purge_rdf_assertions_for_chunk_ids(
        kb_id,
        [int(x) for x in chunk_ids],
    )
    return stats


def cleanup_orphan_evidence_packages(db: Session) -> dict[str, int]:
    """Best-effort cleanup for stale EvidencePackage rows left by legacy deletion flows."""
    rows = db.execute(select(EvidencePackage)).scalars().all()
    if not rows:
        return {"scanned": 0, "deleted": 0}

    valid_doc = {
        (int(kb), int(doc_id))
        for kb, doc_id in db.execute(select(Document.knowledge_base_id, Document.id)).all()
    }
    valid_entry = {
        (int(kb), int(entry_id))
        for kb, entry_id in db.execute(select(KnowledgeEntry.knowledge_base_id, KnowledgeEntry.id)).all()
    }
    valid_git = {
        (int(kb), int(source_id))
        for kb, source_id in db.execute(select(KnowledgeGitSource.knowledge_base_id, KnowledgeGitSource.id)).all()
    }
    valid_git_repo = {
        (
            int(row.knowledge_base_id),
            str(row.owner or "").strip().lower(),
            str(row.repo or "").strip().lower(),
            str(row.branch or "").strip(),
        )
        for row in db.execute(select(KnowledgeGitSource)).scalars().all()
    }
    valid_import = {
        (int(kb), int(import_id))
        for kb, import_id in db.execute(select(KnowledgeDatabaseImport.knowledge_base_id, KnowledgeDatabaseImport.id)).all()
    }
    valid_api = {int(source_id) for source_id in db.execute(select(KnowledgeApiSource.id)).scalars().all()}

    deleted = 0
    for row in rows:
        kb_id = int(row.knowledge_base_id)
        src = row.source_ref if isinstance(row.source_ref, dict) else {}
        remove = False

        if row.connector == "git":
            git_id = src.get("git_source_id")
            if git_id is not None:
                try:
                    remove = (kb_id, int(git_id)) not in valid_git
                except (TypeError, ValueError):
                    remove = True
            else:
                owner = str(src.get("owner") or "").strip().lower()
                repo = str(src.get("repo") or "").strip().lower()
                branch = str(src.get("branch") or "").strip()
                if owner and repo:
                    remove = (
                        (kb_id, owner, repo, branch) not in valid_git_repo
                        and (kb_id, owner, repo, "") not in valid_git_repo
                    )
        elif row.connector == "database":
            import_id = src.get("import_id")
            if import_id is not None:
                try:
                    remove = (kb_id, int(import_id)) not in valid_import
                except (TypeError, ValueError):
                    remove = True
        elif row.connector == "api":
            api_source_id = src.get("source_id")
            if api_source_id is None:
                api_source_id = src.get("api_source_id")
            if api_source_id is not None:
                try:
                    remove = int(api_source_id) not in valid_api
                except (TypeError, ValueError):
                    remove = True
        elif row.connector == "file":
            # Legacy bad rows: file connector but no resolvable linkage fields.
            # Keep only rows that can be traced by explicit refs or linked ids.
            has_file_ref = bool(str(src.get("filename") or src.get("ref") or "").strip())
            has_entry_ref = src.get("entry_id") is not None
            has_doc_ref = src.get("document_id") is not None or row.linked_document_id is not None
            has_linked_entries = isinstance(row.linked_entry_ids, list) and len(row.linked_entry_ids) > 0
            if not (has_file_ref or has_entry_ref or has_doc_ref or has_linked_entries):
                remove = True

        if not remove and row.linked_document_id is not None:
            remove = (kb_id, int(row.linked_document_id)) not in valid_doc

        if not remove and isinstance(row.linked_entry_ids, list) and row.linked_entry_ids:
            existing_linked = 0
            for item in row.linked_entry_ids:
                try:
                    if (kb_id, int(item)) in valid_entry:
                        existing_linked += 1
                except (TypeError, ValueError):
                    continue
            remove = existing_linked == 0

        if remove:
            db.delete(row)
            deleted += 1

    return {"scanned": len(rows), "deleted": deleted}
