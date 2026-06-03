"""Hybrid ontology concept routing: substring SPARQL + keyword overlap + embedding similarity."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from models import Embedding
from ontology import NS, kb_graph_iri
from services.embedding_service import ONTOLOGY_CONCEPT_EMBEDDING_REF, _embed

_logger = logging.getLogger(__name__)

MIN_LABEL_LEN = 2
EMBED_PROBE_TOP_K = 24
MIN_EMBED_SIMILARITY = 0.50
MIN_KEYWORD_SCORE = 0.42
# 保持与 MIN_KEYWORD_SCORE 一致，避免 keyword 有效匹配被误杀
MIN_MERGED_SCORE = 0.42


def iri_to_embedding_ref_id(iri: str) -> int:
    digest = hashlib.sha256((iri or "").encode("utf-8")).digest()
    # PostgreSQL Integer is 32-bit signed; keep hash in [0, 2^31-1)
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def _kb_content_prefix(kb_id: int) -> str:
    return f"kb_id:{kb_id}\n"


def escape_sparql_literal(text: str, *, max_len: int = 500) -> str:
    s = (text or "")[:max_len]
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def _token_set(text: str) -> set[str]:
    """Split text into tokens: alphanumeric words stay whole, CJK chars are individual."""
    # [a-zA-Z0-9_]+ = English words/numbers stay together
    # [\u4e00-\u9fff] = each CJK character is its own token
    return set(re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", (text or "").lower()))


def keyword_score(label: str, question: str, *, definition: str = "") -> float:
    """Score whether question text aligns with a concept label (name in question wins)."""
    label_l = (label or "").strip().lower()
    q_l = (question or "").strip().lower()
    if not label_l or not q_l:
        return 0.0
    if label_l in q_l:
        return 1.0
    def_l = (definition or "").strip().lower()
    if def_l and len(def_l) >= MIN_LABEL_LEN and def_l in q_l:
        return 0.88
    name_tokens = _token_set(label_l)
    if not name_tokens:
        return 0.0
    q_tokens = _token_set(q_l)
    overlap = len(name_tokens & q_tokens) / len(name_tokens)
    return overlap * 0.55


def _sparql_specificity_score(label: str, question: str) -> float:
    """Score SPARQL substring matches by label length.

    SPARQL CONTAINS is high-precision for Chinese text: if a concept label
    appears as a literal substring of the question, it is almost always
    relevant.  We use a high base score (0.60) plus a per-character bonus
    to reward longer / more specific labels while ensuring even short
    labels survive the merge threshold (MIN_MERGED_SCORE=0.42).

    Scale: len=2 → 0.68, len=3 → 0.72, len=4 → 0.76,
           len=5 → 0.80, ..., len=10 → 1.00

    altLabel / definition matches (no exact substring) get a neutral 0.35
    score, which indicates they came from SPARQL but may need support from
    keyword or embedding to survive the merge.
    """
    label_l = (label or "").strip().lower()
    q_l = (question or "").strip().lower()
    if not label_l or not q_l:
        return 0.35
    if label_l in q_l:
        return round(min(0.60 + len(label_l) * 0.04, 1.0), 4)
    # altLabel or definition matched instead of the label itself
    return 0.35


def build_concept_embedding_text(
    *,
    label: str,
    definition: str = "",
    formula: str = "",
    caliber: str = "",
    concept_type: str = "",
) -> str:
    parts = [p for p in [label, definition, formula, caliber, concept_type] if (p or "").strip()]
    return "；".join(parts)


def format_concept_embedding_content(
    *,
    kb_id: int,
    iri: str,
    concept_type: str,
    label: str,
    body_text: str,
) -> str:
    return (
        f"{_kb_content_prefix(kb_id)}"
        f"iri:{iri}\n"
        f"type:{concept_type}\n"
        f"label:{label}\n\n"
        f"{body_text}"
    )


def parse_concept_embedding_content(content: str) -> dict[str, str]:
    lines = (content or "").split("\n")
    meta: dict[str, str] = {"kb_id": "", "iri": "", "type": "", "label": ""}
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("kb_id:"):
            meta["kb_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("iri:"):
            meta["iri"] = line.split(":", 1)[1].strip()
        elif line.startswith("type:"):
            meta["type"] = line.split(":", 1)[1].strip()
        elif line.startswith("label:"):
            meta["label"] = line.split(":", 1)[1].strip()
        elif line.strip() == "" and meta["iri"]:
            body_start = i + 1
            break
    meta["body"] = "\n".join(lines[body_start:]).strip()
    return meta


def _cosine_similarity_from_distance(dist: float) -> float:
    return max(0.0, 1.0 - float(dist))


def delete_kb_ontology_concept_embeddings(db: Session, kb_id: int, *, commit: bool = False) -> None:
    prefix = _kb_content_prefix(kb_id)
    db.execute(
        delete(Embedding).where(
            Embedding.ref_type == ONTOLOGY_CONCEPT_EMBEDDING_REF,
            Embedding.content.like(f"{prefix}%"),
        )
    )
    if commit:
        db.commit()


def refresh_kb_ontology_concept_embeddings(db: Session, kb_id: int, *, commit: bool = True) -> int:
    """Index Metric + BusinessTerm nodes from RDF into pgvector for semantic routing."""
    from services.ontology.reader import OntologyReader
    from services.triple_store import get_triple_store

    store = get_triple_store()
    from config import get_settings

    if not (store.probe_fuseki(timeout=2.0) or get_settings().ontology_local_store_enabled):
        return 0

    reader = OntologyReader(store)
    delete_kb_ontology_concept_embeddings(db, kb_id, commit=False)
    count = 0
    for class_name, list_fn in (
        ("Metric", reader.list_metrics),
        ("BusinessTerm", reader.list_terms),
        ("Dimension", reader.list_dimensions),
        ("BusinessRule", reader.list_business_rules),
        ("BusinessConcept", reader.list_business_concepts),
    ):
        rows = list_fn(kb_id)
        for row in rows:
            iri = str(row.get("iri") or "").strip()
            label = str(row.get("label") or "").strip()
            if not iri or not label:
                continue
            # Map class-specific descriptive fields to the embedding body
            if class_name == "Dimension":
                desc_field = str(row.get("dimensionType") or "")
            elif class_name == "BusinessRule":
                desc_field = str(row.get("ruleExpression") or "")
            else:
                desc_field = str(row.get("definition") or "")
            body = build_concept_embedding_text(
                label=label,
                definition=desc_field,
                formula=str(row.get("formula") or ""),
                caliber=str(row.get("caliber") or ""),
                concept_type=class_name,
            )
            content = format_concept_embedding_content(
                kb_id=kb_id,
                iri=iri,
                concept_type=class_name,
                label=label,
                body_text=body,
            )
            ref_id = iri_to_embedding_ref_id(iri)
            vec = _embed([body])[0]
            db.add(
                Embedding(
                    ref_type=ONTOLOGY_CONCEPT_EMBEDDING_REF,
                    ref_id=ref_id,
                    content=content,
                    embedding=vec,
                )
            )
            count += 1
    if commit:
        db.commit()
    return count


def search_ontology_concept_embeddings(
    db: Session,
    kb_ids: list[int],
    question: str,
    *,
    query_vector: list[float] | None = None,
    top_k: int = 12,
    min_similarity: float = MIN_EMBED_SIMILARITY,
) -> list[dict[str, Any]]:
    q = (question or "").strip()
    if not q or not kb_ids:
        return []
    try:
        qv = query_vector if query_vector is not None else _embed([q])[0]
    except Exception as exc:
        _logger.warning("Ontology concept embed failed: %s", exc)
        return []

    from pgvector.sqlalchemy import Vector
    from sqlalchemy import cast

    prefixes = [_kb_content_prefix(int(k)) for k in kb_ids]
    stmt = (
        select(
            Embedding.content,
            Embedding.embedding.cosine_distance(cast(qv, Vector(1536))).label("dist"),
        )
        .where(
            Embedding.ref_type == ONTOLOGY_CONCEPT_EMBEDDING_REF,
            or_(*[Embedding.content.like(f"{p}%") for p in prefixes]),
        )
        .order_by("dist")
        .limit(max(top_k, EMBED_PROBE_TOP_K))
    )
    try:
        rows = db.execute(stmt).all()
    except Exception as exc:
        _logger.warning("Ontology concept vector search failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for content, dist in rows:
        meta = parse_concept_embedding_content(str(content or ""))
        iri = meta.get("iri") or ""
        if not iri or iri in seen:
            continue
        sim = _cosine_similarity_from_distance(float(dist))
        if sim < min_similarity:
            continue
        seen.add(iri)
        out.append(
            {
                "iri": iri,
                "type": meta.get("type") or "",
                "label": meta.get("label") or "",
                "definition": meta.get("body") or "",
                "confidence": sim,
                "status": "",
                "match_score": sim,
                "match_source": "embedding",
            }
        )
        if len(out) >= top_k:
            break
    return out


def route_concepts_sparql(
    store: Any,
    kb_ids: list[int],
    query_text: str,
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """SPARQL: question contains concept label/altLabel/definition (correct direction)."""
    ns = NS
    skos = "http://www.w3.org/2004/02/skos/core#"
    q_esc = escape_sparql_literal(query_text)
    graph_blocks = []
    for kb_id in kb_ids:
        g = kb_graph_iri(kb_id)
        graph_blocks.append(f"""
            {{ GRAPH <{g}> {{
              ?concept a ?type ;
                       <{skos}prefLabel> ?label .
              OPTIONAL {{ ?concept <{skos}altLabel> ?altLabel . }}
              OPTIONAL {{ ?concept <{skos}definition> ?definition . }}
              OPTIONAL {{ ?concept <{ns}confidence> ?confidence . }}
              OPTIONAL {{ ?concept <{ns}approvalStatus> ?status . }}
              FILTER(
                (STRLEN(STR(?label)) >= {MIN_LABEL_LEN} && CONTAINS(LCASE("{q_esc}"), LCASE(STR(?label)))) ||
                (BOUND(?altLabel) && STRLEN(STR(?altLabel)) >= {MIN_LABEL_LEN} && CONTAINS(LCASE("{q_esc}"), LCASE(STR(?altLabel)))) ||
                (BOUND(?definition) && STRLEN(STR(?definition)) >= 4 && CONTAINS(LCASE("{q_esc}"), LCASE(STR(?definition))))
              )
            }} }}
            """)

    sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?concept ?type ?label ?definition ?confidence ?status WHERE {{
          {' UNION '.join(graph_blocks)}
        }}
        ORDER BY DESC(?confidence)
        LIMIT {top_k}
        """
    try:
        rows = store.sparql_query(sparql)
    except Exception as exc:
        _logger.warning("Concept SPARQL routing failed: %s", exc)
        return []

    return [
        {
            "iri": str(r.get("concept", "")),
            "type": str(r.get("type", "")).replace(ns, ""),
            "label": str(r.get("label", "")),
            "definition": str(r.get("definition", "")),
            "confidence": float(r.get("confidence", 0) or 0),
            "status": str(r.get("status", "")),
            "match_score": _sparql_specificity_score(str(r.get("label", "")), query_text),
            "match_source": "sparql_substring",
        }
        for r in rows
    ]


