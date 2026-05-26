"""Ontology triple store — backward-compatible wrapper.

Delegates to services.triple_store.TripleStore (no module-level globals).
New code should use TripleStore directly via dependency injection.
"""

from __future__ import annotations

from typing import Any

from services.triple_store.store import TripleStore, get_triple_store, reset_triple_store

# Backward-compat: proxy internal attribute reads to the store instance.
# Tests and legacy code that access osmod._local_dataset etc. will
# transparently read from (and write to) the singleton store instance.


def __getattr__(name: str) -> Any:
    """Proxy internal attribute reads to the singleton TripleStore instance."""
    if name.startswith("_"):
        store = get_triple_store()
        if hasattr(store, name):
            return getattr(store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "TripleStore",
    "get_triple_store",
    "reset_triple_store",
    "storage_backend",
    "is_fuseki_enabled",
    "use_fuseki_backend",
    "probe_fuseki",
    "wait_for_fuseki",
    "sparql_query",
    "insert_graph",
    "delete_graph",
    "export_graph_ttl",
    "add_triple",
    "load_tbox",
    "graph_stats",
    "get_named_graph",
    "_get_memory_store",
]


def _store() -> TripleStore:
    return get_triple_store()


def storage_backend() -> str:
    return _store().storage_backend()


def is_fuseki_enabled() -> bool:
    return _store().is_fuseki_enabled()


def use_fuseki_backend() -> bool:
    return _store().use_fuseki_backend()


def probe_fuseki(timeout: float = 3.0) -> bool:
    return _store().probe_fuseki(timeout)


def wait_for_fuseki(max_seconds: int | None = None) -> bool:
    return _store().wait_for_fuseki(max_seconds)


def sparql_query(query: str) -> list[dict[str, Any]]:
    return _store().sparql_query(query)


def insert_graph(graph_iri: str, triples_ttl: str) -> None:
    return _store().insert_graph(graph_iri, triples_ttl)


def delete_graph(graph_iri: str) -> None:
    return _store().delete_graph(graph_iri)


def export_graph_ttl(graph_iri: str | None = None) -> str:
    return _store().export_graph_ttl(graph_iri)


def add_triple(
    graph_iri: str,
    subject: str,
    predicate: str,
    obj: str | float | bool,
    *,
    obj_is_uri: bool = False,
    lang: str | None = None,
) -> None:
    return _store().add_triple(graph_iri, subject, predicate, obj, obj_is_uri=obj_is_uri, lang=lang)


def load_tbox(force: bool = False) -> int:
    return _store().load_tbox(force)


def graph_stats() -> dict[str, Any]:
    return _store().graph_stats()


def get_named_graph(graph_iri: str) -> Any:
    from rdflib import Graph
    return _store().get_named_graph(graph_iri)


def _get_local_dataset() -> Any:
    return _store()._get_local_dataset()


def _get_memory_store() -> Any:
    return _store()._get_local_dataset()
