"""Entity disambiguation via Sentence-BERT embedding similarity.

Adds a pre-link stage before entity resolution: embed candidate entity names
and compare against the existing entity library via cosine similarity.

Thresholds (configurable):
  - >= 0.85  auto-link (high confidence match)
  - 0.60-0.85 flag for LLM arbitration
  - < 0.60   treat as new entity
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)

# Lazy-loaded sentence-transformers model
_model = None
_model_name = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model() -> Any:
    """Lazy-load the Sentence-BERT model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_model_name)
            _logger.info("Entity embedder loaded: %s", _model_name)
        except ImportError:
            _logger.warning(
                "sentence-transformers not installed; entity disambiguation disabled. "
                "Install with: pip install sentence-transformers"
            )
            return None
        except Exception as exc:
            _logger.warning("Failed to load embedding model: %s", exc)
            return None
    return _model


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two normalized vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of text strings. Returns None if model unavailable."""
    model = _get_model()
    if model is None:
        return None
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return [emb.tolist() for emb in embeddings]


def embed_single(text: str) -> list[float] | None:
    """Embed a single text string."""
    result = embed_texts([text])
    return result[0] if result else None


def find_best_match(
    candidate_name: str,
    existing_entities: list[dict[str, Any]],
    *,
    auto_link_threshold: float = 0.85,
    candidate_threshold: float = 0.60,
) -> dict[str, Any] | None:
    """Find the best matching existing entity for a candidate name.

    Args:
        candidate_name: The entity name extracted by LLM.
        existing_entities: List of dicts with keys: 'name', 'iri', 'type'.
        auto_link_threshold: Cosine similarity above which to auto-link.
        candidate_threshold: Minimum similarity to consider as a match candidate.

    Returns:
        {
            "match_iri": str | None,      # IRI of best match (None if no match)
            "match_name": str | None,     # Name of best match
            "similarity": float,           # Cosine similarity score
            "action": "auto_link" | "arbitrate" | "new_entity",
            "candidates": list[dict],     # Top-3 candidates above candidate_threshold
        }
        Returns None if the embedder is unavailable.
    """
    model = _get_model()
    if model is None:
        return None

    if not existing_entities:
        return {
            "match_iri": None,
            "match_name": None,
            "similarity": 0.0,
            "action": "new_entity",
            "candidates": [],
        }

    # Embed candidate
    cand_emb = np.array(model.encode([candidate_name], convert_to_numpy=True)[0])

    # Embed all existing entity names
    existing_names = [e.get("name", "") for e in existing_entities]
    existing_embs = model.encode(existing_names, convert_to_numpy=True)

    # Compute similarities
    similarities = [
        _cosine_similarity(cand_emb, np.array(emb))
        for emb in existing_embs
    ]

    # Find top candidates above threshold
    scored: list[dict[str, Any]] = []
    for i, sim in enumerate(similarities):
        if sim >= candidate_threshold:
            scored.append({
                "iri": existing_entities[i].get("iri", ""),
                "name": existing_entities[i].get("name", ""),
                "type": existing_entities[i].get("type", ""),
                "similarity": round(sim, 4),
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top3 = scored[:3]

    if not top3:
        return {
            "match_iri": None,
            "match_name": None,
            "similarity": 0.0,
            "action": "new_entity",
            "candidates": [],
        }

    best = top3[0]
    if best["similarity"] >= auto_link_threshold:
        return {
            "match_iri": best["iri"],
            "match_name": best["name"],
            "similarity": best["similarity"],
            "action": "auto_link",
            "candidates": top3,
        }
    else:
        return {
            "match_iri": None,
            "match_name": best["name"],
            "similarity": best["similarity"],
            "action": "arbitrate",
            "candidates": top3,
        }


def batch_disambiguate(
    candidate_names: list[str],
    existing_entities: list[dict[str, Any]],
    *,
    auto_link_threshold: float = 0.85,
    candidate_threshold: float = 0.60,
) -> list[dict[str, Any]]:
    """Batch-disambiguate multiple candidate entity names.

    Returns a list of results in the same order as candidate_names.
    """
    results: list[dict[str, Any]] = []
    for name in candidate_names:
        r = find_best_match(
            name,
            existing_entities,
            auto_link_threshold=auto_link_threshold,
            candidate_threshold=candidate_threshold,
        )
        if r is None:
            results.append({
                "match_iri": None,
                "match_name": None,
                "similarity": 0.0,
                "action": "skipped",
                "candidates": [],
            })
        else:
            results.append(r)
    return results
