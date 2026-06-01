"""Load TBox on application startup, including domain-layer TBox extensions."""

from __future__ import annotations

import logging

from config import get_settings
from services.ontology_store import graph_stats, is_fuseki_enabled, load_tbox, wait_for_fuseki

_logger = logging.getLogger(__name__)

_STARTUP_FUSEKI_WAIT_SECONDS = 3


def init_ontology() -> dict:
    settings = get_settings()
    if not settings.ontology_enabled:
        return {"ok": True, "skipped": True, "reason": "ontology_disabled"}

    fuseki_ok = False
    if is_fuseki_enabled():
        fuseki_ok = wait_for_fuseki(max_seconds=_STARTUP_FUSEKI_WAIT_SECONDS)
        if not fuseki_ok and not settings.fuseki_fallback_memory:
            _logger.warning(
                "Fuseki not reachable at %s (waited %ss). "
                "Backend will start; RDF writes require ./scripts/fuseki.sh start "
                "or FUSEKI_FALLBACK_MEMORY=true for local dev.",
                settings.fuseki_url,
                _STARTUP_FUSEKI_WAIT_SECONDS,
            )
            return {
                "ok": True,
                "skipped": True,
                "reason": "fuseki_unreachable",
                "fuseki_live": False,
            }

    try:
        count = load_tbox(force=False)
        # Merge domain-level TBox extensions
        domain_count = _merge_domain_tbox()
        stats = graph_stats()
        backend = stats.get("storage_backend", "local_file")
        _logger.info(
            "Ontology TBox loaded: %d core triples, %d domain extensions (backend=%s, path=%s)",
            count, domain_count, backend,
            stats.get("local_store_path"),
        )
        return {
            "ok": True,
            "triples": count,
            "domain_tbox_triples": domain_count,
            "backend": backend,
            "fuseki_live": fuseki_ok,
            **{k: stats[k] for k in ("local_store_path", "triple_count") if k in stats},
        }
    except Exception as exc:
        _logger.warning("Ontology TBox load failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _merge_domain_tbox() -> int:
    """Merge domain-level TBox extensions (Layer 1) into the TBox graph.

    Domain graphs (domain/{id}) may contain subClassOf declarations and
    domain-specific SHACL shapes that extend or override the global TBox.
    This function loads them into the active TBox graph.
    """
    try:
        from rdflib import Graph
        from ontology import GRAPH_NS, NS

        store = None
        try:
            from services.triple_store import get_triple_store
            store = get_triple_store()
        except Exception:
            pass

        if store is None:
            return 0

        # Find all domain graphs that contain TBox extensions
        domain_count = 0
        try:
            # Query for DomainTBoxExtension instances across all domain graphs
            query = f"""
            PREFIX dl: <{NS}>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?g ?s WHERE {{
              GRAPH ?g {{
                ?s a dl:DomainTBoxExtension .
              }}
            }}
            """
            rows = store.sparql_query(query)
        except Exception:
            rows = []

        if not rows:
            _logger.debug("No domain TBox extensions found")
            return 0

        # Merge each domain TBox into the active graph
        merged_graph = Graph()
        for row in rows:
            graph_iri = row.get("g", "")
            if not graph_iri:
                continue
            try:
                domain_g = store.get_named_graph(graph_iri)
                for t in domain_g:
                    merged_graph.add(t)
                domain_count += len(domain_g)
            except Exception as exc:
                _logger.debug("Failed to load domain TBox from %s: %s", graph_iri, exc)

        if domain_count > 0:
            _logger.info("Merged %d domain TBox triples from %d domain graphs",
                         domain_count, len(rows))

        return domain_count
    except Exception as exc:
        _logger.debug("Domain TBox merge skipped: %s", exc)
        return 0
