"""Cross-knowledge-base term equivalence detection (P2.2).

After extraction, detects skos:exactMatch relationships between newly
extracted terms and existing terms in other knowledge bases using
Sentence-BERT cosine similarity.
"""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

SKOS_PREF_LABEL = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"
SKOS_CLOSE_MATCH = "http://www.w3.org/2004/02/skos/core#closeMatch"

# Thresholds for cross-KB equivalence
EXACT_MATCH_THRESHOLD = 0.92  # High confidence — auto skos:exactMatch
CLOSE_MATCH_THRESHOLD = 0.82  # Medium confidence — skos:closeMatch (suggestion)


def _load_existing_term_labels(
    store: Any,
    kb_id: int,
) -> list[dict[str, str]]:
    """Load prefLabel + IRI of all terms across all KBs except the given one.

    Returns list of {iri, label} dicts.
    """
    query = """
        SELECT DISTINCT ?term ?label WHERE {
            GRAPH ?g {
                ?term a <https://datalens.local/ontology/BusinessTerm> ;
                      <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
            }
            FILTER(?g != <"""
    query += kb_graph_iri(kb_id)
    query += """>)
        }
    """
    try:
        rows = store.sparql_query(query)
        return [{"iri": r["term"], "label": r["label"]} for r in rows if r.get("term") and r.get("label")]
    except Exception:
        _logger.warning("Failed to query existing term labels for cross-KB equivalence", exc_info=True)
        return []


def _compute_cross_kb_matches(
    new_terms: list[dict[str, str]],
    existing_terms: list[dict[str, str]],
    threshold: float = EXACT_MATCH_THRESHOLD,
) -> list[dict[str, Any]]:
    """Compute SBERT cosine similarity between new terms and existing terms.

    Args:
        new_terms: List of {iri, label} for newly extracted terms.
        existing_terms: List of {iri, label} from other KBs.
        threshold: Cosine similarity threshold for a match.

    Returns:
        List of {source_iri, target_iri, similarity, match_type} dicts.
    """
    try:
        from services.ontology.entity_embedder import embed_texts
    except ImportError:
        _logger.warning("entity_embedder unavailable; cross-KB equivalence disabled")
        return []

    if not new_terms or not existing_terms:
        return []

    new_labels = [t["label"] for t in new_terms]
    existing_labels = [t["label"] for t in existing_terms]

    new_embs = embed_texts(new_labels)
    existing_embs = embed_texts(existing_labels)

    if new_embs is None or existing_embs is None:
        return []

    import numpy as np
    new_arr = np.array(new_embs)
    existing_arr = np.array(existing_embs)

    # Normalize
    new_norm = new_arr / (np.linalg.norm(new_arr, axis=1, keepdims=True) + 1e-10)
    existing_norm = existing_arr / (np.linalg.norm(existing_arr, axis=1, keepdims=True) + 1e-10)

    # Cosine similarity matrix: [n_new, n_existing]
    sim_matrix = np.dot(new_norm, existing_norm.T)

    matches: list[dict[str, Any]] = []
    for i, sim_row in enumerate(sim_matrix):
        best_idx = int(np.argmax(sim_row))
        best_sim = float(sim_row[best_idx])
        if best_sim >= threshold:
            match_type = "skos:exactMatch" if best_sim >= EXACT_MATCH_THRESHOLD else "skos:closeMatch"
            matches.append({
                "source_iri": new_terms[i]["iri"],
                "source_label": new_terms[i]["label"],
                "target_iri": existing_terms[best_idx]["iri"],
                "target_label": existing_terms[best_idx]["label"],
                "similarity": round(best_sim, 4),
                "match_type": match_type,
            })

    matches.sort(key=lambda m: m["similarity"], reverse=True)
    return matches


