"""Five-layer cleaning results and per-layer view for modeling UI."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import KnowledgeBase, PipelineRun
from ontology import DATA_NS, NS, kb_graph_iri
from services.ontology.provenance import build_entity_origin, fetch_grounded_sources
from services.ontology.relation_predicates import (
    relation_predicate_in_clause,
    relation_predicate_local_names,
)
from services.ontology_store import sparql_query

_logger = logging.getLogger(__name__)

LAYER_KEYS = frozenset(
    {"vocabulary", "rule", "entity-concept", "dimension", "relation", "attribute"}
)

# Product-facing five-layer chip order (dimension shown as badge on entity-concept)
DISPLAY_LAYER_KEYS = (
    "vocabulary",
    "rule",
    "entity-concept",
    "relation",
    "attribute",
)

_LAYER_ALIASES = {
    "entity_concept": "entity-concept",
    "entity": "entity-concept",
    "concept": "entity-concept",
}

_LAYER_META: dict[str, dict[str, str]] = {
    "vocabulary": {
        "label": "词汇层",
        "description": "业务术语定义",
        "ontology_class": "dl:BusinessTerm",
    },
    "rule": {
        "label": "规则层",
        "description": "指标与业务规则",
        "ontology_class": "dl:Metric, dl:BusinessRule",
    },
    "entity-concept": {
        "label": "实体概念层",
        "description": "存在层级关系的语义实体（术语/指标/维度/概念）",
        "ontology_class": "dl:BusinessTerm, dl:Metric, dl:Dimension, dl:BusinessConcept",
    },
    "dimension": {
        "label": "维度层",
        "description": "分析维度与下钻层级",
        "ontology_class": "dl:Dimension",
    },
    "relation": {
        "label": "关系层",
        "description": "语义关系边",
        "ontology_class": "ObjectProperty edges",
    },
    "attribute": {
        "label": "属性层",
        "description": "数据属性值",
        "ontology_class": "DatatypeProperty values",
    },
}

_LAYER_CRITERIA: dict[str, dict[str, Any]] = {
    "entity-concept": {
        "entity_types": ["BusinessTerm", "Metric", "Dimension", "BusinessConcept"],
        "hierarchy_predicates": ["broader", "narrower"],
        "includes_incoming_hierarchy_edges": True,
    },
    "relation": {
        "object_filter": "isIRI",
        "predicates": relation_predicate_local_names(),
    }
}


def normalize_layer_key(key: str) -> str | None:
    normalized = _LAYER_ALIASES.get(key, key)
    return normalized if normalized in LAYER_KEYS else None


def _sparql_rows(query: str) -> list[dict[str, str]]:
    try:
        rows = sparql_query(query)
        return [{k: str(v) for k, v in row.items()} for row in rows]
    except Exception as exc:
        _logger.warning("SPARQL layer query failed: %s", exc)
        return []


def _sparql_count(query: str) -> int:
    rows = _sparql_rows(query)
    if not rows:
        return 0
    row = rows[0]
    for key in ("c", "count"):
        if key in row:
            try:
                return int(float(row[key]))
            except (TypeError, ValueError):
                pass
    val = next(iter(row.values()), "0")
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _graph_context(kb_id: int) -> tuple[str, str, str, str, str]:
    """Return graph IRI, dl namespace, skos namespace, rdf prefix IRI, rdf:type predicate IRI."""
    graph = kb_graph_iri(kb_id)
    ns = str(NS)
    skos = "http://www.w3.org/2004/02/skos/core#"
    rdf_ns = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    rdf_type = f"{rdf_ns}type"
    return graph, ns, skos, rdf_ns, rdf_type


def _count_queries(kb_id: int) -> dict[str, int]:
    graph, ns, skos, rdf_ns, rdf_type = _graph_context(kb_id)
    relation_predicates = relation_predicate_in_clause()
    entity_types = ", ".join(
        [
            f"<{ns}BusinessTerm>",
            f"<{ns}Metric>",
            f"<{ns}Dimension>",
            f"<{ns}BusinessConcept>",
        ]
    )
    attr_exclude = ", ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
    return {
        "vocabulary": _sparql_count(f"""
            PREFIX dl: <{ns}>
            PREFIX rdf: <{rdf_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:BusinessTerm .
                }}
            }}
        """),
        "rule": _sparql_count(f"""
            PREFIX dl: <{ns}>
            PREFIX rdf: <{rdf_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    {{ ?s rdf:type dl:BusinessRule . }}
                    UNION
                    {{ ?s rdf:type dl:Metric . }}
                }}
            }}
        """),
        "entity-concept": _sparql_count(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type ?entityType .
                    FILTER(?entityType IN ({entity_types}))
                }}
            }}
        """),
        "dimension": _sparql_count(f"""
            PREFIX dl: <{ns}>
            PREFIX rdf: <{rdf_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:Dimension .
                }}
            }}
        """),
        "relation": _sparql_count(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            SELECT (COUNT(*) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    ?s ?p ?o .
                    FILTER(isIRI(?o))
                    FILTER(?p IN ({relation_predicates}))
                }}
            }}
        """),
        "attribute": _sparql_count(f"""
            PREFIX dl: <{ns}>
            PREFIX rdf: <{rdf_ns}>
            SELECT (COUNT(*) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    ?s ?p ?o .
                    FILTER(isLiteral(?o))
                    FILTER(?p NOT IN ({attr_exclude}))
                }}
            }}
        """),
    }


def _physical_table_subject_prefixes() -> tuple[str, ...]:
    return (DATA_NS + "table/", NS + "data/table/")


def is_physical_schema_subject(subject: str) -> bool:
    s = subject or ""
    return any(s.startswith(prefix) for prefix in _physical_table_subject_prefixes())


def _count_physical_attribute_literals(kb_id: int) -> int:
    graph, ns, _skos, rdf_ns, rdf_type = _graph_context(kb_id)
    attr_exclude = ", ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
    prefixes = " || ".join(
        f'STRSTARTS(STR(?s), "{p}")' for p in _physical_table_subject_prefixes()
    )
    return _sparql_count(f"""
        PREFIX dl: <{ns}>
        PREFIX rdf: <{rdf_ns}>
        SELECT (COUNT(*) AS ?c) WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                FILTER(isLiteral(?o))
                FILTER(?p NOT IN ({attr_exclude}))
                FILTER({prefixes})
            }}
        }}
    """)


def _attribute_sort_key(item: dict[str, str]) -> tuple[int, int, str, str, str]:
    subject = str(item.get("s", ""))
    physical_rank = 0 if is_physical_schema_subject(subject) else 1
    # 表级断言（businessSummary 等）排在列字段之前
    column_rank = 1 if "/column/" in subject else 0
    label = str(item.get("subjectLabel") or "")
    pred = str(item.get("p") or "")
    return (physical_rank, column_rank, label.lower(), pred, subject)


def _attribute_row_matches_query(item: dict[str, str], query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    parts = [
        str(item.get("subjectLabel") or ""),
        str(item.get("s") or ""),
        str(item.get("p") or ""),
        str(item.get("o") or ""),
    ]
    blob = " ".join(parts).lower()
    return q in blob


def _apply_attribute_filters(
    items: list[dict[str, str]],
    *,
    q: str | None = None,
    physical_only: bool = False,
) -> list[dict[str, str]]:
    filtered = items
    if physical_only:
        filtered = [i for i in filtered if is_physical_schema_subject(str(i.get("s", "")))]
    if q and q.strip():
        filtered = [i for i in filtered if _attribute_row_matches_query(i, q)]
    return sorted(filtered, key=_attribute_sort_key)


def _fetch_layer_items(kb_id: int, layer_key: str) -> list[dict[str, str]]:
    graph, ns, skos, rdf_ns, rdf_type = _graph_context(kb_id)

    if layer_key == "vocabulary":
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?label ?definition ?status
                   (GROUP_CONCAT(?syn; separator='|||') AS ?synonyms)
            WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:BusinessTerm .
                    OPTIONAL {{ ?s skos:prefLabel ?label }}
                    OPTIONAL {{ ?s skos:definition ?definition }}
                    OPTIONAL {{ ?s dl:approvalStatus ?status }}
                    OPTIONAL {{ ?s skos:altLabel ?syn }}
                }}
            }}
            GROUP BY ?s ?label ?definition ?status
        """)

    if layer_key == "rule":
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?label ?formula ?ruleExpression ?ruleType ?status WHERE {{
                {{
                    GRAPH <{graph}> {{
                        ?s rdf:type dl:BusinessRule .
                        OPTIONAL {{ ?s skos:prefLabel ?label }}
                        OPTIONAL {{ ?s dl:formula ?formula }}
                        OPTIONAL {{ ?s dl:ruleExpression ?ruleExpression }}
                        OPTIONAL {{ ?s dl:ruleType ?ruleType }}
                        OPTIONAL {{ ?s dl:approvalStatus ?status }}
                    }}
                }}
                UNION
                {{
                    GRAPH <{graph}> {{
                        ?s rdf:type dl:Metric .
                        OPTIONAL {{ ?s skos:prefLabel ?label }}
                        OPTIONAL {{ ?s dl:formula ?formula }}
                        OPTIONAL {{ ?s dl:caliber ?ruleExpression }}
                        OPTIONAL {{ ?s dl:approvalStatus ?status }}
                    }}
                }}
            }}
        """)

    if layer_key == "entity-concept":
        entity_types = ", ".join(
            [
                f"<{ns}BusinessTerm>",
                f"<{ns}Metric>",
                f"<{ns}Dimension>",
                f"<{ns}BusinessConcept>",
            ]
        )
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT
                ?s
                (SAMPLE(?label0) AS ?label)
                (SAMPLE(?definition0) AS ?definition)
                (SAMPLE(?entityType0) AS ?entityType)
                (GROUP_CONCAT(DISTINCT STR(?neighbor); separator=" | ") AS ?neighbors)
            WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type ?entityType0 .
                    FILTER(?entityType0 IN ({entity_types}))
                    OPTIONAL {{ ?s skos:prefLabel ?label0 }}
                    OPTIONAL {{ ?s skos:definition ?definition0 }}
                    OPTIONAL {{
                        {{
                            ?s skos:broader|skos:narrower ?neighbor .
                        }}
                        UNION
                        {{
                            ?neighbor skos:broader|skos:narrower ?s .
                        }}
                    }}
                }}
            }}
            GROUP BY ?s
        """)

    if layer_key == "dimension":
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?label ?definition ?dimType ?status WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:Dimension .
                    OPTIONAL {{ ?s skos:prefLabel ?label }}
                    OPTIONAL {{ ?s skos:definition ?definition }}
                    OPTIONAL {{ ?s dl:dimensionType ?dimType }}
                    OPTIONAL {{ ?s dl:approvalStatus ?status }}
                }}
            }}
        """)

    if layer_key == "relation":
        relation_predicates = relation_predicate_in_clause()
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            SELECT ?s ?p ?o WHERE {{
                GRAPH <{graph}> {{
                    ?s ?p ?o .
                    FILTER(isIRI(?o))
                    FILTER(?p IN ({relation_predicates}))
                }}
            }}
        """)

    if layer_key == "attribute":
        attr_exclude = ", ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
        rows = _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?p ?o ?subjectLabel WHERE {{
                GRAPH <{graph}> {{
                    ?s ?p ?o .
                    FILTER(isLiteral(?o))
                    FILTER(?p NOT IN ({attr_exclude}))
                    OPTIONAL {{ ?s skos:prefLabel ?subjectLabel }}
                }}
            }}
        """)
        return _apply_attribute_filters(rows)

    return []


def _build_summary_layers(counts: dict[str, int]) -> dict[str, dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for key in LAYER_KEYS:
        meta = _LAYER_META[key]
        layer_entry: dict[str, Any] = {
            "label": meta["label"],
            "description": meta["description"],
            "ontology_class": meta["ontology_class"],
            "total": counts.get(key, 0),
        }
        if key == "attribute":
            physical_total = int(counts.get("attribute_physical") or 0)
            if physical_total > 0:
                layer_entry["physical_total"] = physical_total
        layers[key] = layer_entry
        criteria = _LAYER_CRITERIA.get(key)
        if criteria:
            layers[key]["criteria"] = criteria
    return layers


def get_cleaning_results(
    db: Session,
    kb_id: int,
    *,
    include_items: bool = False,
) -> dict[str, Any]:
    counts = _count_queries(kb_id)
    counts["attribute_physical"] = _count_physical_attribute_literals(kb_id)
    layers = _build_summary_layers(counts)

    if include_items:
        for key in LAYER_KEYS:
            layers[key]["items"] = _fetch_layer_items(kb_id, key)

    latest_run = db.execute(
        select(PipelineRun)
        .where(
            PipelineRun.knowledge_base_id == kb_id,
            PipelineRun.status == "completed",
        )
        .order_by(PipelineRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "ok": True,
        "kb_id": kb_id,
        "layers": layers,
        "last_cleaning_at": latest_run.completed_at.isoformat()
        if (latest_run and latest_run.completed_at)
        else None,
    }


def get_modeling_layer(
    db: Session,
    kb_id: int,
    layer_key: str,
    *,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    physical_only: bool = False,
) -> dict[str, Any]:
    normalized = normalize_layer_key(layer_key)
    if not normalized:
        return {"ok": False, "error": f"未知清洗层: {layer_key}"}

    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        return {"ok": False, "error": "知识库不存在"}

    meta = _LAYER_META[normalized]
    counts = _count_queries(kb_id)
    unfiltered_total = counts.get(normalized, 0)

    if normalized == "attribute":
        raw_rows = _sparql_rows(_attribute_layer_sparql(kb_id))
        all_items = _apply_attribute_filters(
            raw_rows,
            q=q,
            physical_only=physical_only,
        )
        total = len(all_items)
    else:
        all_items = _fetch_layer_items(kb_id, normalized)
        if q and q.strip():
            ql = q.strip().lower()
            all_items = [
                i
                for i in all_items
                if ql in " ".join(str(v) for v in i.values() if v).lower()
            ]
        total = len(all_items) if (q and q.strip()) else unfiltered_total

    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 2000))
    page = all_items[safe_offset : safe_offset + safe_limit]
    has_more = safe_offset + len(page) < total

    sources = fetch_grounded_sources(db, kb_id)
    enriched_page: list[dict[str, Any]] = []
    for item in page:
        enriched = dict(item)
        subject = str(item.get("s", ""))
        src = sources.get(subject, {}) if subject else {}
        enriched["origin"] = build_entity_origin(kb, src or None)
        enriched_page.append(enriched)

    result: dict[str, Any] = {
        "ok": True,
        "kb_id": kb_id,
        "layer_key": normalized,
        "label": meta["label"],
        "description": meta["description"],
        "ontology_class": meta["ontology_class"],
        "criteria": _LAYER_CRITERIA.get(normalized),
        "total": total,
        "unfiltered_total": unfiltered_total,
        "offset": safe_offset,
        "limit": safe_limit,
        "has_more": has_more,
        "items": enriched_page,
    }
    if normalized == "attribute":
        result["physical_total"] = _count_physical_attribute_literals(kb_id)
        if physical_only:
            result["physical_only"] = True
        if q and q.strip():
            result["q"] = q.strip()
    return result


def _attribute_layer_sparql(kb_id: int) -> str:
    graph, ns, skos, rdf_ns, rdf_type = _graph_context(kb_id)
    attr_exclude = ", ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
    return f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        PREFIX rdf: <{rdf_ns}>
        SELECT ?s ?p ?o ?subjectLabel WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                FILTER(isLiteral(?o))
                FILTER(?p NOT IN ({attr_exclude}))
                OPTIONAL {{ ?s skos:prefLabel ?subjectLabel }}
            }}
        }}
    """


def count_layers_for_kb(kb_id: int) -> dict[str, int]:
    return _count_queries(kb_id)


def fetch_items_for_layer(kb_id: int, layer_key: str) -> list[dict[str, str]]:
    normalized = normalize_layer_key(layer_key)
    if not normalized:
        return []
    return _fetch_layer_items(kb_id, normalized)


def build_layers_summary(counts: dict[str, int]) -> dict[str, dict[str, Any]]:
    return _build_summary_layers(counts)


def get_layer_metadata(layer_key: str) -> dict[str, Any] | None:
    normalized = normalize_layer_key(layer_key)
    if not normalized:
        return None
    meta = _LAYER_META[normalized]
    return {
        "layer_key": normalized,
        "label": meta["label"],
        "description": meta["description"],
        "ontology_class": meta["ontology_class"],
        "criteria": _LAYER_CRITERIA.get(normalized),
    }