def route_concepts_keyword_memory(
    store: Any,
    kb_ids: list[int],
    query_text: str,
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """In-memory keyword overlap over listed metrics/terms (embedding fallback supplement)."""
    from services.ontology.reader import OntologyReader

    reader = OntologyReader(store)
    scored: list[tuple[float, dict[str, Any]]] = []
    for kb_id in kb_ids:
        for class_name, rows_fn in (
            ("Metric", reader.list_metrics),
            ("BusinessTerm", reader.list_terms),
            ("Dimension", reader.list_dimensions),
            ("BusinessRule", reader.list_business_rules),
            ("BusinessConcept", reader.list_business_concepts),
        ):
            for row in rows_fn(kb_id, limit=400):
                label = str(row.get("label") or "").strip()
                iri = str(row.get("iri") or "").strip()
                if not label or not iri:
                    continue
                # Map class-specific descriptive fields for keyword scoring
                if class_name == "Dimension":
                    definition = str(row.get("dimensionType") or "")
                elif class_name == "BusinessRule":
                    definition = str(row.get("ruleExpression") or "")
                else:
                    definition = str(row.get("definition") or "")
                score = keyword_score(label, query_text, definition=definition)
                if score < MIN_KEYWORD_SCORE:
                    continue
                scored.append(
                    (
                        score,
                        {
                            "iri": iri,
                            "type": class_name,
                            "label": label,
                            "definition": definition,
                            "confidence": float(row.get("confidence") or 0),
                            "status": str(row.get("status") or ""),
                            "match_score": score,
                            "match_source": "keyword",
                        },
                    )
                )
    scored.sort(key=lambda x: (-x[0], -x[1].get("confidence", 0)))
    return [item for _, item in scored[:top_k]]


def merge_concept_candidates(
    *candidate_lists: list[dict[str, Any]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Merge by IRI, keep best match_score.

    SPARQL substring matches (CONTAINS label in question) are authoritative
    and are NOT subject to the MIN_MERGED_SCORE threshold — if the concept
    label literally appears in the user's question, it's relevant.  Only
    embedding and keyword matches are filtered by MIN_MERGED_SCORE.
    """
    by_iri: dict[str, dict[str, Any]] = {}
    for lst in candidate_lists:
        for c in lst:
            iri = str(c.get("iri") or "").strip()
            if not iri:
                continue
            score = float(c.get("match_score") or 0)
            prev = by_iri.get(iri)
            if prev is None or score > float(prev.get("match_score") or 0):
                by_iri[iri] = dict(c)
    merged = sorted(
        by_iri.values(),
        key=lambda x: (-float(x.get("match_score") or 0), -float(x.get("confidence") or 0), str(x.get("iri") or "")),
    )
    kept: list[dict[str, Any]] = []
    for c in merged:
        source = str(c.get("match_source") or "")
        score = float(c.get("match_score") or 0)
        # SPARQL substring matches are authoritative — preserve regardless of score
        if source == "sparql_substring":
            kept.append(c)
        elif score >= MIN_MERGED_SCORE:
            kept.append(c)
        # else: drop low-score embedding/keyword candidates
    return kept[:top_k]


def hybrid_route_concepts(
    store: Any,
    db: Session | None,
    kb_ids: list[int],
    query_text: str,
    *,
    top_k: int = 10,
    query_vector: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Substring SPARQL + optional embedding + keyword memory merge."""
    q = (query_text or "").strip()
    if not q or not kb_ids:
        return []

    sparql_hits = route_concepts_sparql(store, kb_ids, q, top_k=top_k)
    embed_hits: list[dict[str, Any]] = []
    keyword_hits: list[dict[str, Any]] = []

    sparql_iris = {c.get("iri") for c in sparql_hits if c.get("iri")}

    if db is not None:
        embed_hits = search_ontology_concept_embeddings(
            db, kb_ids, q, query_vector=query_vector, top_k=top_k
        )
        # SPARQL hits are authoritative; embedding only adds concepts not in SPARQL
        if sparql_iris:
            embed_hits = [c for c in embed_hits if c.get("iri") not in sparql_iris]

    keyword_hits = route_concepts_keyword_memory(store, kb_ids, q, top_k=top_k)
    # SPARQL hits are authoritative; keyword only adds concepts not in SPARQL or embedding
    if sparql_iris:
        keyword_hits = [c for c in keyword_hits if c.get("iri") not in sparql_iris]

    return merge_concept_candidates(sparql_hits, embed_hits, keyword_hits, top_k=top_k)
