"""Five-layer cleaning results and per-layer view for modeling UI."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import PipelineRun
from ontology import NS, kb_graph_iri
from services.ontology_store import sparql_query

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
        "description": "概念层级归属",
        "ontology_class": "dl:BusinessConcept",
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


def normalize_layer_key(key: str) -> str | None:
    normalized = _LAYER_ALIASES.get(key, key)
    return normalized if normalized in LAYER_KEYS else None


def _sparql_rows(query: str) -> list[dict[str, str]]:
    try:
        rows = sparql_query(query)
        return [{k: str(v) for k, v in row.items()} for row in rows]
    except Exception:
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
    relation_predicates = " ".join(
        [
            f"<{ns}dependsOn>",
            f"<{ns}derivedFrom>",
            f"<{ns}joinableWith>",
            f"<{ns}transformsFrom>",
            f"<{skos}related>",
            f"<{skos}broader>",
            f"<{skos}narrower>",
        ]
    )
    attr_exclude = " ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
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
            PREFIX rdf: <{rdf_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:BusinessConcept .
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


def _fetch_layer_items(kb_id: int, layer_key: str) -> list[dict[str, str]]:
    graph, ns, skos, rdf_ns, rdf_type = _graph_context(kb_id)

    if layer_key == "vocabulary":
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?label ?definition ?status WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:BusinessTerm .
                    OPTIONAL {{ ?s skos:prefLabel ?label }}
                    OPTIONAL {{ ?s skos:definition ?definition }}
                    OPTIONAL {{ ?s dl:approvalStatus ?status }}
                }}
            }}
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
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?label ?broader WHERE {{
                GRAPH <{graph}> {{
                    ?s rdf:type dl:BusinessConcept .
                    OPTIONAL {{ ?s skos:prefLabel ?label }}
                    OPTIONAL {{ ?s skos:broader ?broader }}
                }}
            }}
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
        relation_predicates = " ".join(
            [
                f"<{ns}dependsOn>",
                f"<{ns}derivedFrom>",
                f"<{ns}joinableWith>",
                f"<{ns}transformsFrom>",
                f"<{skos}related>",
                f"<{skos}broader>",
                f"<{skos}narrower>",
            ]
        )
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
        attr_exclude = " ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
        return _sparql_rows(f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <{skos}>
            PREFIX rdf: <{rdf_ns}>
            SELECT ?s ?p ?o WHERE {{
                GRAPH <{graph}> {{
                    ?s ?p ?o .
                    FILTER(isLiteral(?o))
                    FILTER(?p NOT IN ({attr_exclude}))
                }}
            }}
        """)

    return []


def _build_summary_layers(counts: dict[str, int]) -> dict[str, dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for key in LAYER_KEYS:
        meta = _LAYER_META[key]
        layers[key] = {
            "label": meta["label"],
            "description": meta["description"],
            "ontology_class": meta["ontology_class"],
            "total": counts.get(key, 0),
        }
    return layers


def get_cleaning_results(
    db: Session,
    kb_id: int,
    *,
    include_items: bool = False,
) -> dict[str, Any]:
    counts = _count_queries(kb_id)
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
    kb_id: int,
    layer_key: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized = normalize_layer_key(layer_key)
    if not normalized:
        return {"ok": False, "error": f"未知清洗层: {layer_key}"}

    meta = _LAYER_META[normalized]
    counts = _count_queries(kb_id)
    total = counts.get(normalized, 0)
    all_items = _fetch_layer_items(kb_id, normalized)

    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 2000))
    page = all_items[safe_offset : safe_offset + safe_limit]
    has_more = safe_offset + len(page) < total

    return {
        "ok": True,
        "kb_id": kb_id,
        "layer_key": normalized,
        "label": meta["label"],
        "description": meta["description"],
        "ontology_class": meta["ontology_class"],
        "total": total,
        "offset": safe_offset,
        "limit": safe_limit,
        "has_more": has_more,
        "items": page,
    }
