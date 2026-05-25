"""SPARQL query templates for ontology routing and context."""
from __future__ import annotations

from ontology import NS, domain_graph_iri, kb_graph_iri


def search_terms_by_keyword(keyword: str, graph_iri: str, limit: int = 10) -> str:
    kw = keyword.replace("\\", "\\\\").replace('"', '\\"').lower()
    return f"""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dl: <{NS}>
SELECT ?term ?label ?definition ?status WHERE {{
  GRAPH <{graph_iri}> {{
    ?term a dl:BusinessTerm ;
          skos:prefLabel ?label .
    OPTIONAL {{ ?term skos:definition ?definition }}
    OPTIONAL {{ ?term dl:approvalStatus ?status }}
    FILTER(CONTAINS(LCASE(STR(?label)), "{kw}"))
  }}
}} LIMIT {limit}
"""


def search_metrics_by_keyword(keyword: str, graph_iri: str, limit: int = 10) -> str:
    kw = keyword.replace("\\", "\\\\").replace('"', '\\"').lower()
    return f"""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dl: <{NS}>
SELECT ?metric ?label ?formula ?table ?status WHERE {{
  GRAPH <{graph_iri}> {{
    ?metric a dl:Metric ;
            skos:prefLabel ?label ;
            dl:formula ?formula .
    OPTIONAL {{ ?metric dl:computedFromTable ?table }}
    OPTIONAL {{ ?metric dl:approvalStatus ?status }}
    FILTER(?status = "approved" || !BOUND(?status))
    FILTER(CONTAINS(LCASE(STR(?label)), "{kw}") || CONTAINS(LCASE(STR(?formula)), "{kw}"))
  }}
}} LIMIT {limit}
"""


def expand_join_neighbors(table_iri: str, graph_iri: str, limit: int = 8) -> str:
    ti = table_iri.replace("<", "").replace(">", "")
    return f"""
PREFIX dl: <{NS}>
SELECT DISTINCT ?neighbor WHERE {{
  GRAPH <{graph_iri}> {{
    {{
      <{ti}> dl:joinableWith ?neighbor .
    }} UNION {{
      ?neighbor dl:joinableWith <{ti}> .
    }} UNION {{
      <{ti}> dl:transformsFrom ?neighbor .
    }}
  }}
}} LIMIT {limit}
"""


def tables_for_metric(metric_iri: str, graph_iri: str) -> str:
    mi = metric_iri.replace("<", "").replace(">", "")
    return f"""
PREFIX dl: <{NS}>
SELECT ?table ?platformId WHERE {{
  GRAPH <{graph_iri}> {{
    <{mi}> dl:computedFromTable ?table .
    OPTIONAL {{ ?table dl:platformId ?platformId }}
  }}
}}
"""


def count_triples_in_graph(graph_iri: str) -> str:
    return f"""
SELECT (COUNT(*) AS ?c) WHERE {{
  GRAPH <{graph_iri}> {{ ?s ?p ?o }}
}}
"""


def list_rdf_terms(graph_iri: str, limit: int = 500) -> str:
    return f"""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dl: <{NS}>
SELECT ?term ?label ?definition ?status WHERE {{
  GRAPH <{graph_iri}> {{
    ?term a dl:BusinessTerm ;
          skos:prefLabel ?label .
    OPTIONAL {{ ?term skos:definition ?definition }}
    OPTIONAL {{ ?term dl:approvalStatus ?status }}
  }}
}} ORDER BY ?label LIMIT {limit}
"""


def list_rdf_metrics(graph_iri: str, limit: int = 500) -> str:
    return f"""
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dl: <{NS}>
SELECT ?metric ?label ?formula ?status WHERE {{
  GRAPH <{graph_iri}> {{
    ?metric a dl:Metric ;
            skos:prefLabel ?label .
    OPTIONAL {{ ?metric dl:formula ?formula }}
    OPTIONAL {{ ?metric dl:approvalStatus ?status }}
  }}
}} ORDER BY ?label LIMIT {limit}
"""


def list_rdf_physical_tables(graph_iri: str, limit: int = 200) -> str:
    return f"""
PREFIX dl: <{NS}>
SELECT ?table ?platformId ?summary WHERE {{
  GRAPH <{graph_iri}> {{
    ?table a dl:PhysicalTable .
    OPTIONAL {{ ?table dl:platformId ?platformId }}
    OPTIONAL {{ ?table dl:businessSummary ?summary }}
  }}
}} ORDER BY ?platformId LIMIT {limit}
"""


def count_quarantine(graph_iri: str) -> str:
    return f"""
PREFIX dl: <{NS}>
SELECT (COUNT(?q) AS ?c) WHERE {{
  GRAPH <{graph_iri}> {{
    ?q a dl:QuarantinedAssertion .
  }}
}}
"""


def build_context_for_tables(table_iris: list[str], graph_iri: str) -> str:
    values = " ".join(f"<{iri}>" for iri in table_iris[:20])
    return f"""
PREFIX dl: <{NS}>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX schema: <https://schema.org/>
CONSTRUCT {{
  ?table dl:businessSummary ?summary .
  ?col dl:semanticDescription ?desc .
  ?col dl:semanticType ?stype .
  ?metric skos:prefLabel ?mlabel .
  ?metric dl:formula ?formula .
}} WHERE {{
  GRAPH <{graph_iri}> {{
    VALUES ?table {{ {values} }}
    OPTIONAL {{ ?table dl:businessSummary ?summary }}
    OPTIONAL {{
      ?col schema:isPartOf ?table ;
           dl:semanticDescription ?desc .
      OPTIONAL {{ ?col dl:semanticType ?stype }}
    }}
    OPTIONAL {{
      ?metric dl:computedFromTable ?table ;
              skos:prefLabel ?mlabel ;
              dl:formula ?formula .
    }}
  }}
}}
"""


def graph_for_kb(kb_id: int) -> str:
    return kb_graph_iri(kb_id)


def graph_for_domain(domain_id: int) -> str:
    return domain_graph_iri(domain_id)
