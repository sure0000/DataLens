"""Knowledge Graph Embedding completer — discover missing relations via TransE/ComplEx.

P3: Introduce embedding-based completion to automatically suggest high-confidence
missing triples. Candidates enter quarantine for human review.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)


class KGECompleter:
    """Knowledge Graph Embedding completer for relation prediction.

    Uses a simplified TransE-like scoring: head + relation ≈ tail.
    For production use, swap in pykeen / ampligraph for full ComplEx/RotatE support.

    Usage:
        completer = KGECompleter()
        completer.fit(triples)  # Train on existing graph
        candidates = completer.predict_top_k(head="...", relation="...", k=10)
    """

    def __init__(self, embedding_dim: int = 128, learning_rate: float = 0.01):
        self._dim = embedding_dim
        self._lr = learning_rate
        self._entity_to_idx: dict[str, int] = {}
        self._idx_to_entity: dict[int, str] = {}
        self._relation_to_idx: dict[str, int] = {}
        self._idx_to_relation: dict[int, str] = {}
        self._entity_embeddings: np.ndarray | None = None
        self._relation_embeddings: np.ndarray | None = None
        self._trained = False

    @property
    def entity_count(self) -> int:
        return len(self._entity_to_idx)

    @property
    def relation_count(self) -> int:
        return len(self._relation_to_idx)

    def _build_vocab(self, triples: list[tuple[str, str, str]]) -> None:
        for s, p, o in triples:
            if s not in self._entity_to_idx:
                idx = len(self._entity_to_idx)
                self._entity_to_idx[s] = idx
                self._idx_to_entity[idx] = s
            if o not in self._entity_to_idx:
                idx = len(self._entity_to_idx)
                self._entity_to_idx[o] = idx
                self._idx_to_entity[idx] = o
            if p not in self._relation_to_idx:
                idx = len(self._relation_to_idx)
                self._relation_to_idx[p] = idx
                self._idx_to_relation[idx] = p

    def fit(
        self,
        triples: list[tuple[str, str, str]],
        epochs: int = 100,
        batch_size: int = 128,
        negative_samples: int = 2,
    ) -> dict[str, Any]:
        """Train TransE embeddings on the given triples.

        Args:
            triples: List of (subject, predicate, object) where each is an IRI string.
            epochs: Number of training epochs.
            batch_size: Mini-batch size.
            negative_samples: Number of negative samples per positive.

        Returns:
            Dict with training stats (epochs, final_loss, entity_count, relation_count).
        """
        if len(triples) < 10:
            _logger.warning("Too few triples (%d) for KGE training", len(triples))
            return {"ok": False, "error": "insufficient_triples", "triples": len(triples)}

        self._build_vocab(triples)

        # Initialize embeddings (Xavier uniform)
        scale = np.sqrt(6.0 / self._dim)
        self._entity_embeddings = np.random.uniform(
            -scale, scale, (self.entity_count, self._dim)
        ).astype(np.float32)
        self._relation_embeddings = np.random.uniform(
            -scale, scale, (self.relation_count, self._dim)
        ).astype(np.float32)

        # Normalize entity embeddings
        self._entity_embeddings = self._entity_embeddings / (
            np.linalg.norm(self._entity_embeddings, axis=1, keepdims=True) + 1e-10
        )

        # Convert triples to index arrays
        triples_idx = np.array([
            (self._entity_to_idx[s], self._relation_to_idx[p], self._entity_to_idx[o])
            for s, p, o in triples
        ], dtype=np.int32)

        n = len(triples_idx)
        margin = 1.0
        losses: list[float] = []

        for epoch in range(epochs):
            np.random.shuffle(triples_idx)
            epoch_loss = 0.0
            batch_count = 0

            for start in range(0, n, batch_size):
                batch = triples_idx[start : start + batch_size]
                if len(batch) == 0:
                    continue

                h_idx = batch[:, 0]
                r_idx = batch[:, 1]
                t_idx = batch[:, 2]

                h = self._entity_embeddings[h_idx]
                r = self._relation_embeddings[r_idx]
                t = self._entity_embeddings[t_idx]

                # Positive score: ||h + r - t||
                pos_score = np.sum((h + r - t) ** 2, axis=1)

                # Negative sampling: corrupt tail
                neg_entities = np.random.randint(0, self.entity_count, size=(len(batch), negative_samples))
                neg_emb = self._entity_embeddings[neg_entities]
                # h + r - neg_t for each negative
                neg_score = np.sum((h[:, None, :] + r[:, None, :] - neg_emb) ** 2, axis=2)
                best_neg = np.min(neg_score, axis=1)

                # Hinge loss: max(0, margin + pos - neg)
                loss = np.maximum(0, margin + pos_score - best_neg)
                batch_loss = np.mean(loss)
                epoch_loss += batch_loss
                batch_count += 1

                # Gradient descent (simplified)
                # Positive gradient
                grad_pos = 2.0 * (h + r - t)
                # Update only for violated margin
                violated = loss > 0
                if np.any(violated):
                    lr = self._lr
                    # Update head, relation, tail for violated triples
                    self._entity_embeddings[h_idx[violated]] -= lr * grad_pos[violated]
                    self._relation_embeddings[r_idx[violated]] -= lr * grad_pos[violated]
                    self._entity_embeddings[t_idx[violated]] += lr * grad_pos[violated]

                # Normalize entity embeddings
                norms = np.linalg.norm(self._entity_embeddings, axis=1, keepdims=True) + 1e-10
                self._entity_embeddings = self._entity_embeddings / norms

            avg_loss = epoch_loss / max(batch_count, 1)
            losses.append(avg_loss)

            if (epoch + 1) % 20 == 0:
                _logger.info("KGE epoch %d/%d, loss=%.4f", epoch + 1, epochs, avg_loss)

        self._trained = True
        _logger.info("KGE training complete: %d entities, %d relations, final_loss=%.4f",
                     self.entity_count, self.relation_count, losses[-1])

        return {
            "ok": True,
            "epochs": epochs,
            "final_loss": round(float(losses[-1]), 6),
            "entity_count": self.entity_count,
            "relation_count": self.relation_count,
        }

    def predict_top_k(
        self,
        head: str | None = None,
        relation: str | None = None,
        tail: str | None = None,
        k: int = 10,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Predict top-k missing entities for a partial triple.

        Args:
            head: Subject IRI (None to predict head given relation + tail).
            relation: Predicate IRI.
            tail: Object IRI (None to predict tail given head + relation).
            k: Number of top candidates to return.
            min_score: Minimum similarity score (lower = more permissive).

        Returns:
            List of {entity_iri, score} sorted by descending score.
        """
        if not self._trained:
            _logger.warning("KGE model not trained; call fit() first")
            return []

        if relation and relation in self._relation_to_idx:
            r_idx = self._relation_to_idx[relation]
            r_emb = self._relation_embeddings[r_idx]
        else:
            return []

        if head and tail:
            return []  # Both given, nothing to predict
        if not head and not tail:
            return []  # Nothing to anchor

        if head and head in self._entity_to_idx:
            h_emb = self._entity_embeddings[self._entity_to_idx[head]]
            target_vec = h_emb + r_emb  # Predict tail
        elif tail and tail in self._entity_to_idx:
            t_emb = self._entity_embeddings[self._entity_to_idx[tail]]
            target_vec = t_emb - r_emb  # Predict head
        else:
            return []

        # Cosine similarity against all entities
        norms_e = np.linalg.norm(self._entity_embeddings, axis=1) + 1e-10
        target_norm = np.linalg.norm(target_vec) + 1e-10
        similarities = np.dot(self._entity_embeddings, target_vec) / (norms_e * target_norm)

        # Exclude the head/tail itself if already known
        if head and head in self._entity_to_idx:
            similarities[self._entity_to_idx[head]] = -1.0
        if tail and tail in self._entity_to_idx:
            similarities[self._entity_to_idx[tail]] = -1.0

        # Get top-k indices
        top_indices = np.argsort(-similarities)[:k]

        results: list[dict[str, Any]] = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < min_score:
                continue
            results.append({
                "entity_iri": self._idx_to_entity[int(idx)],
                "score": round(score, 4),
            })

        return results

    def discover_missing_relations(
        self,
        triples: list[tuple[str, str, str]],
        top_k_per_relation: int = 5,
        min_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Discover candidate missing relations from existing graph.

        For each relation type, find (head, tail) pairs that score highly
        but are not yet connected by that relation.

        Args:
            triples: Existing triples to avoid re-predicting.
            top_k_per_relation: Max candidates per relation type.
            min_score: Minimum confidence for a candidate.

        Returns:
            List of {head, relation, tail, score, status: "candidate"}.
        """
        if not self._trained:
            return []

        # Build existing edge set
        existing_edges: set[tuple[str, str, str]] = set()
        for s, p, o in triples:
            existing_edges.add((s, p, o))

        candidates: list[dict[str, Any]] = []

        # For each entity, predict top-k tails for each relation
        sample_entities = list(self._entity_to_idx.keys())[:200]  # Cap for efficiency

        for relation in self._relation_to_idx:
            for head in sample_entities:
                if len(candidates) >= top_k_per_relation * self.relation_count:
                    break

                predictions = self.predict_top_k(head=head, relation=relation, k=top_k_per_relation, min_score=min_score)
                for pred in predictions:
                    candidate_tail = pred["entity_iri"]
                    if (head, relation, candidate_tail) not in existing_edges:
                        candidates.append({
                            "head": head,
                            "relation": relation,
                            "tail": candidate_tail,
                            "score": pred["score"],
                            "status": "candidate",
                        })

        # Sort by score descending
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # Deduplicate
        seen: set[tuple[str, str, str]] = set()
        unique: list[dict[str, Any]] = []
        for c in candidates:
            key = (c["head"], c["relation"], c["tail"])
            if key not in seen:
                seen.add(key)
                unique.append(c)

        _logger.info("KGE discovered %d missing relation candidates", len(unique))
        return unique


def train_and_discover(
    triples: list[tuple[str, str, str]],
    *,
    embedding_dim: int = 128,
    epochs: int = 100,
    top_k_per_relation: int = 5,
    min_score: float = 0.5,
) -> dict[str, Any]:
    """Convenience: train KGE and discover missing relations.

    Returns dict with training stats, candidates, and training loss history.
    """
    completer = KGECompleter(embedding_dim=embedding_dim)
    train_result = completer.fit(triples, epochs=epochs)

    if not train_result.get("ok"):
        return {"ok": False, **train_result}

    candidates = completer.discover_missing_relations(
        triples,
        top_k_per_relation=top_k_per_relation,
        min_score=min_score,
    )

    return {
        "ok": True,
        "training": train_result,
        "candidates": candidates,
        "candidate_count": len(candidates),
    }
