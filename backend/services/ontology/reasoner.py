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


class SubClassOfRule(InferenceRule):
    """Materialize rdfs:subClassOf hierarchy closure.

    IF ?a rdfs:subClassOf ?b AND ?b rdfs:subClassOf ?c THEN ?a rdfs:subClassOf ?c
    IF ?x rdf:type ?a AND ?a rdfs:subClassOf ?b THEN ?x rdf:type ?b
    """

    def __init__(self):
        super().__init__("subclass-closure", "Materialize rdfs:subClassOf hierarchy closure and type propagation")

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []

        # Build subclass hierarchy closure
        subclass_closure: dict[URIRef, set[URIRef]] = {}
        for s, o in graph.subject_objects(RDFS.subClassOf):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                subclass_closure.setdefault(s, set()).add(o)

        # Transitive closure of subclass hierarchy
        changed = True
        while changed:
            changed = False
            for s in list(subclass_closure):
                for o in list(subclass_closure[s]):
                    if o in subclass_closure:
                        for o2 in subclass_closure[o]:
                            if o2 not in subclass_closure[s]:
                                subclass_closure[s].add(o2)
                                changed = True

        # Emit inferred subclass triples
        for s, targets in subclass_closure.items():
            for o in targets:
                if (s, RDFS.subClassOf, o) not in graph:
                    new.append((s, RDFS.subClassOf, o))

        # Type propagation: if ?x rdf:type ?a and ?a rdfs:subClassOf ?b, then ?x rdf:type ?b
        for s, t in graph.subject_objects(RDF.type):
            if isinstance(s, URIRef) and isinstance(t, URIRef) and t in subclass_closure:
                for sup in subclass_closure[t]:
                    if (s, RDF.type, sup) not in graph:
                        new.append((s, RDF.type, sup))

        return new


class SubPropertyOfRule(InferenceRule):
    """Materialize rdfs:subPropertyOf hierarchy closure.

    IF ?a rdfs:subPropertyOf ?b AND ?b rdfs:subPropertyOf ?c THEN ?a rdfs:subPropertyOf ?c
    IF ?x ?a ?y AND ?a rdfs:subPropertyOf ?b THEN ?x ?b ?y
    """

    def __init__(self):
        super().__init__("subproperty-closure", "Materialize rdfs:subPropertyOf hierarchy closure and property propagation")

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []

        # Build subproperty hierarchy closure
        subprop_closure: dict[URIRef, set[URIRef]] = {}
        for s, o in graph.subject_objects(RDFS.subPropertyOf):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                subprop_closure.setdefault(s, set()).add(o)

        changed = True
        while changed:
            changed = False
            for s in list(subprop_closure):
                for o in list(subprop_closure[s]):
                    if o in subprop_closure:
                        for o2 in subprop_closure[o]:
                            if o2 not in subprop_closure[s]:
                                subprop_closure[s].add(o2)
                                changed = True

        # Emit inferred subPropertyOf triples
        for s, targets in subprop_closure.items():
            for o in targets:
                if (s, RDFS.subPropertyOf, o) not in graph:
                    new.append((s, RDFS.subPropertyOf, o))

        # Property propagation: if ?x ?prop ?y and ?prop rdfs:subPropertyOf ?super_prop, then ?x ?super_prop ?y
        for s, p, o in graph:
            if isinstance(p, URIRef) and p in subprop_closure:
                for sup in subprop_closure[p]:
                    if (s, sup, o) not in graph:
                        new.append((s, sup, o))

        return new


