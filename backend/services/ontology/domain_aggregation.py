"""Aggregate ontology presentation data across knowledge bases in a business domain."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BusinessDomain, BusinessDomainKnowledgeBase, Document, DocumentChunk, KnowledgeBase
from ontology import NS, kb_graph_iri
from services.context_builder import kb_ids_for_business_domain
from services.ontology.modeling_status import get_modeling_status
from services.ontology.provenance import build_entity_origin, fetch_grounded_sources
from services.ontology.reader import OntologyReader
from services.ontology.views import view_graph, view_lineage
from services.ontology_rdf_browser import fetch_kb_rdf_view
from services.ontology_store import sparql_query
from services.triple_store import get_triple_store

_logger = logging.getLogger(__name__)


def _reader() -> OntologyReader:
    return OntologyReader(get_triple_store())


def _domain_kb_rows(db: Session, domain_id: int) -> list[KnowledgeBase]:
    kb_ids = kb_ids_for_business_domain(db, domain_id)
    if not kb_ids:
        return []
    rows = db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))).scalars().all()
    by_id = {r.id: r for r in rows}
    return [by_id[i] for i in kb_ids if i in by_id]


def _normalize_term(raw: dict[str, Any], kb: KnowledgeBase, idx: int, sources: dict[str, dict]) -> dict[str, Any]:
    iri = raw.get("iri", "")
    src = sources.get(iri, {})
    return {
        "id": kb.id * 1_000_000 + idx,
        "iri": iri,
        "name": raw.get("label", ""),
        "type": "other",
        "definition": raw.get("definition", ""),
        "related_fields": [],
        "concept_id": None,
        "confidence": float(raw.get("confidence") or 0),
        "status": raw.get("status") or "draft",
        "origin": build_entity_origin(kb, src),
    }


def _normalize_metric(raw: dict[str, Any], kb: KnowledgeBase, idx: int, sources: dict[str, dict]) -> dict[str, Any]:
    iri = raw.get("iri", "")
    src = sources.get(iri, {})
    return {
        "id": kb.id * 1_000_000 + idx,
        "iri": iri,
        "name": raw.get("label", ""),
        "formula": raw.get("formula", ""),
        "caliber": raw.get("caliber") or None,
        "bound_table_refs": [],
        "concept_id": None,
        "confidence": float(raw.get("confidence") or 0),
        "status": raw.get("status") or "draft",
        "origin": build_entity_origin(kb, src),
    }


def _normalize_dimension(raw: dict[str, Any], kb: KnowledgeBase, idx: int, sources: dict[str, dict]) -> dict[str, Any]:
    iri = raw.get("iri", "")
    src = sources.get(iri, {})
    return {
        "id": kb.id * 1_000_000 + idx,
        "iri": iri,
        "name": raw.get("label", ""),
        "definition": raw.get("definition", ""),
        "dim_type": raw.get("dimensionType", ""),
        "confidence": float(raw.get("confidence") or 0),
        "status": raw.get("status") or "draft",
        "origin": build_entity_origin(kb, src),
    }


def _list_rules_for_kb(kb_id: int) -> list[dict[str, Any]]:
    graph = kb_graph_iri(kb_id)
    ns = str(NS)
    query = f"""
    PREFIX dl: <{ns}>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?s ?label ?ruleExpression ?ruleType ?status ?confidence WHERE {{
      GRAPH <{graph}> {{
        ?s a dl:BusinessRule ;
           skos:prefLabel ?label .
        OPTIONAL {{ ?s dl:ruleExpression ?ruleExpression . }}
        OPTIONAL {{ ?s dl:ruleType ?ruleType . }}
        OPTIONAL {{ ?s dl:approvalStatus ?status . }}
        OPTIONAL {{ ?s dl:confidence ?confidence . }}
      }}
    }}
    ORDER BY ?label
    LIMIT 500
    """
    try:
        return sparql_query(query)
    except Exception as exc:
        _logger.warning("SPARQL rules failed kb=%s: %s", kb_id, exc)
        return []


def _normalize_rule(raw: dict[str, Any], kb: KnowledgeBase, idx: int, sources: dict[str, dict]) -> dict[str, Any]:
    iri = str(raw.get("s", ""))
    src = sources.get(iri, {})
    return {
        "id": kb.id * 1_000_000 + idx,
        "iri": iri,
        "name": str(raw.get("label", "")),
        "rule_expression": str(raw.get("ruleExpression", "")),
        "rule_type": str(raw.get("ruleType", "")),
        "confidence": float(raw.get("confidence") or 0),
        "status": str(raw.get("status") or "draft"),
        "origin": build_entity_origin(kb, src),
    }


def _filter_kb_ids(kb_rows: list[KnowledgeBase], kb_filter: int | None) -> list[KnowledgeBase]:
    if kb_filter is None:
        return kb_rows
    return [kb for kb in kb_rows if kb.id == kb_filter]


def domain_overview(db: Session, domain_id: int) -> dict[str, Any]:
    domain = db.get(BusinessDomain, domain_id)
    if not domain:
        return {"ok": False, "error": "domain not found"}
    kb_rows = _domain_kb_rows(db, domain_id)
    kb_summaries: list[dict[str, Any]] = []
    totals = {
        "term_count": 0,
        "metric_count": 0,
        "physical_table_count": 0,
        "relation_edge_count": 0,
        "triple_count": 0,
        "quarantine_count": 0,
    }
    for kb in kb_rows:
        modeling = get_modeling_status(db, kb.id)
        prod: dict[str, Any] = {}
        quar: dict[str, Any] = {}
        try:
            rdf = fetch_kb_rdf_view(kb.id)
            prod = rdf.get("production", {})
            quar = rdf.get("quarantine", {})
        except Exception:
            pass
        graph_res = view_graph(kb.id)
        edge_count = len(graph_res.get("edges") or [])
        term_c = int(prod.get("term_count") or 0)
        metric_c = int(prod.get("metric_count") or 0)
        table_c = int(prod.get("physical_table_count") or 0)
        triple_c = int(prod.get("triple_count") or 0)
        quar_c = int(quar.get("assertion_count") or 0)
        totals["term_count"] += term_c
        totals["metric_count"] += metric_c
        totals["physical_table_count"] += table_c
        totals["relation_edge_count"] += edge_count
        totals["triple_count"] += triple_c
        totals["quarantine_count"] += quar_c
        shacl_rate = (modeling.get("quality") or {}).get("shacl_pass_rate")
        extraction = modeling.get("extraction") or {}
        kb_summaries.append(
            {
                "knowledge_base_id": kb.id,
                "knowledge_base_name": kb.name,
                "term_count": term_c,
                "metric_count": metric_c,
                "physical_table_count": table_c,
                "relation_edge_count": edge_count,
                "triple_count": triple_c,
                "quarantine_count": quar_c,
                "shacl_pass_rate": shacl_rate,
                "pipeline_status": extraction.get("status") or modeling.get("pipeline_phase"),
                "last_cleaning_at": extraction.get("completed_at"),
            }
        )
    return {
        "ok": True,
        "domain_id": domain_id,
        "domain_name": domain.name,
        "knowledge_base_count": len(kb_rows),
        "knowledge_bases": kb_summaries,
        "totals": totals,
    }


def domain_terms(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    reader = _reader()
    terms: list[dict[str, Any]] = []
    for kb in kb_rows:
        sources = fetch_grounded_sources(db, kb.id)
        raw_list = reader.list_terms(kb.id)
        for idx, raw in enumerate(raw_list):
            terms.append(_normalize_term(raw, kb, idx, sources))
    terms.sort(key=lambda t: (t.get("name") or "").lower())
    return {"ok": True, "domain_id": domain_id, "terms": terms, "total": len(terms)}


def domain_metrics(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    reader = _reader()
    metrics: list[dict[str, Any]] = []
    for kb in kb_rows:
        sources = fetch_grounded_sources(db, kb.id)
        raw_list = reader.list_metrics(kb.id)
        for idx, raw in enumerate(raw_list):
            metrics.append(_normalize_metric(raw, kb, idx, sources))
    metrics.sort(key=lambda m: (m.get("name") or "").lower())
    return {"ok": True, "domain_id": domain_id, "metrics": metrics, "total": len(metrics)}


def domain_dimensions(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    reader = _reader()
    dimensions: list[dict[str, Any]] = []
    for kb in kb_rows:
        sources = fetch_grounded_sources(db, kb.id)
        raw_list = reader.list_dimensions(kb.id)
        for idx, raw in enumerate(raw_list):
            dimensions.append(_normalize_dimension(raw, kb, idx, sources))
    dimensions.sort(key=lambda d: (d.get("name") or "").lower())
    return {"ok": True, "domain_id": domain_id, "dimensions": dimensions, "total": len(dimensions)}


def domain_rules(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    rules: list[dict[str, Any]] = []
    for kb in kb_rows:
        sources = fetch_grounded_sources(db, kb.id)
        raw_list = _list_rules_for_kb(kb.id)
        for idx, raw in enumerate(raw_list):
            rules.append(_normalize_rule(raw, kb, idx, sources))
    rules.sort(key=lambda r: (r.get("name") or "").lower())
    return {"ok": True, "domain_id": domain_id, "rules": rules, "total": len(rules)}


def domain_graph(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for kb in kb_rows:
        res = view_graph(kb.id)
        for n in res.get("nodes") or []:
            nid = str(n.get("id", ""))
            if not nid or nid in seen_node_ids:
                continue
            seen_node_ids.add(nid)
            nodes.append({**n, "knowledge_base_id": kb.id, "knowledge_base_name": kb.name})
        for e in res.get("edges") or []:
            edges.append(
                {
                    **e,
                    "id": f"kb{kb.id}-{e.get('id', '')}",
                    "knowledge_base_id": kb.id,
                }
            )
    return {
        "ok": True,
        "domain_id": domain_id,
        "nodes": nodes,
        "edges": edges,
        "knowledge_base_count": len(kb_rows),
    }


def domain_lineage(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    all_edges: list[dict[str, Any]] = []
    for kb in kb_rows:
        res = view_lineage(kb.id)
        for e in res.get("edges") or []:
            all_edges.append({**e, "knowledge_base_id": kb.id, "knowledge_base_name": kb.name})
    return {"ok": True, "domain_id": domain_id, "edges": all_edges, "total": len(all_edges)}


def domain_assets(db: Session, domain_id: int, *, kb_filter: int | None = None) -> dict[str, Any]:
    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    tables: list[dict[str, Any]] = []
    for kb in kb_rows:
        try:
            rdf = fetch_kb_rdf_view(kb.id)
            for tbl in rdf.get("production", {}).get("physical_tables", []):
                tables.append(
                    {
                        **tbl,
                        "origin": build_entity_origin(kb),
                    }
                )
        except Exception:
            continue
    return {"ok": True, "domain_id": domain_id, "physical_tables": tables, "total": len(tables)}


_LAYERS_WITH_GROUNDING = frozenset({"vocabulary", "rule", "entity-concept", "dimension"})


def _merge_layer_counts(kb_rows: list[KnowledgeBase]) -> dict[str, int]:
    from services.ontology.modeling_layers import LAYER_KEYS, count_layers_for_kb

    totals = {key: 0 for key in LAYER_KEYS}
    for kb in kb_rows:
        kb_counts = count_layers_for_kb(kb.id)
        for key in LAYER_KEYS:
            totals[key] += int(kb_counts.get(key, 0))
    return totals


def domain_layers_summary(
    db: Session,
    domain_id: int,
    *,
    kb_filter: int | None = None,
) -> dict[str, Any]:
    from services.ontology.modeling_layers import build_layers_summary

    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    counts = _merge_layer_counts(kb_rows)
    return {
        "ok": True,
        "domain_id": domain_id,
        "knowledge_base_count": len(kb_rows),
        "layers": build_layers_summary(counts),
    }


def _sort_layer_items(layer_key: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if layer_key in ("relation", "attribute"):
        return sorted(
            items,
            key=lambda r: (
                str((r.get("origin") or {}).get("knowledge_base_name", "")),
                str(r.get("s", "")),
                str(r.get("p", "")),
            ),
        )
    return sorted(
        items,
        key=lambda r: (
            str((r.get("origin") or {}).get("knowledge_base_name", "")),
            str(r.get("label") or r.get("s", "")).lower(),
        ),
    )


def domain_layer_detail(
    db: Session,
    domain_id: int,
    layer_key: str,
    *,
    kb_filter: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from services.ontology.modeling_layers import fetch_items_for_layer, get_layer_metadata, normalize_layer_key

    normalized = normalize_layer_key(layer_key)
    if not normalized:
        return {"ok": False, "error": f"未知清洗层: {layer_key}"}

    meta = get_layer_metadata(normalized)
    if not meta:
        return {"ok": False, "error": f"未知清洗层: {layer_key}"}

    kb_rows = _filter_kb_ids(_domain_kb_rows(db, domain_id), kb_filter)
    all_items: list[dict[str, Any]] = []
    for kb in kb_rows:
        sources = fetch_grounded_sources(db, kb.id) if normalized in _LAYERS_WITH_GROUNDING else {}
        for item in fetch_items_for_layer(kb.id, normalized):
            enriched = dict(item)
            subject = str(item.get("s", ""))
            src = sources.get(subject, {}) if subject else {}
            enriched["origin"] = build_entity_origin(kb, src)
            all_items.append(enriched)

    all_items = _sort_layer_items(normalized, all_items)
    total = len(all_items)
    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 2000))
    page = all_items[safe_offset : safe_offset + safe_limit]
    has_more = safe_offset + len(page) < total

    return {
        "ok": True,
        "domain_id": domain_id,
        "layer_key": normalized,
        "label": meta["label"],
        "description": meta["description"],
        "ontology_class": meta["ontology_class"],
        "criteria": meta.get("criteria"),
        "total": total,
        "offset": safe_offset,
        "limit": safe_limit,
        "has_more": has_more,
        "items": page,
    }
