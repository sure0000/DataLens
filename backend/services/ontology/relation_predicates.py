"""Shared relation predicate definitions for ontology graph views."""

from __future__ import annotations

from ontology import NS

SKOS_NS = "http://www.w3.org/2004/02/skos/core#"

_RELATION_PREDICATES: tuple[str, ...] = (
    f"{NS}dependsOn",
    f"{NS}derivedFrom",
    f"{NS}relatedTo",
    f"{NS}joinableWith",
    f"{NS}transformsFrom",
    f"{NS}computedFromTable",
    f"{SKOS_NS}related",
    f"{SKOS_NS}broader",
    f"{SKOS_NS}narrower",
)


def relation_predicate_iris() -> tuple[str, ...]:
    return _RELATION_PREDICATES


def relation_predicate_in_clause() -> str:
    # SPARQL IN(...) requires comma-separated values.
    return ", ".join(f"<{predicate}>" for predicate in _RELATION_PREDICATES)


def relation_predicate_local_names() -> list[str]:
    return [predicate.rsplit("#", 1)[-1] if "#" in predicate else predicate.rsplit("/", 1)[-1] for predicate in _RELATION_PREDICATES]

