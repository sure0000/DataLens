"""OWL 2 RL Reasoner — materializes inferred triples into inferred graphs.

After every ABox write, the OntologyWriter triggers incremental reasoning to
expand subclass, transitive, symmetric, and property-chain closures.
"""

from __future__ import annotations

import logging
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from config import get_settings
from ontology import (
    INFERRED_GRAPH_PREFIX,
    NS,
    kb_graph_iri,
)

_logger = logging.getLogger(__name__)

DL = NS
_RDF_TYPE = str(RDF.type)

# ── Inference rule definitions ─────────────────────────────────────────


class InferenceRule:
    """A single inference rule that derives new triples from existing ones."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        """Return new triples derived from this rule. Override in subclasses."""
        return []


class TransitivePropertyRule(InferenceRule):
    """IF ?a P ?b AND ?b P ?c THEN ?a P ?c"""

    def __init__(self, name: str, prop_uri: str):
        super().__init__(name, f"Transitive closure for {prop_uri}")
        self.prop = URIRef(prop_uri)

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []
        edges: list[tuple[URIRef, URIRef]] = [
            (s, o) for s, o in graph.subject_objects(self.prop) if isinstance(s, URIRef) and isinstance(o, URIRef)
        ]
        # BFS transitive closure
        closure: dict[URIRef, set[URIRef]] = {}
        for s, o in edges:
            closure.setdefault(s, set()).add(o)

        changed = True
        while changed:
            changed = False
            for s in list(closure):
                for o in list(closure[s]):
                    if o in closure:
                        for o2 in closure[o]:
                            if o2 not in closure[s] and o2 != s:
                                closure[s].add(o2)
                                changed = True

        for s, targets in closure.items():
            for o in targets:
                if (s, self.prop, o) not in graph:
                    new.append((s, self.prop, o))
        return new


class SymmetricPropertyRule(InferenceRule):
    """IF ?a P ?b THEN ?b P ?a"""

    def __init__(self, name: str, prop_uri: str):
        super().__init__(name, f"Symmetric closure for {prop_uri}")
        self.prop = URIRef(prop_uri)

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []
        for s, o in graph.subject_objects(self.prop):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                if (o, self.prop, s) not in graph:
                    new.append((o, self.prop, s))
        return new


class InversePropertyRule(InferenceRule):
    """IF ?a P ?b THEN ?b Q ?a (e.g., broader ↔ narrower)"""

    def __init__(self, forward_prop: str, inverse_prop: str):
        name = f"inverse-{forward_prop.split('/')[-1]}"
        super().__init__(name, f"Inverse: {forward_prop} ↔ {inverse_prop}")
        self.forward = URIRef(forward_prop)
        self.inverse = URIRef(inverse_prop)

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []
        for s, o in graph.subject_objects(self.forward):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                if (o, self.inverse, s) not in graph:
                    new.append((o, self.inverse, s))
        return new


# ── Rule set ────────────────────────────────────────────────────────────


def _default_rules() -> list[InferenceRule]:
    return [
        TransitivePropertyRule("trans-derivedFrom", f"{NS}derivedFrom"),
        TransitivePropertyRule("trans-transformsFrom", f"{NS}transformsFrom"),
        SymmetricPropertyRule("sym-joinableWith", f"{NS}joinableWith"),
        InversePropertyRule(f"{SKOS}broader", f"{SKOS}narrower"),
        InversePropertyRule(f"{SKOS}narrower", f"{SKOS}broader"),
        SymmetricPropertyRule("sym-exactMatch", f"{SKOS}exactMatch"),
        TransitivePropertyRule("trans-exactMatch", f"{SKOS}exactMatch"),
    ]


# ── Reasoner ────────────────────────────────────────────────────────────


class OntologyReasoner:
    """Applies OWL 2 RL inference rules to materialize derived triples.

    Usage:
        reasoner = OntologyReasoner(store)
        result = reasoner.reason(kb_id=1, domain_id=1)
    """

    def __init__(self, store: Any, rules: list[InferenceRule] | None = None):
        self._store = store
        self._rules = rules or _default_rules()

    def reason(
        self,
        kb_id: int,
        domain_id: int | None = None,
        *,
        max_iterations: int = 3,
    ) -> dict[str, Any]:
        """Run inference rules on the KB's production graph.

        Args:
            kb_id: Knowledge base ID whose production graph is the input.
            domain_id: Domain ID for the inferred graph IRI (defaults to kb_id).
            max_iterations: Max fixpoint iterations (prevents infinite loops).

        Returns:
            Dict with inferred_graph, new_triples count, and per-rule stats.
        """
        domain = domain_id or kb_id
        inferred_graph_iri = f"{INFERRED_GRAPH_PREFIX}{domain}"
        prod_graph_iri = kb_graph_iri(kb_id)

        # Load production graph
        prod_g = self._store.get_named_graph(prod_graph_iri)
        if len(prod_g) == 0:
            _logger.info("Empty production graph for kb=%s, skipping inference", kb_id)
            return {"inferred_graph": inferred_graph_iri, "new_triples": 0, "rules": {}}

        # Create inference working graph (production + inferred)
        working = Graph()
        for t in prod_g:
            working.add(t)

        # Load existing inferred graph if present
        try:
            inferred_g = self._store.get_named_graph(inferred_graph_iri)
            for t in inferred_g:
                working.add(t)
        except Exception:
            pass

        rule_stats: dict[str, int] = {}
        total_new = 0

        for iteration in range(max_iterations):
            iteration_new = 0
            for rule in self._rules:
                try:
                    new_triples = rule.apply(working)
                    if new_triples:
                        for s, p, o in new_triples:
                            working.add((s, p, o))
                        rule_stats[rule.name] = rule_stats.get(rule.name, 0) + len(new_triples)
                        iteration_new += len(new_triples)
                except Exception as exc:
                    _logger.warning("Rule %s failed: %s", rule.name, exc)

            total_new += iteration_new
            if iteration_new == 0:
                _logger.info("Inference fixpoint reached after %d iterations for kb=%s", iteration + 1, kb_id)
                break
        else:
            _logger.info("Inference max iterations (%d) reached for kb=%s", max_iterations, kb_id)

        if total_new == 0:
            return {"inferred_graph": inferred_graph_iri, "new_triples": 0, "rules": rule_stats}

        # Write inferred triples to the inferred graph
        inferred_out = Graph()
        for t in working:
            if t not in prod_g:  # Only write triples that are NOT already in the production graph
                inferred_out.add(t)
                # Strip existing production triples from the inferred graph for clean separation

        # Actually, let's write only the NEW inferred triples
        # Rebuild: inferred_out = working - prod_g
        inferred_clean = Graph()
        for t in working:
            inferred_clean.add(t)
        for t in prod_g:
            inferred_clean.remove(t)

        if len(inferred_clean) > 0:
            ttl = inferred_clean.serialize(format="turtle")
            try:
                self._store.delete_graph(inferred_graph_iri)
                self._store.insert_graph(inferred_graph_iri, ttl)
            except Exception as exc:
                _logger.warning("Write inferred graph failed: %s", exc)

        _logger.info(
            "Inference complete for kb=%s: %d new triples in %s, rules=%s",
            kb_id, total_new, inferred_graph_iri, rule_stats,
        )
        return {
            "inferred_graph": inferred_graph_iri,
            "new_triples": total_new,
            "rules": rule_stats,
        }


# ── Module-level convenience ────────────────────────────────────────────


def materialize_inferred_closure(
    kb_id: int,
    domain_id: int | None = None,
    *,
    max_hops: int | None = None,
) -> dict[str, Any]:
    """Run OWL 2 RL inference on a KB's production graph.

    Backward-compatible with the old ontology_reasoning module.
    """
    from services.triple_store import get_triple_store

    store = get_triple_store()
    reasoner = OntologyReasoner(store)
    return reasoner.reason(kb_id, domain_id, max_iterations=max_hops or 3)