class EquivalentClassRule(InferenceRule):
    """Handle owl:equivalentClass.

    IF ?a owl:equivalentClass ?b THEN materialize bidirectional rdfs:subClassOf
    IF ?x rdf:type ?a AND ?a owl:equivalentClass ?b THEN ?x rdf:type ?b
    """

    def __init__(self):
        from rdflib.namespace import OWL
        super().__init__("equivalent-class", "Materialize owl:equivalentClass inferences")
        self._owl_equiv = OWL.equivalentClass

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []

        for s, o in graph.subject_objects(self._owl_equiv):
            if not isinstance(s, URIRef) or not isinstance(o, URIRef):
                continue
            # Bidirectional subclass
            if (s, RDFS.subClassOf, o) not in graph:
                new.append((s, RDFS.subClassOf, o))
            if (o, RDFS.subClassOf, s) not in graph:
                new.append((o, RDFS.subClassOf, s))

            # Type propagation: entities with type of one get type of the other
            for x, _ in graph.subject_objects(RDF.type):
                if isinstance(x, URIRef):
                    for ent, equiv in [(s, o), (o, s)]:
                        if (x, RDF.type, ent) in graph and (x, RDF.type, equiv) not in graph:
                            new.append((x, RDF.type, equiv))

        return new


class SWRLStyleRule(InferenceRule):
    """Simple SWRL-like rule: IF body patterns match THEN derive head triple.

    Supports basic business rule derivation, e.g.:
      IF ?metric is Metric AND ?metric computedFromTable ?table AND ?table hasMeasure ?m
      THEN ?metric relatedTo ?m
    """

    def __init__(
        self,
        name: str,
        description: str,
        body_patterns: list[tuple[str | None, str, str | None]],
        head: tuple[str, str, str],
    ):
        """Args:
            name: Rule name.
            description: Human-readable description.
            body_patterns: List of (subject_var, predicate_uri, object_var) where
                vars are prefixed with '?', None means any value.
            head: (subject_var, predicate_uri, object_var) to derive.
        """
        super().__init__(name, description)
        self.body_patterns = body_patterns
        self.head = head

    def apply(self, graph: Graph) -> list[tuple[URIRef, URIRef, Any]]:
        new: list[tuple[URIRef, URIRef, Any]] = []
        bindings_list: list[list[dict[str, URIRef | Literal]]] = []

        for subj_var, pred_uri, obj_var in self.body_patterns:
            pred = URIRef(pred_uri)
            bindings: list[dict[str, URIRef | Literal]] = []
            is_obj_var = obj_var and obj_var.startswith("?")
            is_subj_var = subj_var and subj_var.startswith("?")
            obj_constant = URIRef(obj_var) if obj_var and not is_obj_var else None
            subj_constant = URIRef(subj_var) if subj_var and not is_subj_var else None

            for s, o in graph.subject_objects(pred):
                # Filter: if obj is a constant, only match when it equals the constant
                if obj_constant is not None and o != obj_constant:
                    continue
                # Filter: if subject is a constant, only match when it equals the constant
                if subj_constant is not None and s != subj_constant:
                    continue

                binding: dict[str, URIRef | Literal] = {}
                if is_subj_var and subj_var:
                    binding[subj_var] = s
                if is_obj_var and obj_var:
                    binding[obj_var] = o
                if binding:
                    bindings.append(binding)
            bindings_list.append(bindings)

        if not bindings_list:
            return new

        # Simple join: intersect bindings where shared variables match
        # For now, do a naive cartesian product + filter
        import itertools
        for combo in itertools.product(*bindings_list):
            merged: dict[str, URIRef | Literal] = {}
            ok = True
            for b in combo:
                for k, v in b.items():
                    if k in merged and merged[k] != v:
                        ok = False
                        break
                    merged[k] = v
                if not ok:
                    break
            if not ok:
                continue

            # Resolve head
            head_s = merged.get(self.head[0])
            head_o = merged.get(self.head[2])
            if head_s is None or head_o is None:
                # Try literal match
                head_s = head_s or URIRef(self.head[0]) if self.head[0] and not self.head[0].startswith("?") else head_s
                head_o = head_o or URIRef(self.head[2]) if self.head[2] and not self.head[2].startswith("?") else head_o

            if isinstance(head_s, URIRef) and (isinstance(head_o, URIRef) or isinstance(head_o, Literal)):
                head_p = URIRef(self.head[1])
                if (head_s, head_p, head_o) not in graph:
                    new.append((head_s, head_p, head_o))

        return new


# ── Rule file parser ─────────────────────────────────────────────────────


