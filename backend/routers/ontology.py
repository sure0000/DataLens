"""Ontology API: SPARQL proxy, TTL import/export, quarantine, CRUD."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models import BusinessTerm, DataLineage, KnowledgeBase, MetricDefinition, SemanticRelation
from ontology import NS, kb_graph_iri, quarantine_graph_iri
from services.ontology_loader import init_ontology
from services.ontology_population import migrate_legacy_entities_to_triples, populate_from_document
from services.ontology_rdf_browser import fetch_kb_rdf_view
from services.ontology_reasoning import materialize_inferred_closure
from services.ontology_store import export_graph_ttl, graph_stats, insert_graph, sparql_query
from services.ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result
from services.ontology_validation import validate_ttl

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


class SparqlRequest(BaseModel):
    query: str
    kb_id: int | None = None


class TtlImportRequest(BaseModel):
    ttl: str
    kb_id: int
    replace: bool = False


class QuarantineResolveRequest(BaseModel):
    kb_id: int
    subject: str
    predicate: str
    object: str
    object_is_uri: bool = False
    approve: bool = True


class TermOntologyCreate(BaseModel):
    name: str
    definition: str = ""
    related_fields: list[str] = Field(default_factory=list)
    confidence: float = 80.0
    status: str = "approved"


class MetricOntologyCreate(BaseModel):
    name: str
    formula: str
    caliber: str | None = None
    bound_table_refs: list[str] = Field(default_factory=list)
    confidence: float = 80.0
    status: str = "approved"


@router.get("/health")
def ontology_health() -> dict:
    init_ontology()
    return {"ok": True, **graph_stats()}


@router.post("/sparql")
def run_sparql(body: SparqlRequest) -> dict:
    settings = get_settings()
    if not settings.ontology_enabled:
        raise HTTPException(status_code=503, detail="Ontology disabled")
    try:
        rows = sparql_query(body.query)
        return {"ok": True, "results": rows}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge-bases/{kb_id}/export")
def export_kb_ontology(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    graph = kb_graph_iri(kb_id)
    ttl = export_graph_ttl(graph)
    return {"ok": True, "kb_id": kb_id, "graph": graph, "ttl": ttl}


@router.post("/knowledge-bases/{kb_id}/import")
def import_kb_ontology(kb_id: int, body: TtlImportRequest, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    report = validate_ttl(body.ttl)
    if not report.get("conforms") and not report.get("skipped"):
        return {"ok": False, "shacl": report}
    if body.replace:
        from services.ontology_store import delete_graph
        delete_graph(kb_graph_iri(kb_id))
    insert_graph(kb_graph_iri(kb_id), body.ttl)
    return {"ok": True, "shacl": report}


@router.post("/knowledge-bases/{kb_id}/sync-from-legacy")
def sync_from_legacy(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """Migrate legacy PostgreSQL semantic tables into Fuseki RDF store."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from services.ontology_sync_service import sync_knowledge_base_to_rdf

    out = sync_knowledge_base_to_rdf(db, kb_id)
    return {"ok": True, **out}


