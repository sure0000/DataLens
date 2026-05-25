"""Load TBox on application startup."""
from __future__ import annotations

import logging

from config import get_settings
from services.ontology_store import graph_stats, is_fuseki_enabled, load_tbox, wait_for_fuseki

_logger = logging.getLogger(__name__)


def init_ontology() -> dict:
    settings = get_settings()
    if not settings.ontology_enabled:
        return {"ok": True, "skipped": True, "reason": "ontology_disabled"}

    fuseki_ok = False
    if is_fuseki_enabled():
        fuseki_ok = wait_for_fuseki()
        if not fuseki_ok and not settings.fuseki_fallback_memory:
            return {
                "ok": False,
                "error": (
                    f"Fuseki not reachable at {settings.fuseki_url}. "
                    "Unset FUSEKI_URL and set ONTOLOGY_LOCAL_STORE_ENABLED=true for offline Trig file store, "
                    "or run ./scripts/fuseki.sh start"
                ),
            }

    try:
        count = load_tbox(force=False)
        stats = graph_stats()
        backend = stats.get("storage_backend", "local_file")
        _logger.info(
            "Ontology TBox loaded: %d triples (backend=%s, path=%s)",
            count,
            backend,
            stats.get("local_store_path"),
        )
        return {
            "ok": True,
            "triples": count,
            "backend": backend,
            "fuseki_live": fuseki_ok,
            **{k: stats[k] for k in ("local_store_path", "triple_count") if k in stats},
        }
    except Exception as exc:
        _logger.warning("Ontology TBox load failed: %s", exc)
        return {"ok": False, "error": str(exc)}
