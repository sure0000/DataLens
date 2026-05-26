"""Quarantine manager — stores, lists, resolves, and retries rejected triples."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ontology import NS, quarantine_graph_iri

_logger = logging.getLogger(__name__)


@dataclass
class QuarantineItem:
    """A single quarantined assertion with metadata."""

    index: int
    graph: str
    reason: str
    subject: str
    predicate: str
    object: str
    object_is_uri: bool = False
    suggested_fix: str | None = None
    raw_triple: dict[str, Any] | None = None


@dataclass
class QuarantineListResult:
    items: list[QuarantineItem] = field(default_factory=list)
    total: int = 0


class QuarantineManager:
    """Manages quarantined triples in a knowledge base's quarantine named graph."""

    def __init__(self, store: Any):
        """Initialize with a triple store instance.

        Args:
            store: An OntologyStore-like object with sparql_query() and add_triple() methods.
        """
        self._store = store

    def store_rejected(
        self, kb_id: int, rejected: list[dict[str, Any]]
    ) -> int:
        """Write rejected triples to the quarantine graph.

        Each rejected item should have at minimum:
            - triple: the raw triple data
            - reason: why it was rejected

        Returns the number of items stored.
        """
        graph = quarantine_graph_iri(kb_id)
        count = 0
        for item in rejected:
            t = item.get("triple")
            if t is None:
                continue
            reason = item.get("reason", "unknown")
            idx = self._next_index(kb_id)

            subj = f"{graph}/item/{idx}"
            self._add(subj, f"{NS}rejectReason", reason, False)
            self._add(
                subj,
                f"{NS}rawTriple",
                json.dumps(self._triple_to_dict(t), ensure_ascii=False),
                False,
            )
            if item.get("suggested_fix"):
                self._add(
                    subj, f"{NS}suggestedFix", item["suggested_fix"], False
                )
            self._add(subj, str("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), f"{NS}QuarantinedAssertion", True)
            count += 1

        return count

    def list_items(self, kb_id: int) -> QuarantineListResult:
        """List all quarantined items for a knowledge base."""
        graph = quarantine_graph_iri(kb_id)
        query = f"""
            SELECT ?s ?reason ?raw ?fix
            WHERE {{
                GRAPH <{graph}> {{
                    ?s <{NS}rejectReason> ?reason .
                    OPTIONAL {{ ?s <{NS}rawTriple> ?raw . }}
                    OPTIONAL {{ ?s <{NS}suggestedFix> ?fix . }}
                }}
            }}
            ORDER BY ?s
        """
        items: list[QuarantineItem] = []
        try:
            rows = self._store.sparql_query(query)
        except Exception as exc:
            _logger.warning("Quarantine list query failed: %s", exc)
            return QuarantineListResult()

        for i, row in enumerate(rows):
            raw_data = None
            if row.get("raw"):
                try:
                    raw_data = json.loads(row["raw"])
                except json.JSONDecodeError:
                    pass

            items.append(
                QuarantineItem(
                    index=i,
                    graph=graph,
                    reason=str(row.get("reason", "")),
                    subject=str(row.get("s", "")),
                    predicate=raw_data.get("predicate", "") if raw_data else "",
                    object=raw_data.get("object", "") if raw_data else "",
                    object_is_uri=raw_data.get("object_is_uri", False) if raw_data else False,
                    suggested_fix=str(row.get("fix", "")) or None,
                    raw_triple=raw_data,
                )
            )

        return QuarantineListResult(items=items, total=len(items))

    def resolve(self, kb_id: int, item_index: int, approved: bool) -> bool:
        """Approve or reject a quarantined item.

        If approved: the triple moves from quarantine to production.
        If rejected: the item is deleted from quarantine.
        """
        graph = quarantine_graph_iri(kb_id)
        subj = f"{graph}/item/{item_index}"

        if approved:
            items = self.list_items(kb_id)
            target = None
            for item in items.items:
                if item.subject == subj:
                    target = item
                    break
            if target and target.raw_triple:
                from ontology import kb_graph_iri
                from ontology_triple_cleaner import RawTriple, clean_triples, persist_clean_result

                t = target.raw_triple
                triple = RawTriple(
                    subject=t.get("subject", ""),
                    predicate=t.get("predicate", ""),
                    object=t.get("object", ""),
                    object_is_uri=t.get("object_is_uri", False),
                    lang=t.get("lang"),
                    graph=kb_graph_iri(kb_id),
                    confidence=float(t.get("confidence", 70.0)),
                    source_type=t.get("source_type", "manual"),
                    provenance=t.get("provenance"),
                )
                result = clean_triples([triple], kb_id=kb_id)
                persist_clean_result(result, kb_id)

        # Delete the quarantine entry
        try:
            self._store.sparql_query(
                f"""
                DELETE WHERE {{
                    GRAPH <{graph}> {{
                        <{subj}> ?p ?o .
                    }}
                }}
                """
            )
            return True
        except Exception as exc:
            _logger.warning("Failed to resolve quarantine item: %s", exc)
            return False

    def _next_index(self, kb_id: int) -> int:
        items = self.list_items(kb_id)
        return items.total

    def _add(self, subj: str, pred: str, obj: str, is_uri: bool) -> None:
        from ontology_triple_cleaner import RawTriple

        t = RawTriple(
            subject=subj,
            predicate=pred,
            object=obj,
            object_is_uri=is_uri,
            graph=quarantine_graph_iri(0),  # will be overridden
        )
        self._store.add_triple(t)

    @staticmethod
    def _triple_to_dict(triple: Any) -> dict[str, Any]:
        if hasattr(triple, "__dict__"):
            return {k: v for k, v in triple.__dict__.items() if not k.startswith("_")}
        return dict(triple) if isinstance(triple, dict) else {"raw": str(triple)}
