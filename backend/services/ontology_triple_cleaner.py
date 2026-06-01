"""Nine-stage ontology triple cleaning pipeline."""
from __future__ import annotations

import json
import logging
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SKOS, XSD

from config import get_settings
from ontology import NS, kb_graph_iri, quarantine_graph_iri
from services.ontology_entity_linker import resolve_table_ref
from services.ontology_entity_embedder import batch_disambiguate
from services.ontology_store import insert_graph
from services.ontology_validation import validate_ttl

DL = Namespace(NS)

_logger = logging.getLogger(__name__)

# ── Predicate embedding cache (P1-4) ────────────────────────
_predicate_embeddings: dict[str, np.ndarray] | None = None
_predicate_labels: list[str] = []
_EMBED_AUTO_MAP_THRESHOLD = 0.85
_EMBED_SUGGEST_THRESHOLD = 0.60

APPROVED = "approved"
DRAFT = "draft"
QUARANTINE = "quarantine"

# 使用字符串 URI，与 RawTriple.predicate 一致（避免 URIRef 与 str 比较失败导致全部进隔离区）
_TBOX_PREDICATES = {
    # dl: namespace predicates (auto-passed via NS prefix check, listed for explicit documentation)
    f"{NS}appliesTo",
    f"{NS}mapsToColumn",
    f"{NS}computedFromTable",
    f"{NS}joinableWith",
    f"{NS}transformsFrom",
    f"{NS}leftTable",
    f"{NS}rightTable",
    f"{NS}aliasOf",
    f"{NS}derivedFrom",
    f"{NS}aggregatesOver",
    f"{NS}dependsOn",
    f"{NS}relatedTo",
    f"{NS}hasMeasure",
    f"{NS}hasDimension",
    f"{NS}materializedFrom",
    f"{NS}belongsToDataSource",
    f"{NS}belongsToDomain",
    f"{NS}hasSource",
    f"{NS}producesConcept",
    f"{NS}documentedBy",
    f"{NS}hasChunk",
    f"{NS}partOf",
    f"{NS}groundedBy",
    f"{NS}asserts",
    f"{NS}originatedFrom",
    f"{NS}precedes",
    f"{NS}generalizes",
    f"{NS}usedBy",
    f"{NS}triggers",
    # dl: quality / governance object properties
    f"{NS}hasQualityMetric",
    f"{NS}hasQualityReport",
    # DQV standard object properties
    "http://www.w3.org/ns/dqv#hasQualityMeasurement",
    "http://www.w3.org/ns/dqv#isMeasurementOf",
    "http://www.w3.org/ns/dqv#inDimension",
    "http://www.w3.org/ns/dqv#computedOn",
    # dl: datatype properties
    f"{NS}formula",
    f"{NS}caliber",
    f"{NS}confidence",
    f"{NS}approvalStatus",
    f"{NS}joinKey",
    f"{NS}joinType",
    f"{NS}platformId",
    f"{NS}semanticType",
    f"{NS}semanticDescription",
    f"{NS}dataType",
    f"{NS}nullable",
    f"{NS}businessSummary",
    f"{NS}rowCount",
    f"{NS}sensitivityLevel",
    f"{NS}sourceChunk",
    f"{NS}linkMethod",
    f"{NS}linkConfidence",
    f"{NS}inferred",
    f"{NS}rejectReason",
    f"{NS}rawTriple",
    f"{NS}suggestedFix",
    f"{NS}dimensionType",
    f"{NS}connectionString",
    f"{NS}sourceType",
    f"{NS}host",
    f"{NS}viewDefinition",
    f"{NS}title",
    f"{NS}sourceUri",
    f"{NS}mimeType",
    f"{NS}chunkText",
    f"{NS}chunkIndex",
    f"{NS}embeddingRef",
    f"{NS}transformLogic",
    f"{NS}layer",
    f"{NS}sourceField",
    f"{NS}targetField",
    f"{NS}ruleExpression",
    f"{NS}ruleType",
    f"{NS}businessOwner",
    f"{NS}steward",
    f"{NS}validFrom",
    f"{NS}validUntil",
    f"{NS}version",
    f"{NS}changeNote",
    f"{NS}certificationStatus",
    f"{NS}lastReviewedAt",
    f"{NS}reviewCycleDays",
    f"{NS}tags",
    f"{NS}overallQualityScore",
    # DQV standard datatype property
    "http://www.w3.org/ns/dqv#value",
    # RDF / RDFS / SKOS / Schema.org predicates (not in dl: namespace)
    str(RDF.type),
    str(SKOS.prefLabel),
    str(SKOS.definition),
    str(SKOS.altLabel),
    str(SKOS.scopeNote),
    str(SKOS.broader),
    str(SKOS.narrower),
    str(SKOS.related),
    str(SKOS.exactMatch),
    str(SKOS.closeMatch),
    str(SKOS.broadMatch),
    str(SKOS.narrowMatch),
    str(SKOS.relatedMatch),
    "https://schema.org/isPartOf",
    "http://purl.org/dc/terms/created",
    "http://purl.org/dc/terms/modified",
    "http://purl.org/dc/terms/description",
    "http://www.w3.org/ns/prov#wasDerivedFrom",
    "http://www.w3.org/ns/prov#wasGeneratedBy",
    "http://www.w3.org/ns/prov#used",
    "http://www.w3.org/ns/prov#wasAttributedTo",
    "http://www.w3.org/ns/prov#wasInformedBy",
}