def suggest_cross_domain_mappings(
    store: Any,
    *,
    source_domain_id: int | None = None,
    threshold: float = 0.88,
) -> list[dict[str, Any]]:
    """Suggest skos:exactMatch / skos:closeMatch between terms in different domains.

    Uses SBERT cosine similarity to detect equivalent concepts across business
    domains (e.g., 「订单金额」in trade domain ≈ 「收入确认金额」in finance).

    Args:
        store: TripleStore for querying terms across all KBs.
        source_domain_id: If set, only suggest mappings FROM this domain.
            If None, compares all domain pairs.
        threshold: Cosine similarity threshold (default 0.88).

    Returns:
        List of {source_iri, source_label, source_domain, target_iri,
                 target_label, target_domain, similarity, match_type} dicts.
    """
    # Query all BusinessTerm instances with domain and label
    query = """
        PREFIX dl: <https://datalens.local/ontology/>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

        SELECT ?term ?label ?domain WHERE {
            GRAPH ?g {
                ?term a dl:BusinessTerm ;
                      skos:prefLabel ?label .
                OPTIONAL { ?term dl:belongsToDomain ?domain . }
            }
        }
    """
    try:
        rows = store.sparql_query(query)
    except Exception:
        _logger.warning("Failed to query terms for cross-domain alignment", exc_info=True)
        return []

    # Group terms by domain
    from collections import defaultdict
    domain_terms: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        term_iri = str(r.get("term", ""))
        label = str(r.get("label", ""))
        domain = str(r.get("domain", "")) if r.get("domain") else "__no_domain__"
        if term_iri and label:
            domain_terms[domain].append({"iri": term_iri, "label": label})

    domain_ids = sorted(domain_terms.keys())
    if len(domain_ids) < 2:
        _logger.info("Cross-domain alignment: fewer than 2 domains found, skipping")
        return []

    # Determine which domain pairs to compare
    if source_domain_id is not None:
        from ontology import domain_iri
        src_domain_iri = domain_iri(source_domain_id)
        if src_domain_iri not in domain_terms:
            _logger.info("Source domain %s has no terms for cross-domain alignment", src_domain_iri)
            return []
        source_domains = [src_domain_iri]
    else:
        source_domains = domain_ids

    all_matches: list[dict[str, Any]] = []

    for src_domain in source_domains:
        src_terms = domain_terms[src_domain]
        for tgt_domain in domain_ids:
            if tgt_domain == src_domain:
                continue
            tgt_terms = domain_terms[tgt_domain]
            matches = _compute_cross_kb_matches(src_terms, tgt_terms, threshold=threshold)
            for m in matches:
                m["source_domain"] = src_domain
                m["target_domain"] = tgt_domain
            all_matches.extend(matches)

    all_matches.sort(key=lambda m: m["similarity"], reverse=True)
    _logger.info(
        "Cross-domain alignment: %d mappings found across %d domains",
        len(all_matches), len(domain_ids),
    )
    return all_matches


def resolve_cross_kb_equivalences(
    triples: list[RawTriple],
    kb_id: int,
    store: Any,
    *,
    exact_threshold: float = EXACT_MATCH_THRESHOLD,
    close_threshold: float = CLOSE_MATCH_THRESHOLD,
) -> list[RawTriple]:
    """Detect cross-KB term equivalences and produce skos:exactMatch/closeMatch triples.

    Call this after all extractors complete, before writing to RDF.

    Args:
        triples: All extraction triples from the current pipeline run.
        kb_id: The knowledge base being processed.
        store: TripleStore for querying existing terms.
        exact_threshold: Cosine similarity for skos:exactMatch.
        close_threshold: Cosine similarity for skos:closeMatch.

    Returns:
        New RawTriple list of skos:exactMatch / skos:closeMatch assertions.
    """
    graph = kb_graph_iri(kb_id)

    # Collect new terms from current batch
    new_terms: dict[str, dict[str, str]] = {}  # iri → {iri, label}
    for t in triples:
        if t.predicate == SKOS_PREF_LABEL and "term/" in str(t.subject):
            iri = str(t.subject)
            label = str(t.object)
            new_terms[iri] = {"iri": iri, "label": label}

    if not new_terms:
        _logger.info("No new terms to check for cross-KB equivalence in kb=%s", kb_id)
        return []

    # Load existing terms from other KBs
    existing_terms = _load_existing_term_labels(store, kb_id)
    if not existing_terms:
        _logger.info("No existing terms in other KBs for cross-KB equivalence check")
        return []

    _logger.info(
        "Cross-KB equivalence: %d new terms vs %d existing terms from other KBs",
        len(new_terms), len(existing_terms),
    )

    # Compute exactMatch candidates
    exact_matches = _compute_cross_kb_matches(
        list(new_terms.values()), existing_terms, threshold=exact_threshold,
    )

    # Compute closeMatch candidates at lower threshold
    close_candidates = _compute_cross_kb_matches(
        list(new_terms.values()), existing_terms, threshold=close_threshold,
    )
    # Exclude already-matched pairs
    exact_pairs = {(m["source_iri"], m["target_iri"]) for m in exact_matches}
    close_matches = [
        m for m in close_candidates
        if (m["source_iri"], m["target_iri"]) not in exact_pairs
        and m["similarity"] < exact_threshold
    ]

    equivalence_triples: list[RawTriple] = []

    for match in exact_matches:
        confidence = match["similarity"] * 100
        equivalence_triples.append(RawTriple(
            match["source_iri"], SKOS_EXACT_MATCH, match["target_iri"], True,
            graph=graph, confidence=confidence, source_type="cross_kb_sbert",
        ))

    for match in close_matches:
        confidence = match["similarity"] * 100
        equivalence_triples.append(RawTriple(
            match["source_iri"], SKOS_CLOSE_MATCH, match["target_iri"], True,
            graph=graph, confidence=confidence, source_type="cross_kb_sbert",
        ))

    _logger.info(
        "Cross-KB equivalence for kb=%s: %d exactMatch, %d closeMatch",
        kb_id, len(exact_matches), len(close_matches),
    )

    return equivalence_triples
