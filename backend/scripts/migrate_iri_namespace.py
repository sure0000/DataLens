"""
IRI namespace migration: bridge legacy GRAPH_NS IRIs to new DATA_NS IRIs.

P3: term_iri, metric_iri, dimension_iri, rule_iri move from
    graph://{domain}/term/{slug} → data://{domain}/term/{slug}

This script inserts owl:sameAs triples so queries against old IRIs
resolve to the new ones transparently.

Usage:
    python -m scripts.migrate_iri_namespace --kb-id 1 [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_logger = logging.getLogger(__name__)


def migrate_iri_namespace(
    kb_id: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """For all entities in a KB, add owl:sameAs from old GRAPH_NS IRI to new DATA_NS IRI.

    Args:
        kb_id: Knowledge base ID to migrate.
        dry_run: If True, only report what would change without writing.

    Returns:
        Dict with migration stats.
    """
    from ontology import (
        GRAPH_NS, DATA_NS, kb_graph_iri, domain_graph_iri,
        term_iri, term_iri_legacy,
        metric_iri, metric_iri_legacy,
        dimension_iri, dimension_iri_legacy,
        rule_iri, rule_iri_legacy,
    )

    graph = kb_graph_iri(kb_id)

    # Pattern: graph://.../domain/{id}/term/{slug} or metric, dimension, rule
    legacy_pattern = re.compile(
        r"^" + re.escape(GRAPH_NS) + r"domain/(\d+)/(term|metric|dimension|rule)/(.+)$"
    )

    bridge_map = {
        "term": (term_iri_legacy, term_iri),
        "metric": (metric_iri_legacy, metric_iri),
        "dimension": (dimension_iri_legacy, dimension_iri),
        "rule": (rule_iri_legacy, rule_iri),
    }

    from services.ontology_store import get_named_graph, insert_graph

    try:
        prod_g = get_named_graph(graph)
    except Exception as exc:
        _logger.error("Failed to load graph %s: %s", graph, exc)
        return {"ok": False, "error": str(exc)}

    same_as_triples: list[str] = []
    rewrites: list[dict[str, str]] = []

    for s, p, o in prod_g:
        s_str = str(s)
        m = legacy_pattern.match(s_str)
        if m:
            domain_id = int(m.group(1))
            entity_type = m.group(2)
            slug = m.group(3)

            _, new_iri_fn = bridge_map[entity_type]
            new_iri = new_iri_fn(domain_id, slug)

            if new_iri != s_str:
                same_as_triples.append(f'<{s_str}> <http://www.w3.org/2002/07/owl#sameAs> <{new_iri}> .')
                same_as_triples.append(f'<{new_iri}> <http://www.w3.org/2002/07/owl#sameAs> <{s_str}> .')
                rewrites.append({"old": s_str, "new": new_iri, "type": entity_type})

        # Also check object positions
        o_str = str(o)
        m = legacy_pattern.match(o_str)
        if m:
            domain_id = int(m.group(1))
            entity_type = m.group(2)
            slug = m.group(3)

            _, new_iri_fn = bridge_map[entity_type]
            new_iri = new_iri_fn(domain_id, slug)

            if new_iri != o_str and not any(r["old"] == o_str for r in rewrites):
                same_as_triples.append(f'<{o_str}> <http://www.w3.org/2002/07/owl#sameAs> <{new_iri}> .')
                same_as_triples.append(f'<{new_iri}> <http://www.w3.org/2002/07/owl#sameAs> <{o_str}> .')
                rewrites.append({"old": o_str, "new": new_iri, "type": entity_type})

    _logger.info("Found %d entities to bridge (dry_run=%s)", len(rewrites), dry_run)

    if dry_run:
        for r in rewrites:
            _logger.info("  %s → %s (%s)", r["old"], r["new"], r["type"])
        return {"ok": True, "dry_run": True, "rewrites": len(rewrites), "entities": rewrites}

    if same_as_triples:
        ttl = "\n".join(same_as_triples) + "\n"
        try:
            insert_graph(graph, ttl)
            _logger.info("Inserted %d owl:sameAs bridge triples into %s", len(same_as_triples), graph)
        except Exception as exc:
            _logger.error("Failed to insert bridge triples: %s", exc)
            return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "kb_id": kb_id,
        "rewrites": len(rewrites),
        "same_as_triples": len(same_as_triples),
        "entities": [r["old"] for r in rewrites[:10]],  # first 10 for verification
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate IRI namespace from GRAPH_NS to DATA_NS")
    parser.add_argument("--kb-id", type=int, required=True, help="Knowledge base ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    result = migrate_iri_namespace(args.kb_id, dry_run=args.dry_run)
    _logger.info("Migration result: %s", result)
