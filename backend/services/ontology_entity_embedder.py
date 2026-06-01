"""Public API for entity embedding disambiguation (re-exports from ontology/)."""
from __future__ import annotations

from services.ontology.entity_embedder import (  # noqa: F401
    batch_disambiguate,
    embed_single,
    embed_texts,
    find_best_match,
)