def _resolve_uri(token: str) -> str:
    """Resolve a prefixed token like dl:formula or rdf:type to a full URI."""
    prefixes = {
        "dl:": NS,
        "rdf:": str(RDF),
        "rdfs:": str(RDFS),
        "skos:": str(SKOS),
        "owl:": "http://www.w3.org/2002/07/owl#",
        "xsd:": "http://www.w3.org/2001/XMLSchema#",
    }
    for prefix, ns in prefixes.items():
        if token.startswith(prefix):
            return ns + token[len(prefix):]
    return token


def load_swrl_rules(filepath: str | None = None) -> list[InferenceRule]:
    """Load SWRL-style inference rules from a .rules file.

    Parses Datalog-style syntax:
      [rule-name] (?a pred ?b) (?b pred ?c) -> (?a pred ?c)

    Returns a list of SWRLStyleRule instances ready for the reasoner.
    """
    import re
    from pathlib import Path

    if filepath is None:
        filepath = str(Path(__file__).resolve().parent.parent.parent / "ontology" / "rules" / "inference.rules")

    rules: list[InferenceRule] = []
    try:
        text = Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        _logger.warning("Inference rules file not found: %s", filepath)
        return rules

    # Pattern: [name] (patterns...) -> (head)
    rule_pattern = re.compile(
        r"\[([^\]]+)\]\s*(.+?)\s*->\s*\(([^)]+)\)",
        re.MULTILINE,
    )

    for match in rule_pattern.finditer(text):
        rule_name = match.group(1).strip()
        body_text = match.group(2).strip()
        head_text = match.group(3).strip()

        # Skip comment-only lines that look like rules
        if rule_name.startswith("#") or rule_name.startswith("─"):
            continue

        # Parse body patterns: (?a pred ?b) or (?a pred dl:Constant)
        body_patterns: list[tuple[str | None, str, str | None]] = []
        body_matches = re.findall(r"\((\?\w+)\s+(\S+)\s+(\?\w+|\S+:\S+)\)", body_text)
        for subj, pred, obj in body_matches:
            resolved_obj = obj if obj.startswith("?") else _resolve_uri(obj)
            body_patterns.append((subj, _resolve_uri(pred), resolved_obj))

        # Parse head: (?a pred ?c)
        head_match = re.match(r"(\?\w+)\s+(\S+)\s+(\?\w+)", head_text)
        if not head_match:
            _logger.warning("Cannot parse head of rule [%s]: %s", rule_name, head_text)
            continue

        head = (head_match.group(1), _resolve_uri(head_match.group(2)), head_match.group(3))

        if body_patterns:
            rules.append(SWRLStyleRule(
                name=rule_name,
                description=f"SWRL rule from inference.rules: {rule_name}",
                body_patterns=body_patterns,
                head=head,
            ))

    _logger.info("Loaded %d SWRL rules from %s", len(rules), filepath)
    return rules


# ── Rule set ────────────────────────────────────────────────────────────


def _default_rules() -> list[InferenceRule]:
    rules: list[InferenceRule] = [
        # Hierarchy closure
        SubClassOfRule(),
        SubPropertyOfRule(),
        EquivalentClassRule(),
        # Transitive closures
        TransitivePropertyRule("trans-derivedFrom", f"{NS}derivedFrom"),
        TransitivePropertyRule("trans-transformsFrom", f"{NS}transformsFrom"),
        TransitivePropertyRule("trans-precedes", f"{NS}precedes"),
        # Symmetric closures
        SymmetricPropertyRule("sym-joinableWith", f"{NS}joinableWith"),
        SymmetricPropertyRule("sym-exactMatch", f"{SKOS}exactMatch"),
        # Inverse properties
        InversePropertyRule(f"{SKOS}broader", f"{SKOS}narrower"),
        InversePropertyRule(f"{SKOS}narrower", f"{SKOS}broader"),
        InversePropertyRule(f"{NS}groundedBy", f"{NS}asserts"),
        InversePropertyRule(f"{NS}computedFromTable", f"{NS}usedBy"),
    ]

    # Load business-level SWRL rules from inference.rules
    try:
        swrl_rules = load_swrl_rules()
        rules.extend(swrl_rules)
    except Exception:
        _logger.warning("Failed to load SWRL rules", exc_info=True)

    return rules


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
