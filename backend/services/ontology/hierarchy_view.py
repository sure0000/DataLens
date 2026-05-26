"""Build concept hierarchy tree for presentation layer."""

from __future__ import annotations

from typing import Any

from ontology import NS, kb_graph_iri
from services.ontology_store import sparql_query


def build_hierarchy_roots(kb_id: int) -> list[dict[str, Any]]:
    graph = kb_graph_iri(kb_id)
    ns = str(NS)

    nodes: dict[str, dict[str, Any]] = {}
    child_of: dict[str, str] = {}

    try:
        label_rows = sparql_query(
            f"""
            PREFIX dl: <{ns}>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT ?s ?label ?definition WHERE {{
              GRAPH <{graph}> {{
                {{
                  ?s a dl:BusinessTerm .
                  OPTIONAL {{ ?s skos:prefLabel ?label }}
                  OPTIONAL {{ ?s skos:definition ?definition }}
                }}
                UNION
                {{
                  ?s a dl:BusinessConcept .
                  OPTIONAL {{ ?s skos:prefLabel ?label }}
                  OPTIONAL {{ ?s skos:definition ?definition }}
                }}
                UNION
                {{
                  ?s a dl:Dimension .
                  OPTIONAL {{ ?s skos:prefLabel ?label }}
                  OPTIONAL {{ ?s skos:definition ?definition }}
                }}
                UNION
                {{
                  ?s a dl:Metric .
                  OPTIONAL {{ ?s skos:prefLabel ?label }}
                  OPTIONAL {{ ?s skos:definition ?definition }}
                }}
              }}
            }}
            """
        )
    except Exception:
        label_rows = []

    for row in label_rows:
        iri = str(row.get("s", ""))
        if not iri:
            continue
        nodes[iri] = {
            "iri": iri,
            "label": str(row.get("label") or iri.split("/")[-1]),
            "definition": str(row.get("definition") or ""),
            "children": [],
        }

    try:
        edge_rows = sparql_query(
            f"""
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT ?child ?parent WHERE {{
              GRAPH <{graph}> {{
                {{
                  ?child skos:broader ?parent .
                }}
                UNION
                {{
                  ?parent skos:narrower ?child .
                }}
              }}
            }}
            """
        )
    except Exception:
        edge_rows = []

    for row in edge_rows:
        child = str(row.get("child", ""))
        parent = str(row.get("parent", ""))
        if not child or not parent:
            continue
        child_of[child] = parent
        nodes.setdefault(child, {"iri": child, "label": child.split("/")[-1], "definition": "", "children": []})
        nodes.setdefault(parent, {"iri": parent, "label": parent.split("/")[-1], "definition": "", "children": []})

    roots = [iri for iri in nodes if iri not in child_of]
    if not roots and nodes:
        roots = list(nodes.keys())[:20]

    def attach(iri: str, seen: set[str]) -> dict[str, Any]:
        if iri in seen:
            return {**nodes[iri], "children": []}
        seen.add(iri)
        base = nodes.get(iri, {"iri": iri, "label": iri.split("/")[-1], "definition": "", "children": []})
        kids = [attach(c, seen) for c, p in child_of.items() if p == iri]
        return {**base, "children": kids}

    return [attach(r, set()) for r in roots[:30]]