@dataclass
class RawTriple:
    subject: str
    predicate: str
    object: str
    object_is_uri: bool = False
    lang: str | None = None
    graph: str | None = None
    confidence: float = 70.0
    source_type: str = "document"
    provenance: str | None = None


@dataclass
class CleanResult:
    production: list[RawTriple] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _normalize_literal(value: str) -> str:
    t = unicodedata.normalize("NFKC", (value or "").strip())
    return t


def _clamp_confidence(v: float) -> float:
    return max(0.0, min(100.0, round(v, 1)))


def escape_turtle_literal(value: str) -> str:
    """Escape literal for Turtle / N-Triples (newlines break Fuseki INSERT DATA)."""
    return json.dumps(str(value), ensure_ascii=False)[1:-1]


def stage1_syntax_normalize(triples: list[RawTriple]) -> list[RawTriple]:
    out: list[RawTriple] = []
    for t in triples:
        subj = _normalize_literal(t.subject)
        pred = _normalize_literal(t.predicate)
        if not subj or not pred:
            continue
        if t.object_is_uri:
            obj = _normalize_literal(t.object)
            if not obj:
                continue
            out.append(RawTriple(subj, pred, obj, True, t.lang, t.graph, _clamp_confidence(t.confidence), t.source_type, t.provenance))
        else:
            obj = _normalize_literal(str(t.object))
            if not obj:
                continue
            out.append(RawTriple(subj, pred, obj, False, t.lang, t.graph, _clamp_confidence(t.confidence), t.source_type, t.provenance))
    return out


def stage2_entity_link(
    triples: list[RawTriple],
    domain_tables: list,
) -> tuple[list[RawTriple], list[dict[str, Any]]]:
    linked: list[RawTriple] = []
    quarantine: list[dict[str, Any]] = []
    settings = get_settings()

    for t in triples:
        if t.predicate in (f"{NS}computedFromTable", f"{NS}joinableWith", f"{NS}leftTable", f"{NS}rightTable") and not t.object_is_uri:
            iri, method, conf = resolve_table_ref(str(t.object), domain_tables)
            if iri is None:
                quarantine.append({"triple": t, "reason": "unresolved_table_ref", "ref": t.object})
                continue
            if method == "ambiguous" and settings.ontology_quarantine_on_ambiguous_link:
                quarantine.append({"triple": t, "reason": "ambiguous_table_ref", "ref": t.object})
                continue
            linked.append(RawTriple(t.subject, t.predicate, iri, True, t.lang, t.graph, conf, t.source_type, t.provenance))
            linked.append(RawTriple(t.subject, f"{NS}linkMethod", method, False, None, t.graph, conf, t.source_type, t.provenance))
        else:
            linked.append(t)
    return linked, quarantine