@router.post("/knowledge-bases/{kb_id}/documents/{document_id}/assert")
def assert_document_ontology(
    kb_id: int, document_id: int, db: Session = Depends(get_db)
) -> dict:
    from services.context_builder import tables_from_business_domain
    from models import BusinessDomainKnowledgeBase, Document

    doc = db.get(Document, document_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    domain_id = None
    domain_row = db.execute(
        select(BusinessDomainKnowledgeBase.domain_id).where(
            BusinessDomainKnowledgeBase.knowledge_base_id == kb_id
        )
    ).first()
    domain_tables = []
    if domain_row:
        domain_id = int(domain_row[0])
        domain_tables = tables_from_business_domain(db, domain_id)
    return populate_from_document(db, document_id, kb_id=kb_id, domain_tables=domain_tables, domain_id=domain_id)


@router.get("/knowledge-bases/{kb_id}/quarantine")
def list_quarantine(kb_id: int) -> dict:
    graph = quarantine_graph_iri(kb_id)
    q = f"""
PREFIX dl: <{NS}>
SELECT ?q ?reason ?raw WHERE {{
  GRAPH <{graph}> {{
    ?q a dl:QuarantinedAssertion ;
       dl:rejectReason ?reason .
    OPTIONAL {{ ?q dl:rawTriple ?raw }}
  }}
}}"""
    try:
        rows = sparql_query(q)
    except Exception:
        rows = []
    return {"ok": True, "items": rows}


@router.post("/quarantine/{item_idx}/resolve")
def resolve_quarantine(item_idx: int, body: QuarantineResolveRequest) -> dict:
    if not body.approve:
        return {"ok": True, "action": "rejected"}
    triple = RawTriple(
        body.subject,
        body.predicate,
        body.object,
        body.object_is_uri,
        graph=kb_graph_iri(body.kb_id),
        confidence=90.0,
    )
    result = clean_triples([triple], kb_id=body.kb_id)
    out = persist_clean_result(result, body.kb_id)
    return {"ok": True, **out}


@router.get("/knowledge-bases/{kb_id}/rdf-view")
def get_kb_rdf_view(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """Entities stored in RDF named graphs (production + quarantine stats)."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    try:
        rdf = fetch_kb_rdf_view(kb_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RDF 查询失败: {exc}") from exc
    return {"ok": True, "kb_id": kb_id, "kb_name": kb.name, **rdf, "store": graph_stats()}


@router.get("/knowledge-bases/{kb_id}/graph")
def get_ontology_graph(kb_id: int, db: Session = Depends(get_db)) -> dict:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    graph_iri = kb_graph_iri(kb_id)
    nodes: list[dict] = []
    edges: list[dict] = []
    rdf_view: dict | None = None
    try:
        rdf_view = fetch_kb_rdf_view(kb_id)
        for t in rdf_view.get("production", {}).get("terms", []):
            nodes.append({
                "id": t["iri"],
                "type": "term",
                "label": t["label"],
                "status": t.get("status"),
                "source": "rdf",
            })
        for m in rdf_view.get("production", {}).get("metrics", []):
            nodes.append({
                "id": m["iri"],
                "type": "metric",
                "label": m["label"],
                "status": m.get("status"),
                "source": "rdf",
            })
        for tbl in rdf_view.get("production", {}).get("physical_tables", []):
            nodes.append({
                "id": tbl["iri"],
                "type": "physical_table",
                "label": tbl.get("summary")[:40] if tbl.get("summary") else f"表 #{tbl.get('platform_id')}",
                "status": "rdf",
                "source": "rdf",
                "platform_id": tbl.get("platform_id"),
            })
    except Exception:
        rdf_view = None

    # PostgreSQL 语义表（编辑源；RDF 生产图为空时仍可在页面浏览）
    terms = db.execute(select(BusinessTerm).where(BusinessTerm.knowledge_base_id == kb_id)).scalars().all()
    for t in terms:
        nodes.append({
            "id": f"term:{t.id}",
            "type": "term",
            "label": t.name,
            "status": t.status,
            "source": "postgresql",
        })
    metrics = db.execute(select(MetricDefinition).where(MetricDefinition.knowledge_base_id == kb_id)).scalars().all()
    for m in metrics:
        nodes.append({
            "id": f"metric:{m.id}",
            "type": "metric",
            "label": m.name,
            "status": m.status,
            "source": "postgresql",
        })
    rels = db.execute(select(SemanticRelation).where(SemanticRelation.knowledge_base_id == kb_id)).scalars().all()
    for r in rels:
        edges.append({
            "id": f"rel:{r.id}",
            "type": r.relation_type,
            "source": r.source_ref,
            "target": r.target_ref,
        })
    lineages = db.execute(select(DataLineage).where(DataLineage.knowledge_base_id == kb_id)).scalars().all()
    for lg in lineages:
        edges.append({
            "id": f"lineage:{lg.id}",
            "type": "lineage",
            "source": lg.source_table,
            "target": lg.target_table,
        })

    return {
        "ok": True,
        "graph_iri": graph_iri,
        "nodes": nodes,
        "edges": edges,
        "rdf": rdf_view,
        "store": graph_stats(),
    }


# Backward-compatible term/metric CRUD writing to both PG (deprecated) and ontology

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEF = "http://www.w3.org/2004/02/skos/core#definition"


@router.get("/knowledge-bases/{kb_id}/terms")
def list_terms(kb_id: int, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(BusinessTerm).where(BusinessTerm.knowledge_base_id == kb_id).order_by(BusinessTerm.name)
    ).scalars().all()
    return {
        "terms": [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "definition": t.definition,
                "related_fields": t.related_fields or [],
                "concept_id": t.concept_id,
                "confidence": t.confidence,
                "status": t.status,
            }
            for t in rows
        ]
    }


@router.post("/knowledge-bases/{kb_id}/terms")
def create_term(kb_id: int, body: TermOntologyCreate, db: Session = Depends(get_db)) -> dict:
    from ontology import concept_slug, term_iri

    term = BusinessTerm(
        knowledge_base_id=kb_id,
        name=body.name,
        type="other",
        definition=body.definition,
        related_fields=body.related_fields,
        confidence=body.confidence,
        status=body.status,
        concept_id=concept_slug(body.name, "term"),
    )
    db.add(term)
    db.commit()
    db.refresh(term)

    slug = concept_slug(body.name, "term").replace("term.", "")
    subj = term_iri(kb_id, slug)
    ttl = f"""
<{subj}> <{RDF_TYPE}> <{NS}BusinessTerm> .
<{subj}> <{SKOS_PREF}> "{body.name.replace(chr(34), chr(92)+chr(34))}"@zh .
<{subj}> <{SKOS_DEF}> "{body.definition.replace(chr(34), chr(92)+chr(34))}"@zh .
<{subj}> <{NS}approvalStatus> "{body.status}" .
"""
    insert_graph(kb_graph_iri(kb_id), ttl)
    return {"ok": True, "term_id": term.id, "iri": subj}


@router.get("/knowledge-bases/{kb_id}/metrics")
def list_metrics(kb_id: int, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(MetricDefinition).where(MetricDefinition.knowledge_base_id == kb_id).order_by(MetricDefinition.name)
    ).scalars().all()
    return {
        "metrics": [
            {
                "id": m.id,
                "name": m.name,
                "formula": m.formula,
                "caliber": m.caliber,
                "bound_table_refs": m.bound_table_refs or [],
                "concept_id": m.concept_id,
                "confidence": m.confidence,
                "status": m.status,
            }
            for m in rows
        ]
    }


@router.post("/knowledge-bases/{kb_id}/metrics")
def create_metric(kb_id: int, body: MetricOntologyCreate, db: Session = Depends(get_db)) -> dict:
    from ontology import concept_slug, metric_iri

    metric = MetricDefinition(
        knowledge_base_id=kb_id,
        name=body.name,
        formula=body.formula,
        caliber=body.caliber,
        bound_table_refs=body.bound_table_refs,
        confidence=body.confidence,
        status=body.status,
        concept_id=concept_slug(body.name, "metric"),
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)

    slug = concept_slug(body.name, "metric").replace("metric.", "")
    subj = metric_iri(kb_id, slug)
    esc_name = body.name.replace('"', '\\"')
    esc_formula = body.formula.replace('"', '\\"')
    ttl = f"""
<{subj}> <{RDF_TYPE}> <{NS}Metric> .
<{subj}> <{SKOS_PREF}> "{esc_name}"@zh .
<{subj}> <{NS}formula> "{esc_formula}"@zh .
<{subj}> <{NS}approvalStatus> "{body.status}" .
"""
    insert_graph(kb_graph_iri(kb_id), ttl)
    return {"ok": True, "metric_id": metric.id, "iri": subj}
