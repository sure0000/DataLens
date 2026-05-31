"""Source deletion cascade cleanup helpers.

Scope:
- remove source-bound evidence packages
- remove source-bound documents / entries
- remove RDF assertions grounded by affected document chunks
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

_logger = logging.getLogger(__name__)

_CHUNK_ID_FROM_IRI = re.compile(r"/chunk/(\d+)/?$")

from rdflib import URIRef
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from models import (
    ColumnMeta,
    Document,
    DocumentChunk,
    EvidencePackage,
    KnowledgeApiSource,
    KnowledgeDatabaseImport,
    KnowledgeEntry,
    KnowledgeGitSource,
    PipelineRun,
    TableMeta,
)
from ontology import NS, chunk_iri, column_iri, kb_graph_iri, legacy_column_iri, legacy_table_iri, table_iri
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
    pipeline_runs_deleted: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "entries_deleted": self.entry_count,
            "documents_deleted": self.document_count,
            "evidence_packages_deleted": self.package_count,
            "assertions_deleted": self.assertion_subject_count,
            "pipeline_runs_deleted": self.pipeline_runs_deleted,
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


def _purge_rdf_subjects(kb_id: int, subject_iris: list[str]) -> int:
    """Delete RDF subjects (and incoming links) from the KB production graph."""
    unique = sorted({s.strip() for s in subject_iris if s and str(s).strip()})
    if not unique:
        return 0
    graph = kb_graph_iri(kb_id)
    store = get_triple_store()
    if store.use_fuseki_backend():
        values = " ".join(f"<{iri}>" for iri in unique)
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
                VALUES ?s {{ {values} }}
                ?s ?p ?o .
                OPTIONAL {{ ?x ?xp ?s . }}
              }}
            }}
            """
        )
        return len(unique)

    g = store.get_named_graph(graph)
    refs = [URIRef(iri) for iri in unique]
    for subj in refs:
        for triple in list(g.triples((subj, None, None))):
            g.remove(triple)
        for triple in list(g.triples((None, None, subj))):
            g.remove(triple)
    store._persist_local_store()  # noqa: SLF001
    return len(unique)


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


def _purge_physical_tables_for_import(
    db: Session,
    *,
    kb_id: int,
    di: KnowledgeDatabaseImport,
) -> int:
    """Remove PhysicalTable / PhysicalColumn assertions synced for a database import."""
    table_ids = list(
        db.execute(
            select(TableMeta.id).where(
                TableMeta.datasource_id == di.datasource_id,
                TableMeta.database_name.in_(di.database_names or []),
            )
        ).scalars().all()
    )
    if not table_ids:
        return 0
    subjects: list[str] = []
    for tid in table_ids:
        tid_int = int(tid)
        subjects.append(table_iri(tid_int))
        subjects.append(legacy_table_iri(tid_int))
        col_names = db.execute(
            select(ColumnMeta.column_name).where(ColumnMeta.table_id == tid_int)
        ).scalars().all()
        for name in col_names:
            subjects.append(column_iri(tid_int, str(name)))
            subjects.append(legacy_column_iri(tid_int, str(name)))
    return _purge_rdf_subjects(kb_id, subjects)


def _delete_pipeline_runs_for_source(
    db: Session,
    *,
    kb_id: int,
    source_type: str,
    source_id: int,
) -> tuple[int, int]:
    """Delete pipeline runs for a source and purge RDF subjects from step caches."""
    import shutil

    from services.extraction.step_cache import CACHED_EXTRACTION_STEPS, _cache_dir, load_step_triples

    full_type = source_type if source_type.startswith("source:") else f"source:{source_type}"
    runs = db.execute(
        select(PipelineRun).where(
            PipelineRun.knowledge_base_id == kb_id,
            PipelineRun.source_type == full_type,
            PipelineRun.source_id == source_id,
        )
    ).scalars().all()
    runs_deleted = 0
    purged = 0
    for run in runs:
        subjects: list[str] = []
        for step in CACHED_EXTRACTION_STEPS:
            for triple in load_step_triples(kb_id, run.id, step):
                subjects.append(str(triple.subject))
        purged += _purge_rdf_subjects(kb_id, subjects)
        shutil.rmtree(_cache_dir(kb_id, run.id), ignore_errors=True)
        db.delete(run)
        runs_deleted += 1
    return runs_deleted, purged


