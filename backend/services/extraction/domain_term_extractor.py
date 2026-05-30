"""Domain term extraction — BusinessTerm triples from Python domain model code."""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, concept_slug, domain_iri, kb_graph_iri, term_iri
from services.extraction.code_patterns.diagnostics import GitDiagnostics
from services.extraction.code_patterns.python_domain import extract_python_domain_terms
from services.extraction.code_patterns.router import entry_path
from services.ontology_triple_cleaner import RawTriple

_logger = logging.getLogger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
SKOS_DEF = "http://www.w3.org/2004/02/skos/core#definition"
SKOS_ALT = "http://www.w3.org/2004/02/skos/core#altLabel"


def extract_domain_term_triples(
    *,
    kb_id: int,
    entries: list[Any],
    domain_id: int | None = None,
    diagnostics: GitDiagnostics | None = None,
    extraction_config: dict[str, Any] | None = None,
    auto_approve_confidence: float = 80.0,
) -> list[RawTriple]:
    """Extract BusinessTerm triples from Python Enum/dataclass definitions (rule-based)."""
    cfg = extraction_config or {}
    min_chars = int(cfg.get("min_body_chars") or 50)
    enable_domain = cfg.get("enable_domain_term_extractors", True) is not False

    if not enable_domain:
        return []

    graph = kb_graph_iri(kb_id)
    triples: list[RawTriple] = []
    seen_names: set[str] = set()
    domain_terms_found = 0

    for entry in entries:
        path = entry_path(entry)
        if not path.lower().endswith(".py"):
            continue
        body = (getattr(entry, "body", None) or "").strip()
        if not body or len(body) < min_chars:
            continue

        found, _hits = extract_python_domain_terms(body)
        if diagnostics and found:
            diagnostics.record_domain_terms(len(found))

        for item in found:
            name = (item.name or "").strip()
            if not name or name.lower() in seen_names:
                continue

            confidence = float(item.confidence)
            slug = concept_slug(name, "term")
            iri = term_iri(kb_id, slug)
            definition = (item.definition or "").strip() or name
            status = "approved" if confidence >= auto_approve_confidence else "draft"
            term_type = item.term_type or "entity"

            triples.extend([
                RawTriple(iri, RDF_TYPE, f"{NS}BusinessTerm", True, graph=graph, confidence=confidence),
                RawTriple(iri, SKOS_PREF, name, False, "zh", graph, confidence),
                RawTriple(iri, SKOS_DEF, definition, False, "zh", graph, confidence),
                RawTriple(iri, f"{NS}termType", term_type, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}approvalStatus", status, False, graph=graph, confidence=confidence),
                RawTriple(iri, f"{NS}confidence", str(confidence), False, graph=graph, confidence=confidence),
            ])

            effective_domain_id = domain_id if domain_id is not None else kb_id
            triples.append(
                RawTriple(
                    iri,
                    f"{NS}belongsToDomain",
                    domain_iri(effective_domain_id),
                    True,
                    graph=graph,
                    confidence=confidence,
                )
            )

            if item.code_name and item.code_name.lower() != name.lower():
                triples.append(
                    RawTriple(iri, SKOS_ALT, item.code_name, False, "zh", graph, confidence)
                )

            for field_name in item.related_fields:
                triples.append(
                    RawTriple(iri, f"{NS}mapsToColumn", field_name, True, graph=graph, confidence=confidence)
                )

            seen_names.add(name.lower())
            domain_terms_found += 1

    _logger.info(
        "Domain term extraction for kb=%s: %d terms → %d triples",
        kb_id,
        domain_terms_found,
        len(triples),
    )
    return triples