def stage2a_entity_disambiguate(
    triples: list[RawTriple],
    existing_entities: list[dict[str, Any]] | None = None,
) -> tuple[list[RawTriple], list[dict[str, Any]]]:
    """Embedding-based entity disambiguation before TBox check.

    For each unique subject that looks like a new entity IRI, compare
    its label against the existing entity library via Sentence-BERT
    cosine similarity and either auto-merge (≥0.85), quarantine for
    LLM arbitration (0.6-0.85), or pass through as new (<0.6).

    Args:
        triples: Post-entity-link triples.
        existing_entities: List of dicts with 'name', 'iri', 'type' keys.
            If None or empty, disambiguation is skipped.

    Returns:
        (disambiguated triples, quarantine items for arbitration)
    """
    if not existing_entities:
        return triples, []

    # Collect unique subject IRIs that might be new entities
    import re
    subject_names: dict[str, str] = {}
    for t in triples:
        subj = t.subject
        # Extract a human-readable name from the IRI
        # Pattern: .../term/{slug}, .../metric/{slug}, etc.
        m = re.search(r"/([^/]+)$", subj)
        if m:
            slug = m.group(1)
            # Try to find a prefLabel among the same subject's triples
            label = slug.replace("_", " ").replace("-", " ")
            subject_names[subj] = label

    # Also extract prefLabel values for subjects that have one
    for t in triples:
        if str(t.predicate) == "http://www.w3.org/2004/02/skos/core#prefLabel":
            if t.subject in subject_names:
                subject_names[t.subject] = str(t.object)

    if not subject_names:
        return triples, []

    # Batch disambiguate
    names = list(subject_names.values())
    subjects = list(subject_names.keys())
    results = batch_disambiguate(names, existing_entities)

    # Build IRI rewrite map for auto-linked subjects
    rewrite: dict[str, str] = {}
    quarantine: list[dict[str, Any]] = []
    for subj, name, result in zip(subjects, names, results):
        if result["action"] == "auto_link" and result["match_iri"]:
            rewrite[subj] = result["match_iri"]
        elif result["action"] == "arbitrate":
            quarantine.append({
                "subject": subj,
                "candidate_name": name,
                "reason": "entity_disambiguation_arbitrate",
                "candidates": result["candidates"],
                "suggestedFix": f"手动确认 '{name}' 是否与已有实体 '{result['match_name']}' 相同",
            })

    # Rewrite triples for auto-linked subjects
    out: list[RawTriple] = []
    for t in triples:
        if t.subject in rewrite:
            new_subj = rewrite[t.subject]
            out.append(replace(t, subject=new_subj))
            # Also rewrite any object references to this subject
        elif t.object_is_uri and t.object in rewrite:
            out.append(replace(t, object=rewrite[t.object]))
        else:
            out.append(t)

    return out, quarantine


def _extract_predicate_label(iri: str) -> str:
    """Extract a human-readable label from a predicate IRI.

    e.g. 'https://datalens.local/ontology/computedFromTable' → 'computedFromTable'
    """
    # Strip fragment or trailing path segment
    if "#" in iri:
        return iri.rsplit("#", 1)[-1]
    return iri.rsplit("/", 1)[-1]


def _get_predicate_embeddings() -> dict[str, np.ndarray]:
    """Lazy-load Sentence-BERT embeddings for all known TBox predicates.

    Returns a dict mapping each known predicate URI to its embedding vector.
    Cached at module level so embeddings are computed only once.
    """
    global _predicate_embeddings, _predicate_labels
    if _predicate_embeddings is not None:
        return _predicate_embeddings

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except ImportError:
        _logger.warning("sentence-transformers not installed; predicate embedding matching disabled")
        _predicate_embeddings = {}
        _predicate_labels = []
        return {}

    labels = [_extract_predicate_label(p) for p in sorted(_TBOX_PREDICATES)]
    _predicate_labels = sorted(_TBOX_PREDICATES)

    if not labels:
        _predicate_embeddings = {}
        return {}

    embeddings = model.encode(labels, convert_to_numpy=True, show_progress_bar=False)
    _predicate_embeddings = {
        iri: np.array(emb) for iri, emb in zip(_predicate_labels, embeddings)
    }
    _logger.info("Predicate embeddings computed for %d known predicates", len(_predicate_embeddings))
    return _predicate_embeddings