def _delete_single_pipeline_run(db: Session, run: PipelineRun) -> int:
    """Delete one pipeline run row and purge RDF subjects from its step cache."""
    import shutil

    from services.extraction.step_cache import CACHED_EXTRACTION_STEPS, _cache_dir, load_step_triples

    kb_id = int(run.knowledge_base_id)
    subjects: list[str] = []
    for step in CACHED_EXTRACTION_STEPS:
        for triple in load_step_triples(kb_id, run.id, step):
            subjects.append(str(triple.subject))
    purged = _purge_rdf_subjects(kb_id, subjects)
    shutil.rmtree(_cache_dir(kb_id, run.id), ignore_errors=True)
    db.delete(run)
    return purged


def _pipeline_binding_for_entry(entry: KnowledgeEntry) -> tuple[str, int]:
    meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
    kind = str(meta.get("kind") or "file")
    if kind == "manual":
        return "source:manual", int(entry.id)
    if kind in ("notion", "confluence", "feishu") or kind.endswith("_api"):
        raw = meta.get("api_source_id")
        try:
            if raw is not None:
                return "source:api", int(raw)
        except (TypeError, ValueError):
            pass
    return "source:file", int(entry.id)


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
    runs_deleted, purged_from_runs = _delete_pipeline_runs_for_source(
        db, kb_id=kb_id, source_type="source:git", source_id=source_id
    )
    stats.pipeline_runs_deleted = runs_deleted
    stats.assertion_subject_count += purged_from_runs
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
    runs_deleted, purged_from_runs = _delete_pipeline_runs_for_source(
        db, kb_id=kb_id, source_type="source:api", source_id=source_id
    )
    stats.pipeline_runs_deleted = runs_deleted
    stats.assertion_subject_count += purged_from_runs
    return stats


