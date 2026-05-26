"""Triple store layer — Fuseki SPARQL client with local/memory fallback."""

from services.triple_store.store import TripleStore, get_triple_store

__all__ = ["TripleStore", "get_triple_store"]