def _match_predicate(predicate: str) -> tuple[str | None, float, list[dict[str, Any]]]:
    """Attempt to match an unknown predicate to a known TBox predicate via embedding similarity.

    Returns (mapped_iri_or_None, best_similarity, top3_candidates).
    """
    embeddings = _get_predicate_embeddings()
    if not embeddings:
        return None, 0.0, []

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except ImportError:
        return None, 0.0, []

    cand_label = _extract_predicate_label(predicate)
    cand_emb = np.array(model.encode([cand_label], convert_to_numpy=True)[0])

    scored: list[dict[str, Any]] = []
    for iri, emb in embeddings.items():
        sim = float(np.dot(cand_emb, emb) / (np.linalg.norm(cand_emb) * np.linalg.norm(emb) + 1e-10))
        if sim >= _EMBED_SUGGEST_THRESHOLD:
            scored.append({"iri": iri, "label": _extract_predicate_label(iri), "similarity": round(sim, 4)})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top3 = scored[:3]

    if not top3:
        return None, 0.0, []

    best = top3[0]
    if best["similarity"] >= _EMBED_AUTO_MAP_THRESHOLD:
        return best["iri"], best["similarity"], top3
    return None, best["similarity"], top3


def stage3_tbox_check(triples: list[RawTriple]) -> tuple[list[RawTriple], list[dict[str, Any]]]:
    """TBox predicate check with embedding-based fuzzy matching.

    For each triple:
      1. Exact match in _TBOX_PREDICATES → pass
      2. Starts with NS prefix (dl: namespace) → pass (explicit namespace trust)
      3. Otherwise → embedding similarity match:
         - similarity >= 0.85 → auto-map to known predicate
         - similarity >= 0.60 → quarantine with top-3 suggestions
         - similarity < 0.60  → quarantine as unknown_predicate
    """
    ok: list[RawTriple] = []
    bad: list[dict[str, Any]] = []
    for t in triples:
        if t.predicate in _TBOX_PREDICATES:
            ok.append(t)
            continue
        if t.predicate.startswith(NS):
            ok.append(t)
            continue

        # Try embedding-based matching for non-dl predicates
        mapped_iri, best_sim, candidates = _match_predicate(t.predicate)
        if mapped_iri is not None and best_sim >= _EMBED_AUTO_MAP_THRESHOLD:
            _logger.info("Auto-mapped predicate '%s' → '%s' (sim=%.3f)", t.predicate, mapped_iri, best_sim)
            ok.append(replace(t, predicate=mapped_iri))
        elif candidates:
            top_label = candidates[0]["label"]
            bad.append({
                "triple": t,
                "reason": "unknown_predicate_fuzzy",
                "suggestedFix": f"将谓词 '{_extract_predicate_label(t.predicate)}' 映射为 '{top_label}' (相似度 {best_sim:.2f})",
                "candidates": candidates,
            })
        else:
            bad.append({"triple": t, "reason": "unknown_predicate"})

    return ok, bad


