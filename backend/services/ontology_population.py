"""Populate ontology ABox from documents, analyze results, and legacy tables."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    ColumnMeta,
    DocumentChunk,
    TableMeta,
    TableSummary,
)
# BusinessTerm, DataLineage, MetricDefinition, SemanticRelation removed in Phase 1
from ontology import (
    NS,
    chunk_iri,
    column_iri,
    concept_iri,
    concept_slug,
    datasource_iri,
    kb_graph_iri,
    legacy_column_iri,
    legacy_table_iri,
    metric_iri,
    table_iri,
    term_iri,
)
from services.ontology_entity_linker import resolve_grounding_to_iris
from services.ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result
from services.ontology_store import add_triple, insert_graph

SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEF = "http://www.w3.org/2004/02/skos/core#definition"
SKOS_ALT = "http://www.w3.org/2004/02/skos/core#altLabel"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _ttl_string_literal(value: str, *, max_len: int | None = None) -> str:
    """Escape text for Turtle double-quoted literals."""
    s = value[:max_len] if max_len is not None else value
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
        .replace("\t", "\\t")
    )


def triples_from_semantic_meta(
    meta: dict[str, Any],
    *,
    chunk_id: int,
    kb_id: int,
    domain_id: int | None,
    domain_tables: list[TableMeta],
) -> list[RawTriple]:
    """Convert chunk semantic_meta JSON to RawTriple list."""
    role = meta.get("semantic_role") or "general_reference"
    conf = float(meta.get("confidence", 70))
    grounding = meta.get("grounding") if isinstance(meta.get("grounding"), dict) else {}
    graph = kb_graph_iri(kb_id)
    chunk = chunk_iri(chunk_id)
    triples: list[RawTriple] = []

    linked = resolve_grounding_to_iris(None, grounding, domain_tables)

    if role == "business_metric":
        mid = metric_iri(domain_id or kb_id, concept_slug(f"chunk_{chunk_id}", "metric"))
        triples.append(RawTriple(mid, RDF_TYPE, f"{NS}Metric", True, graph=graph, confidence=conf))
        triples.append(RawTriple(mid, f"{NS}sourceChunk", chunk, True, graph=graph, confidence=conf))
        for ti in linked["table_iris"]:
            triples.append(RawTriple(mid, f"{NS}computedFromTable", ti, True, graph=graph, confidence=conf))

    if role == "join_guide":
        for idx, edge in enumerate(meta.get("join_edges") or []):
            if not isinstance(edge, dict):
                continue
            jid = f"{NS}join/{kb_id}/{chunk_id}/{idx}"
            triples.append(RawTriple(jid, RDF_TYPE, f"{NS}JoinRelation", True, graph=graph, confidence=conf))
            left_ref = str(edge.get("left") or "")
            right_ref = str(edge.get("right") or "")
            on = str(edge.get("on") or "")
            li, _, _ = resolve_table_ref_from_domain(left_ref, domain_tables)
            ri, _, _ = resolve_table_ref_from_domain(right_ref, domain_tables)
            if li:
                triples.append(RawTriple(jid, f"{NS}leftTable", li, True, graph=graph, confidence=conf))
            if ri:
                triples.append(RawTriple(jid, f"{NS}rightTable", ri, True, graph=graph, confidence=conf))
            if on:
                triples.append(RawTriple(jid, f"{NS}joinKey", on, False, lang="zh", graph=graph, confidence=conf))
            if li and ri:
                triples.append(RawTriple(li, f"{NS}joinableWith", ri, True, graph=graph, confidence=conf))

    if role == "column_glossary":
        for col_iri in linked["column_iris"]:
            tid = concept_slug(col_iri, "column")
            term = term_iri(domain_id or kb_id, tid)
            triples.append(RawTriple(term, RDF_TYPE, f"{NS}BusinessTerm", True, graph=graph, confidence=conf))
            triples.append(RawTriple(term, f"{NS}mapsToColumn", col_iri, True, graph=graph, confidence=conf))

    return triples


def resolve_table_ref_from_domain(ref: str, domain_tables: list[TableMeta]) -> tuple[str | None, str, float]:
    from services.ontology_entity_linker import resolve_table_ref
    return resolve_table_ref(ref, domain_tables)


def populate_from_document(
    db: Session,
    document_id: int,
    *,
    kb_id: int,
    domain_tables: list[TableMeta] | None = None,
    domain_id: int | None = None,
) -> dict[str, Any]:
    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).scalars().all()
    all_triples: list[RawTriple] = []
    for chunk in chunks:
        meta = chunk.semantic_meta if isinstance(chunk.semantic_meta, dict) else {}
        if not meta:
            continue
        all_triples.extend(
            triples_from_semantic_meta(
                meta,
                chunk_id=chunk.id,
                kb_id=kb_id,
                domain_id=domain_id,
                domain_tables=domain_tables or [],
            )
        )
    result = clean_triples(all_triples, kb_id=kb_id, domain_tables=domain_tables or [])
    return persist_clean_result(result, kb_id)


def _purge_physical_table_subjects(db: Session, table_id: int, kb_id: int) -> None:
    """Remove prior PhysicalTable/Column assertions (incl. legacy wrong IRI prefix)."""
    from services.source_cascade_cleanup import _purge_rdf_subjects

    subjects: list[str] = [table_iri(table_id), legacy_table_iri(table_id)]
    col_names = db.execute(
        select(ColumnMeta.column_name).where(ColumnMeta.table_id == table_id)
    ).scalars().all()
    for name in col_names:
        cn = str(name)
        subjects.append(column_iri(table_id, cn))
        subjects.append(legacy_column_iri(table_id, cn))
    _purge_rdf_subjects(kb_id, subjects)


def sync_physical_table_to_ontology(
    db: Session,
    table_id: int,
    kb_id: int,
    *,
    datasource_id: int | None = None,
) -> dict[str, Any]:
    """Write PhysicalTable / Column semantics from analyze results (clean → SHACL → production graph)."""
    table = db.get(TableMeta, table_id)
    if table is None:
        return {"written": 0, "shacl_blocked": False, "literal_count": 0}

    _purge_physical_table_subjects(db, table_id, kb_id)

    graph = kb_graph_iri(kb_id)
    ti = table_iri(table_id)
    triples: list[RawTriple] = [
        RawTriple(ti, RDF_TYPE, f"{NS}PhysicalTable", True, graph=graph),
        RawTriple(ti, f"{NS}platformId", str(table_id), False, graph=graph),
        RawTriple(ti, f"{NS}sensitivityLevel", "internal", False, graph=graph),
    ]
    if table.datasource_id:
        ds_id = int(table.datasource_id)
    elif datasource_id is not None:
        ds_id = int(datasource_id)
    else:
        ds_id = None
    if ds_id is not None:
        triples.append(
            RawTriple(
                ti,
                f"{NS}belongsToDataSource",
                datasource_iri(ds_id),
                True,
                graph=graph,
            )
        )
    table_label = (table.table_name or "").strip() or f"table_{table_id}"
    triples.append(RawTriple(ti, SKOS_PREF, table_label, False, lang="zh", graph=graph))
    if table.row_count is not None and table.row_count > 0:
        triples.append(RawTriple(ti, f"{NS}rowCount", str(int(table.row_count)), False, graph=graph))

    summary = db.execute(
        select(TableSummary).where(TableSummary.table_id == table_id).order_by(TableSummary.generated_at.desc())
    ).scalars().first()
    if summary and summary.summary:
        triples.append(
            RawTriple(ti, f"{NS}businessSummary", summary.summary[:8000], False, lang="zh", graph=graph)
        )

    cols = db.execute(select(ColumnMeta).where(ColumnMeta.table_id == table_id)).scalars().all()
    for col in cols:
        ci = column_iri(table_id, col.column_name)
        triples.append(RawTriple(ci, RDF_TYPE, f"{NS}PhysicalColumn", True, graph=graph))
        triples.append(RawTriple(ci, "https://schema.org/isPartOf", ti, True, graph=graph))
        triples.append(RawTriple(ci, SKOS_PREF, col.column_name, False, lang="zh", graph=graph))
        if col.data_type:
            triples.append(RawTriple(ci, f"{NS}dataType", col.data_type, False, graph=graph))
        if col.comment:
            triples.append(RawTriple(ci, f"{NS}semanticDescription", col.comment, False, lang="zh", graph=graph))
        elif col.semantic_desc:
            triples.append(RawTriple(ci, f"{NS}semanticDescription", col.semantic_desc, False, lang="zh", graph=graph))
        if col.semantic_type:
            triples.append(RawTriple(ci, f"{NS}semanticType", col.semantic_type, False, graph=graph))

    cleaned = clean_triples(triples, kb_id=kb_id)
    persisted = persist_clean_result(cleaned, kb_id)
    literal_count = sum(1 for t in cleaned.production if not t.object_is_uri)
    return {
        "written": int(persisted.get("written") or 0),
        "shacl_blocked": bool(persisted.get("shacl_blocked")),
        "literal_count": literal_count,
        "quarantined": int(persisted.get("quarantined") or 0),
    }


def migrate_legacy_entities_to_triples(db: Session, kb_id: int, domain_id: int = 0) -> list[RawTriple]:
    """Build RawTriple list from legacy PostgreSQL semantic tables."""
    triples: list[RawTriple] = []
    graph = kb_graph_iri(kb_id)

    for term in db.execute(select(BusinessTerm).where(BusinessTerm.knowledge_base_id == kb_id)).scalars():
        slug = term.concept_id or concept_slug(term.name, "term")
        subj = term_iri(domain_id or kb_id, slug.replace("term.", ""))
        triples.append(RawTriple(subj, RDF_TYPE, f"{NS}BusinessTerm", True, graph=graph, confidence=term.confidence))
        triples.append(RawTriple(subj, SKOS_PREF, term.name, False, lang="zh", graph=graph, confidence=term.confidence))
        triples.append(RawTriple(subj, SKOS_DEF, term.definition, False, lang="zh", graph=graph, confidence=term.confidence))
        triples.append(RawTriple(subj, f"{NS}approvalStatus", term.status if term.status == "approved" else "draft", False, graph=graph))
        for field in term.related_fields or []:
            triples.append(RawTriple(subj, f"{NS}mapsToColumn", str(field), False, graph=graph))

    for metric in db.execute(select(MetricDefinition).where(MetricDefinition.knowledge_base_id == kb_id)).scalars():
        slug = metric.concept_id or concept_slug(metric.name, "metric")
        subj = metric_iri(domain_id or kb_id, slug.replace("metric.", ""))
        triples.append(RawTriple(subj, RDF_TYPE, f"{NS}Metric", True, graph=graph, confidence=metric.confidence))
        triples.append(RawTriple(subj, SKOS_PREF, metric.name, False, lang="zh", graph=graph))
        triples.append(RawTriple(subj, f"{NS}formula", metric.formula, False, lang="zh", graph=graph))
        if metric.caliber:
            triples.append(RawTriple(subj, f"{NS}caliber", metric.caliber, False, lang="zh", graph=graph))
        triples.append(RawTriple(subj, f"{NS}approvalStatus", metric.status if metric.status == "approved" else "draft", False, graph=graph))
        for ref in metric.bound_table_refs or []:
            triples.append(RawTriple(subj, f"{NS}computedFromTable", str(ref), False, graph=graph))

    for lg in db.execute(select(DataLineage).where(DataLineage.knowledge_base_id == kb_id)).scalars():
        # Store as joinableWith using table name refs — entity linker resolves on clean
        src, tgt = lg.source_table, lg.target_table
        if src and tgt:
            triples.append(RawTriple(f"{NS}lineage/{lg.id}", f"{NS}transformsFrom", tgt, False, graph=graph, source_type="code"))

    for rel in db.execute(select(SemanticRelation).where(SemanticRelation.knowledge_base_id == kb_id)).scalars():
        pred_map = {
            "term_column": f"{NS}mapsToColumn",
            "metric_table": f"{NS}computedFromTable",
            "table_join": f"{NS}joinableWith",
            "concept_alias": SKOS_ALT,
        }
        pred = pred_map.get(rel.relation_type)
        if pred:
            subj = concept_iri(rel.source_ref) if rel.source_type == "concept" else f"{NS}entity/{rel.source_ref}"
            triples.append(RawTriple(subj, pred, rel.target_ref, False, graph=graph, confidence=rel.confidence))

    return triples
