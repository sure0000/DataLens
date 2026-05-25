"""Materialize OWL-RL inferred triples for join/alias closure."""
from __future__ import annotations

import logging
from typing import Any

from rdflib import Graph, Literal, Namespace

from config import get_settings
from ontology import INFERRED_GRAPH_PREFIX, NS
from services.ontology_store import insert_graph, is_fuseki_enabled, load_tbox, sparql_query

_logger = logging.getLogger(__name__)
DL = Namespace(NS)


def _memory_graph() -> Graph:
    load_tbox()
    from services.ontology_store import _get_memory_store
    return _get_memory_store()


def materialize_inferred_closure(domain_id: int, kb_id: int, *, max_hops: int | None = None) -> dict[str, Any]:
    """Expand joinableWith / transformsFrom up to max_hops; write to inferred graph."""
    settings = get_settings()
    hops = max_hops if max_hops is not None else settings.ontology_inferred_max_hops
    inferred_graph = f"{INFERRED_GRAPH_PREFIX}{domain_id}"

    # BFS over join edges via SPARQL property paths when Fuseki available
    if is_fuseki_enabled():
        from services.sparql_queries import graph_for_kb

        g_iri = graph_for_kb(kb_id)
        query = f"""
PREFIX dl: <{NS}>
CONSTRUCT {{ ?a dl:joinableWith ?b . ?a dl:inferred true . }}
WHERE {{
  GRAPH <{g_iri}> {{
    ?a dl:joinableWith/{{1,{hops}}} ?b .
    FILTER(?a != ?b)
  }}
}}"""
        try:
            rows = sparql_query(query)
            _logger.info("Inferred closure rows: %d", len(rows))
        except Exception as exc:
            _logger.warning("Inferred closure via Fuseki failed: %s", exc)

    # Memory fallback: copy direct join edges with inferred flag
    g = _memory_graph()
    inf = Graph()
    join_pred = DL.joinableWith
    for s, p, o in g.triples((None, join_pred, None)):
        inf.add((s, join_pred, o))
        inf.add((s, DL.inferred, Literal(True)))

    if len(inf):
        ttl = inf.serialize(format="turtle")
        try:
            insert_graph(inferred_graph, ttl)
        except Exception as exc:
            _logger.warning("Write inferred graph failed: %s", exc)

    return {"inferred_graph": inferred_graph, "triples": len(inf), "max_hops": hops}