def cleanup_entry_in_kb(
    db: Session,
    *,
    kb_id: int,
    entry_id: int,
) -> CleanupStats:
    """Cascade-delete evidence, documents, RDF, and pipeline runs for a file/manual/API entry card."""
    entry = db.get(KnowledgeEntry, entry_id)
    if not entry or entry.knowledge_base_id != kb_id:
        return CleanupStats()

    meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
    kind = str(meta.get("kind") or "file")
    doc_ids = _collect_source_documents(
        db,
        kb_id=kb_id,
        entry_ids=[entry_id],
        source_kind=None,
        source_id_field="entry_id",
        source_id=entry_id,
    )
    chunk_ids = (
        db.execute(select(DocumentChunk.id).where(DocumentChunk.document_id.in_(doc_ids))).scalars().all()
        if doc_ids
        else []
    )

    stats = CleanupStats()

    def _entry_matcher(src: dict[str, Any]) -> bool:
        if str(src.get("entry_id") or "") == str(entry_id):
            return True
        api_id = meta.get("api_source_id")
        if api_id is not None and str(src.get("source_id") or src.get("api_source_id") or "") == str(api_id):
            return True
        return False

    stats.package_count = _delete_evidence_packages(
        db,
        kb_id=kb_id,
        source_matcher=_entry_matcher,
        linked_entry_ids={entry_id},
        linked_document_ids=set(doc_ids),
    )
    if doc_ids:
        docs = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
        for doc in docs:
            db.delete(doc)
        stats.document_count = len(docs)
    stats.assertion_subject_count = _purge_rdf_assertions_for_chunk_ids(
        kb_id,
        [int(x) for x in chunk_ids],
    )
    pipeline_type, pipeline_source_id = _pipeline_binding_for_entry(entry)
    runs_deleted, purged_from_runs = _delete_pipeline_runs_for_source(
        db,
        kb_id=kb_id,
        source_type=pipeline_type,
        source_id=pipeline_source_id,
    )
    stats.pipeline_runs_deleted = runs_deleted
    stats.assertion_subject_count += purged_from_runs
    delete_embeddings_for_knowledge_entries(db, [entry_id])
    db.delete(entry)
    stats.entry_count = 1
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

    di = db.get(KnowledgeDatabaseImport, import_id)
    if di is None:
        return CleanupStats()

    ds_id = di.datasource_id
    db_names_sorted = sorted(str(x) for x in (di.database_names or []))

    def _db_matcher(src: dict[str, Any]) -> bool:
        if str(src.get("import_id") or "") == str(import_id):
            return True
        if src.get("datasource_id") == ds_id:
            raw_names = src.get("database_names") or src.get("databases") or []
            if sorted(str(x) for x in raw_names) == db_names_sorted:
                return True
        return False

    stats = CleanupStats()
    stats.package_count = _delete_evidence_packages(
        db,
        kb_id=kb_id,
        source_matcher=_db_matcher,
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
    stats.assertion_subject_count += _purge_physical_tables_for_import(db, kb_id=kb_id, di=di)
    runs_deleted, purged_from_runs = _delete_pipeline_runs_for_source(
        db,
        kb_id=kb_id,
        source_type="source:database",
        source_id=import_id,
    )
    stats.pipeline_runs_deleted = runs_deleted
    stats.assertion_subject_count += purged_from_runs
    return stats


@dataclass
class SourceIndexes:
    valid_doc: set[tuple[int, int]] = field(default_factory=set)
    valid_entry: set[tuple[int, int]] = field(default_factory=set)
    valid_git: set[tuple[int, int]] = field(default_factory=set)
    valid_git_repo: set[tuple[int, str, str, str]] = field(default_factory=set)
    valid_import: set[tuple[int, int]] = field(default_factory=set)
    valid_api: set[int] = field(default_factory=set)


def _build_source_indexes(db: Session) -> SourceIndexes:
    return SourceIndexes(
        valid_doc={
            (int(kb), int(doc_id))
            for kb, doc_id in db.execute(select(Document.knowledge_base_id, Document.id)).all()
        },
        valid_entry={
            (int(kb), int(entry_id))
            for kb, entry_id in db.execute(select(KnowledgeEntry.knowledge_base_id, KnowledgeEntry.id)).all()
        },
        valid_git={
            (int(kb), int(source_id))
            for kb, source_id in db.execute(
                select(KnowledgeGitSource.knowledge_base_id, KnowledgeGitSource.id)
            ).all()
        },
        valid_git_repo={
            (
                int(row.knowledge_base_id),
                str(row.owner or "").strip().lower(),
                str(row.repo or "").strip().lower(),
                str(row.branch or "").strip(),
            )
            for row in db.execute(select(KnowledgeGitSource)).scalars().all()
        },
        valid_import={
            (int(kb), int(import_id))
            for kb, import_id in db.execute(
                select(KnowledgeDatabaseImport.knowledge_base_id, KnowledgeDatabaseImport.id)
            ).all()
        },
        valid_api={
            int(source_id)
            for source_id in db.execute(select(KnowledgeApiSource.id)).scalars().all()
        },
    )


def _evidence_package_is_orphan(row: EvidencePackage, idx: SourceIndexes) -> bool:
    kb_id = int(row.knowledge_base_id)
    src = row.source_ref if isinstance(row.source_ref, dict) else {}
    remove = False

    if row.connector == "git":
        git_id = src.get("git_source_id")
        if git_id is not None:
            try:
                remove = (kb_id, int(git_id)) not in idx.valid_git
            except (TypeError, ValueError):
                remove = True
        else:
            owner = str(src.get("owner") or "").strip().lower()
            repo = str(src.get("repo") or "").strip().lower()
            branch = str(src.get("branch") or "").strip()
            if owner and repo:
                remove = (
                    (kb_id, owner, repo, branch) not in idx.valid_git_repo
                    and (kb_id, owner, repo, "") not in idx.valid_git_repo
                )
    elif row.connector == "database":
        import_id = src.get("import_id")
        if import_id is not None:
            try:
                remove = (kb_id, int(import_id)) not in idx.valid_import
            except (TypeError, ValueError):
                remove = True
    elif row.connector == "api":
        api_source_id = src.get("source_id")
        if api_source_id is None:
            api_source_id = src.get("api_source_id")
        if api_source_id is not None:
            try:
                remove = int(api_source_id) not in idx.valid_api
            except (TypeError, ValueError):
                remove = True
    elif row.connector in ("file", "manual", "ttl"):
        entry_id = src.get("entry_id")
        if entry_id is not None:
            try:
                remove = (kb_id, int(entry_id)) not in idx.valid_entry
            except (TypeError, ValueError):
                remove = True
        elif row.connector == "file":
            has_file_ref = bool(str(src.get("filename") or src.get("ref") or "").strip())
            has_entry_ref = src.get("entry_id") is not None
            has_doc_ref = src.get("document_id") is not None or row.linked_document_id is not None
            has_linked_entries = isinstance(row.linked_entry_ids, list) and len(row.linked_entry_ids) > 0
            if not (has_file_ref or has_entry_ref or has_doc_ref or has_linked_entries):
                remove = True

    if not remove and row.linked_document_id is not None:
        remove = (kb_id, int(row.linked_document_id)) not in idx.valid_doc

    if not remove and isinstance(row.linked_entry_ids, list) and row.linked_entry_ids:
        existing_linked = 0
        for item in row.linked_entry_ids:
            try:
                if (kb_id, int(item)) in idx.valid_entry:
                    existing_linked += 1
            except (TypeError, ValueError):
                continue
        remove = existing_linked == 0

    return remove


def cleanup_orphan_evidence_packages(
    db: Session,
    *,
    kb_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Best-effort cleanup for stale EvidencePackage rows left by legacy deletion flows."""
    q = select(EvidencePackage)
    if kb_id is not None:
        q = q.where(EvidencePackage.knowledge_base_id == kb_id)
    rows = db.execute(q).scalars().all()
    if not rows:
        return {"scanned": 0, "deleted": 0}

    idx = _build_source_indexes(db)
    deleted = 0
    for row in rows:
        if not _evidence_package_is_orphan(row, idx):
            continue
        if dry_run:
            deleted += 1
            continue
        db.delete(row)
        deleted += 1

    return {"scanned": len(rows), "deleted": deleted}


def _document_is_orphan(doc: Document, idx: SourceIndexes) -> bool:
    kb_id = int(doc.knowledge_base_id)
    if doc.knowledge_entry_id is not None:
        try:
            if (kb_id, int(doc.knowledge_entry_id)) not in idx.valid_entry:
                return True
        except (TypeError, ValueError):
            return True

    meta = doc.source_meta if isinstance(doc.source_meta, dict) else {}
    git_id = meta.get("git_source_id")
    if git_id is not None:
        try:
            if (kb_id, int(git_id)) not in idx.valid_git:
                return True
        except (TypeError, ValueError):
            return True

    api_id = meta.get("api_source_id")
    if api_id is not None:
        try:
            if int(api_id) not in idx.valid_api:
                return True
        except (TypeError, ValueError):
            return True

    import_id = meta.get("import_id")
    if import_id is not None:
        try:
            if (kb_id, int(import_id)) not in idx.valid_import:
                return True
        except (TypeError, ValueError):
            return True

    return False


def cleanup_orphan_documents(
    db: Session,
    *,
    kb_id: int,
    dry_run: bool = False,
) -> dict[str, int]:
    """Remove documents whose entry or import-source linkage no longer exists."""
    idx = _build_source_indexes(db)
    docs = db.execute(select(Document).where(Document.knowledge_base_id == kb_id)).scalars().all()
    deleted = 0
    assertions_purged = 0
    for doc in docs:
        if not _document_is_orphan(doc, idx):
            continue
        chunk_ids = list(
            db.execute(select(DocumentChunk.id).where(DocumentChunk.document_id == doc.id)).scalars().all()
        )
        if dry_run:
            deleted += 1
            continue
        assertions_purged += _purge_rdf_assertions_for_chunk_ids(kb_id, [int(c) for c in chunk_ids])
        db.delete(doc)
        deleted += 1
    return {"scanned": len(docs), "deleted": deleted, "assertions_purged": assertions_purged}


def cleanup_orphan_git_entries(
    db: Session,
    *,
    kb_id: int,
    dry_run: bool = False,
) -> dict[str, int]:
    """Remove git_file entries whose git source row was already deleted."""
    idx = _build_source_indexes(db)
    entries = db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
        )
    ).scalars().all()
    deleted = 0
    agg_assertions = 0
    for entry in entries:
        meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
        raw_git = meta.get("git_source_id")
        try:
            git_id = int(raw_git)
        except (TypeError, ValueError):
            continue
        if (kb_id, git_id) in idx.valid_git:
            continue
        if dry_run:
            deleted += 1
            continue
        stats = cleanup_entry_in_kb(db, kb_id=kb_id, entry_id=int(entry.id))
        deleted += stats.entry_count
        agg_assertions += stats.assertion_subject_count
    return {"scanned": len(entries), "deleted": deleted, "assertions_purged": agg_assertions}


def _pipeline_run_source_missing(run: PipelineRun, idx: SourceIndexes) -> bool:
    if not run.source_type or run.source_id is None:
        return False
    kb_id = int(run.knowledge_base_id)
    source_id = int(run.source_id)
    src = run.source_type.removeprefix("source:")
    if src == "git":
        return (kb_id, source_id) not in idx.valid_git
    if src == "api":
        return source_id not in idx.valid_api
    if src == "database":
        return (kb_id, source_id) not in idx.valid_import
    if src in ("file", "manual"):
        return (kb_id, source_id) not in idx.valid_entry
    return False


def cleanup_orphan_pipeline_runs(
    db: Session,
    *,
    kb_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Delete pipeline runs that reference import sources which no longer exist."""
    q = select(PipelineRun)
    if kb_id is not None:
        q = q.where(PipelineRun.knowledge_base_id == kb_id)
    runs = db.execute(q).scalars().all()
    idx = _build_source_indexes(db)
    deleted = 0
    assertions_purged = 0
    for run in runs:
        if not _pipeline_run_source_missing(run, idx):
            continue
        if dry_run:
            deleted += 1
            continue
        assertions_purged += _delete_single_pipeline_run(db, run)
        deleted += 1
    return {"scanned": len(runs), "deleted": deleted, "assertions_purged": assertions_purged}


def _chunk_ids_referenced_in_graph(kb_id: int) -> set[int]:
    graph = kb_graph_iri(kb_id)
    store = get_triple_store()
    chunk_iris: set[str] = set()
    if store.use_fuseki_backend():
        rows = store.sparql_query(
            f"""
            PREFIX dl: <{NS}>
            SELECT DISTINCT ?chunk WHERE {{
              GRAPH <{graph}> {{
                {{ ?s dl:groundedBy ?chunk }} UNION {{ ?s dl:sourceChunk ?chunk }}
              }}
            }}
            """
        )
        for row in rows:
            iri = str(row.get("chunk", "")).strip()
            if iri:
                chunk_iris.add(iri)
    else:
        g = store.get_named_graph(graph)
        for pred in (_DL_GROUNDED_BY, _DL_SOURCE_CHUNK):
            for _subj, _pred, obj in g.triples((None, pred, None)):
                if isinstance(obj, URIRef):
                    chunk_iris.add(str(obj))

    out: set[int] = set()
    for iri in chunk_iris:
        m = _CHUNK_ID_FROM_IRI.search(iri)
        if m:
            out.add(int(m.group(1)))
    return out


def cleanup_orphan_rdf_chunks(
    db: Session,
    *,
    kb_id: int,
    dry_run: bool = False,
) -> dict[str, int]:
    """Purge ontology assertions grounded on document chunks that no longer exist in PostgreSQL."""
    valid = {
        int(cid)
        for cid in db.execute(
            select(DocumentChunk.id).where(DocumentChunk.knowledge_base_id == kb_id)
        ).scalars().all()
    }
    referenced = _chunk_ids_referenced_in_graph(kb_id)
    orphan_ids = sorted(referenced - valid)
    if dry_run or not orphan_ids:
        return {
            "orphan_chunk_ids": len(orphan_ids),
            "assertions_purged": 0,
        }
    purged = _purge_rdf_assertions_for_chunk_ids(kb_id, orphan_ids)
    return {"orphan_chunk_ids": len(orphan_ids), "assertions_purged": purged}


def cleanup_legacy_orphans(
    db: Session,
    *,
    kb_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run all legacy orphan cleanups (evidence packages, documents, entries, pipeline runs, RDF)."""
    from models import KnowledgeBase

    if kb_id is not None:
        kb_ids = [kb_id]
    else:
        kb_ids = [int(x) for x in db.execute(select(KnowledgeBase.id)).scalars().all()]

    report: dict[str, Any] = {
        "dry_run": dry_run,
        "kb_ids": kb_ids,
        "evidence_packages": cleanup_orphan_evidence_packages(db, kb_id=kb_id, dry_run=dry_run),
        "pipeline_runs": cleanup_orphan_pipeline_runs(db, kb_id=kb_id, dry_run=dry_run),
        "per_kb": [],
    }

    for kid in kb_ids:
        per_kb: dict[str, Any] = {"kb_id": kid}
        per_kb["documents"] = cleanup_orphan_documents(db, kb_id=kid, dry_run=dry_run)
        per_kb["git_entries"] = cleanup_orphan_git_entries(db, kb_id=kid, dry_run=dry_run)
        per_kb["rdf_chunks"] = cleanup_orphan_rdf_chunks(db, kb_id=kid, dry_run=dry_run)
        report["per_kb"].append(per_kb)

    if not dry_run:
        db.flush()
    _logger.info("Legacy orphan cleanup complete: %s", report)
    return report
