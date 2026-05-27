"""Nine-stage ontology triple cleaning pipeline."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SKOS, XSD

from config import get_settings
from ontology import NS, kb_graph_iri, quarantine_graph_iri
from services.ontology_entity_linker import resolve_table_ref
from services.ontology_store import insert_graph
from services.ontology_validation import validate_ttl

DL = Namespace(NS)

APPROVED = "approved"
DRAFT = "draft"
QUARANTINE = "quarantine"

# 使用字符串 URI，与 RawTriple.predicate 一致（避免 URIRef 与 str 比较失败导致全部进隔离区）
_TBOX_PREDICATES = {
    # dl: namespace predicates (auto-passed via NS prefix check, listed for explicit documentation)
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
    f"{NS}hasQualityMetric",
    f"{NS}hasQualityReport",
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
    f"{NS}completenessScore",
    f"{NS}accuracyScore",
    f"{NS}timelinessScore",
    f"{NS}consistencyScore",
    f"{NS}uniquenessScore",
    f"{NS}overallQualityScore",
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


def stage3_tbox_check(triples: list[RawTriple]) -> tuple[list[RawTriple], list[dict[str, Any]]]:
    ok: list[RawTriple] = []
    bad: list[dict[str, Any]] = []
    for t in triples:
        if t.predicate not in _TBOX_PREDICATES and not t.predicate.startswith(NS):
            bad.append({"triple": t, "reason": "unknown_predicate"})
            continue
        ok.append(t)
    return ok, bad


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
            esc = str(t.object).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}"@{t.lang} .')
        elif t.predicate in (f"{NS}confidence",):
            esc = str(t.object).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}"^^<{XSD.decimal}> .')
        elif t.predicate in (f"{NS}rowCount", f"{NS}platformId", f"{NS}chunkIndex"):
            esc = str(t.object).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}"^^<{XSD.integer}> .')
        else:
            esc = str(t.object).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'<{t.subject}> <{t.predicate}> "{esc}" .')
    return "\n".join(lines)


def clean_triples(
    triples: list[RawTriple],
    *,
    kb_id: int,
    domain_tables: list | None = None,
) -> CleanResult:
    """Run cleaning pipeline stages 1-7."""
    graph = kb_graph_iri(kb_id)
    for t in triples:
        if not t.graph:
            t.graph = graph

    stats: dict[str, int] = {"input": len(triples)}
    t1 = stage1_syntax_normalize(triples)
    stats["after_syntax"] = len(t1)

    t2, q_link = stage2_entity_link(t1, domain_tables or [])
    t3, q_tbox = stage3_tbox_check(t2)
    stats["quarantine_link"] = len(q_link)
    stats["quarantine_tbox"] = len(q_tbox)

    t5 = stage5_deduplicate(t3)
    t7 = stage7_status_gate(t5)
    stats["production"] = len(t7)

    quarantine_items = []
    for item in q_link + q_tbox:
        t = item["triple"]
        quarantine_items.append({
            "reason": item["reason"],
            "subject": t.subject,
            "predicate": t.predicate,
            "object": t.object,
            "suggestedFix": "绑定正确表 IRI 或使用已登记物理表名",
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