def stage4a_conflict_resolve(
    triples: list[RawTriple],
) -> tuple[list[RawTriple], list[dict[str, Any]]]:
    """Multi-source conflict detection and Bayesian confidence fusion.

    1. Same (s, p, o) from different provenance → Bayesian fusion of confidence
    2. Same (s, p) with different object → conflict detection
       - 3+ sources: majority vote, minority → quarantine
       - 2 sources: higher confidence wins, lower → quarantine (reason: conflict_detected)

    Returns (resolved triples, quarantine items).
    """
    if not triples:
        return triples, []

    # Group by (subject, predicate, object)
    spo_groups: dict[tuple, list[RawTriple]] = defaultdict(list)
    for t in triples:
        key = (t.subject, t.predicate, t.object, t.object_is_uri)
        spo_groups[key].append(t)

    # Group by (subject, predicate) for conflict detection
    sp_groups: dict[tuple, list[tuple[str, bool, list[RawTriple]]]] = defaultdict(list)
    for (s, p, o, is_uri), group in spo_groups.items():
        sp_groups[(s, p)].append((o, is_uri, group))

    resolved: list[RawTriple] = []
    quarantine: list[dict[str, Any]] = []

    for (s, p), obj_entries in sp_groups.items():
        if len(obj_entries) == 1:
            # Single object value — Bayesian fuse if multiple sources
            o, is_uri, group = obj_entries[0]
            if len(group) == 1:
                resolved.append(group[0])
            else:
                # Bayesian fusion: fused_conf = 1 - ∏(1 - c_i/100)
                confidences = [t.confidence for t in group]
                prod = 1.0
                for c in confidences:
                    prod *= (1.0 - c / 100.0)
                fused_conf = round((1.0 - prod) * 100.0, 1)
                # Use the first triple as template, update confidence
                fused = replace(group[0], confidence=fused_conf)
                resolved.append(fused)
        else:
            # Conflict: same (s, p) with different objects
            sources = defaultdict(list)
            for o, is_uri, group in obj_entries:
                for t in group:
                    src_key = t.provenance or t.source_type or "unknown"
                    sources[o].append(t)

            # Rank by: (number of distinct sources, max confidence)
            def _rank_key(item: tuple[str, list[RawTriple]]) -> tuple[int, float]:
                _, grp = item
                distinct_sources = len({t.provenance or t.source_type for t in grp})
                max_conf = max(t.confidence for t in grp)
                return (distinct_sources, max_conf)

            ranked = sorted(obj_entries, key=lambda x: _rank_key((x[0], x[2])), reverse=True)
            winner_o, winner_is_uri, winner_group = ranked[0]
            winner_sources = len({t.provenance or t.source_type for t in winner_group})

            # Bayesian fuse winner group
            confidences = [t.confidence for t in winner_group]
            prod = 1.0
            for c in confidences:
                prod *= (1.0 - c / 100.0)
            winner_conf = round((1.0 - prod) * 100.0, 1)
            resolved.append(replace(winner_group[0], confidence=winner_conf))

            # Losers go to quarantine
            for o, is_uri, group in ranked[1:]:
                for t in group:
                    quarantine.append({
                        "triple": t,
                        "reason": "conflict_detected",
                        "suggestedFix": (
                            f"同一属性 '{_extract_predicate_label(p)}' 存在冲突值。"
                            f"当前采用 '{winner_o}' ({winner_sources}源, conf={winner_conf})，"
                            f"冲突值 '{o}' 被隔离。请人工确认。"
                        ),
                        "winner_value": winner_o,
                        "winner_confidence": winner_conf,
                    })

    return resolved, quarantine


def stage5_deduplicate(triples: list[RawTriple]) -> list[RawTriple]:
    seen: set[tuple] = set()
    out: list[RawTriple] = []
    for t in triples:
        if t.predicate == f"{NS}joinableWith" and t.object_is_uri:
            a, b = sorted([t.subject, t.object])
            key2 = (t.graph or "", a, t.predicate, b, True)
            if key2 in seen:
                continue
            seen.add(key2)
            out.append(RawTriple(a, t.predicate, b, True, t.lang, t.graph, t.confidence, t.source_type, t.provenance))
        else:
            key = (t.graph or "", t.subject, t.predicate, t.object, t.object_is_uri)
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return out


def stage7_status_gate(triples: list[RawTriple]) -> list[RawTriple]:
    settings = get_settings()
    out = list(triples)
    subjects = {t.subject for t in triples}
    for subj in subjects:
        confs = [t.confidence for t in triples if t.subject == subj and t.predicate == f"{NS}confidence"]
        conf = confs[0] if confs else 70.0
        status = APPROVED if conf >= settings.ontology_min_confidence_auto_approve else DRAFT
        out.append(RawTriple(subj, f"{NS}approvalStatus", status, False, None, triples[0].graph if triples else None))
    return out


