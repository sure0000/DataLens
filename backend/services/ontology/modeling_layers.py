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

_LAYER_ALIASES = {
    "entity_concept": "entity-concept",
    "entity": "entity-concept",
    "concept": "entity-concept",
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


def _fetch_layers(kb_id: int) -> dict[str, dict[str, Any]]:
    graph = kb_graph_iri(kb_id)
    ns = str(NS)
    skos = "http://www.w3.org/2004/02/skos/core#"
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    vocab_rows = _sparql_rows(f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        PREFIX rdf: <{rdf_type}>
        SELECT ?s ?label ?definition ?status WHERE {{
            GRAPH <{graph}> {{
                ?s rdf:type dl:BusinessTerm .
                OPTIONAL {{ ?s skos:prefLabel ?label }}
                OPTIONAL {{ ?s skos:definition ?definition }}
                OPTIONAL {{ ?s dl:approvalStatus ?status }}
            }}
        }}
    """)
    layers: dict[str, dict[str, Any]] = {
        "vocabulary": {
            "label": "词汇层",
            "description": "业务术语定义",
            "total": len(vocab_rows),
            "ontology_class": "dl:BusinessTerm",
            "items": vocab_rows,
        }
    }

    rule_rows = _sparql_rows(f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        PREFIX rdf: <{rdf_type}>
        SELECT ?s ?label ?formula ?ruleExpression ?ruleType ?status WHERE {{
            GRAPH <{graph}> {{
                ?s rdf:type ?type .
                OPTIONAL {{ ?s skos:prefLabel ?label }}
                OPTIONAL {{ ?s dl:formula ?formula }}
                OPTIONAL {{ ?s dl:ruleExpression ?ruleExpression }}
                OPTIONAL {{ ?s dl:ruleType ?ruleType }}
                OPTIONAL {{ ?s dl:approvalStatus ?status }}
                VALUES ?type {{ dl:BusinessRule }}
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
    """)
    layers["rule"] = {
        "label": "规则层",
        "description": "指标与业务规则",
        "total": len(rule_rows),
        "ontology_class": "dl:Metric, dl:BusinessRule",
        "items": rule_rows,
    }

    concept_rows = _sparql_rows(f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        PREFIX rdf: <{rdf_type}>
        SELECT ?s ?label ?broader WHERE {{
            GRAPH <{graph}> {{
                ?s rdf:type dl:BusinessConcept .
                OPTIONAL {{ ?s skos:prefLabel ?label }}
                OPTIONAL {{ ?s skos:broader ?broader }}
            }}
        }}
    """)
    layers["entity-concept"] = {
        "label": "实体概念层",
        "description": "概念层级归属",
        "total": len(concept_rows),
        "ontology_class": "dl:BusinessConcept",
        "items": concept_rows,
    }

    dimension_rows = _sparql_rows(f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        PREFIX rdf: <{rdf_type}>
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
    layers["dimension"] = {
        "label": "维度层",
        "description": "分析维度与下钻层级",
        "total": len(dimension_rows),
        "ontology_class": "dl:Dimension",
        "items": dimension_rows,
    }

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
    relation_rows = _sparql_rows(f"""
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
    layers["relation"] = {
        "label": "关系层",
        "description": "语义关系边",
        "total": len(relation_rows),
        "ontology_class": "ObjectProperty edges",
        "items": relation_rows,
    }

    attr_exclude = " ".join([f"<{rdf_type}>", f"<{ns}approvalStatus>"])
    attribute_rows = _sparql_rows(f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        PREFIX rdf: <{rdf_type}>
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                FILTER(isLiteral(?o))
                FILTER(?p NOT IN ({attr_exclude}))
            }}
        }}
    """)
    layers["attribute"] = {
        "label": "属性层",
        "description": "数据属性值",
        "total": len(attribute_rows),
        "ontology_class": "DatatypeProperty values",
        "items": attribute_rows,
    }

    return layers


def get_cleaning_results(db: Session, kb_id: int) -> dict[str, Any]:
    layers = _fetch_layers(kb_id)
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


def get_modeling_layer(kb_id: int, layer_key: str, *, limit: int | None = None) -> dict[str, Any]:
    normalized = normalize_layer_key(layer_key)
    if not normalized:
        return {"ok": False, "error": f"未知清洗层: {layer_key}"}

    layers = _fetch_layers(kb_id)
    layer = layers[normalized]
    items = layer["items"]
    if limit is not None and limit > 0:
        items = items[:limit]

    return {
        "ok": True,
        "kb_id": kb_id,
        "layer_key": normalized,
        "label": layer["label"],
        "description": layer["description"],
        "ontology_class": layer["ontology_class"],
        "total": layer["total"],
        "items": items,
    }