def triples_to_ttl(triples: list[RawTriple]) -> str:
    lines: list[str] = []
    for t in triples:
        if t.object_is_uri:
            lines.append(f"<{t.subject}> <{t.predicate}> <{t.object}> .")
        elif t.lang:
            esc = escape_turtle_literal(str(t.object))
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}"@{t.lang} .')
        elif t.predicate in (f"{NS}confidence", "http://www.w3.org/ns/dqv#value"):
            esc = escape_turtle_literal(str(t.object))
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}"^^<{XSD.decimal}> .')
        elif t.predicate in (f"{NS}rowCount", f"{NS}platformId", f"{NS}chunkIndex"):
            esc = escape_turtle_literal(str(t.object))
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}"^^<{XSD.integer}> .')
        else:
            esc = escape_turtle_literal(str(t.object))
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}" .')
    return "\n".join(lines)


def clean_triples(
    triples: list[RawTriple],
    *,
    kb_id: int,
    domain_tables: list | None = None,
    existing_entities: list[dict[str, Any]] | None = None,
) -> CleanResult:
    """Run cleaning pipeline stages 1-7.

    Args:
        triples: Raw triples to clean.
        kb_id: Knowledge base ID.
        domain_tables: Known physical tables for entity linking.
        existing_entities: Known entities (name, iri, type) for embedding
            disambiguation. If provided, stage2a runs before TBox check.
    """
    graph = kb_graph_iri(kb_id)
    for t in triples:
        if not t.graph:
            t.graph = graph

    stats: dict[str, int] = {"input": len(triples)}
    t1 = stage1_syntax_normalize(triples)
    stats["after_syntax"] = len(t1)

    t2, q_link = stage2_entity_link(t1, domain_tables or [])
    t2a, q_disambig = stage2a_entity_disambiguate(t2, existing_entities or [])
    t3, q_tbox = stage3_tbox_check(t2a)
    t4, q_conflict = stage4a_conflict_resolve(t3)
    stats["quarantine_link"] = len(q_link)
    stats["quarantine_disambig"] = len(q_disambig)
    stats["quarantine_tbox"] = len(q_tbox)
    stats["quarantine_conflict"] = len(q_conflict)

    t5 = stage5_deduplicate(t4)
    t7 = stage7_status_gate(t5)
    stats["production"] = len(t7)

    quarantine_items = []
    for item in q_link + q_disambig + q_tbox + q_conflict:
        if "triple" in item:
            t = item["triple"]
            quarantine_items.append({
                "reason": item["reason"],
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "suggestedFix": item.get("suggestedFix", "绑定正确表 IRI 或使用已登记物理表名"),
            })
        else:
            # Direct quarantine dict from disambiguation
            quarantine_items.append({
                "reason": item.get("reason", "entity_disambiguation"),
                "subject": item.get("subject", ""),
                "predicate": "",
                "object": str(item.get("candidates", "")),
                "suggestedFix": item.get("suggestedFix", ""),
            })

    return CleanResult(production=t7, quarantine=quarantine_items, stats=stats)


def persist_clean_result(result: CleanResult, kb_id: int) -> dict[str, Any]:
    """Write production triples to store; quarantine to separate graph."""
    shacl_ok = True
    shacl_report: dict[str, Any] = {}

    inserted = 0
    if result.production:
        ttl = triples_to_ttl(result.production)
        shacl_report = validate_ttl(ttl)
        shacl_ok = shacl_report.get("conforms", True) or shacl_report.get("skipped")
        if shacl_ok:
            insert_graph(kb_graph_iri(kb_id), ttl)
            inserted = len(result.production)

    if result.quarantine:
        q_graph = quarantine_graph_iri(kb_id)
        q_lines = []
        for idx, item in enumerate(result.quarantine):
            qid = f"{NS}assertion/q/{kb_id}/{idx}"
            q_lines.append(f"<{qid}> <{RDF.type}> <{NS}QuarantinedAssertion> .")
            q_lines.append(f'<{qid}> <{NS}rejectReason> "{item.get("reason", "")}" .')
            q_lines.append(f'<{qid}> <{NS}rawTriple> "{json.dumps(item, ensure_ascii=False)[:2000].replace(chr(34), chr(92)+chr(34))}" .')
        insert_graph(q_graph, "\n".join(q_lines))

    return {
        "written": inserted,
        "candidates": len(result.production),
        "quarantined": len(result.quarantine),
        "stats": result.stats,
        "shacl": shacl_report,
        "shacl_blocked": bool(result.production) and inserted == 0 and not shacl_ok,
    }
