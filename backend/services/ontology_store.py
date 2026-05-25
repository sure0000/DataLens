"""Ontology triple store: Fuseki (local or Docker) with optional in-memory fallback."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from rdflib import Dataset, Graph, URIRef
from rdflib.namespace import XSD

from config import get_settings
from ontology import NS

_logger = logging.getLogger(__name__)

_local_dataset: Dataset | None = None
_tbox_loaded = False
_fuseki_live: bool | None = None
# rdflib SPARQL parser + pyparsing are not thread-safe under concurrent uvicorn workers
_sparql_lock = threading.Lock()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _local_store_path() -> Path:
    settings = get_settings()
    raw = (settings.ontology_local_store_path or ".run/ontology-store/datalens.trig").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = _project_root() / path
    return path


def _get_local_dataset() -> Dataset:
    global _local_dataset
    if _local_dataset is not None:
        return _local_dataset

    ds = Dataset()
    store_path = _local_store_path()
    if store_path.is_file():
        try:
            ds.parse(str(store_path), format="trig")
            _logger.info("Loaded local ontology store: %s (%d triples)", store_path, len(ds))
        except Exception as exc:
            _logger.warning("Failed to load local ontology store %s: %s", store_path, exc)
    _local_dataset = ds
    return ds


def get_named_graph(graph_iri: str) -> Graph:
    """Return one named graph from the local dataset (creates empty graph if missing)."""
    ds = _get_local_dataset()
    return ds.graph(URIRef(graph_iri))


def _persist_local_store() -> None:
    if _local_dataset is None:
        return
    settings = get_settings()
    if not settings.ontology_local_store_enabled:
        return
    path = _local_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _local_dataset.serialize(destination=str(path), format="trig")
    _logger.debug("Persisted local ontology store: %s", path)


def storage_backend() -> str:
    if use_fuseki_backend():
        return "fuseki"
    if get_settings().ontology_local_store_enabled:
        return "local_file"
    return "memory"


def is_fuseki_enabled() -> bool:
    return bool((get_settings().fuseki_url or "").strip())


def use_fuseki_backend() -> bool:
    global _fuseki_live
    if not is_fuseki_enabled():
        return False
    if _fuseki_live is None:
        _fuseki_live = probe_fuseki()
    return bool(_fuseki_live)


def probe_fuseki(timeout: float = 3.0) -> bool:
    global _fuseki_live
    settings = get_settings()
    base = (settings.fuseki_url or "").rstrip("/")
    if not base:
        _fuseki_live = False
        return False
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base}/$/ping")
            if resp.status_code != 200:
                raise RuntimeError(f"ping status {resp.status_code}")
            dataset = settings.fuseki_dataset.strip("/")
            q = client.post(
                f"{base}/{dataset}/query",
                data={"query": "ASK { ?s ?p ?o }"},
                headers={"Accept": "application/sparql-results+json"},
            )
            q.raise_for_status()
        _fuseki_live = True
        return True
    except Exception as exc:
        _fuseki_live = False
        if settings.fuseki_fallback_memory:
            _logger.warning(
                "Fuseki unreachable at %s (%s); using in-memory RDF (not persisted). "
                "Run ./scripts/fuseki.sh start or set FUSEKI_URL.",
                base,
                exc,
            )
        else:
            _logger.error(
                "Fuseki unreachable at %s (%s). RDF writes will fail until Fuseki is up.",
                base,
                exc,
            )
        return False


def wait_for_fuseki(max_seconds: int | None = None) -> bool:
    if not is_fuseki_enabled():
        return False
    import time

    settings = get_settings()
    limit = max_seconds if max_seconds is not None else settings.fuseki_wait_seconds
    if limit <= 0:
        return probe_fuseki()
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if probe_fuseki(timeout=2.0):
            return True
        time.sleep(1.5)
    return probe_fuseki(timeout=2.0)


def _sparql_update(query: str) -> None:
    settings = get_settings()
    base = (settings.fuseki_url or "").rstrip("/")
    dataset = settings.fuseki_dataset.strip("/")
    update_url = f"{base}/{dataset}/update"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            update_url,
            content=query,
            headers={"Content-Type": "application/sparql-update"},
        )
        resp.raise_for_status()


def sparql_query(query: str) -> list[dict[str, Any]]:
    if use_fuseki_backend():
        settings = get_settings()
        base = (settings.fuseki_url or "").rstrip("/")
        dataset = settings.fuseki_dataset.strip("/")
        query_url = f"{base}/{dataset}/query"
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                query_url,
                data=urlencode({"query": query}),
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            data = resp.json()
        out: list[dict[str, Any]] = []
        for row in data.get("results", {}).get("bindings", []):
            parsed: dict[str, Any] = {}
            for k, v in row.items():
                parsed[k] = v.get("value")
            out.append(parsed)
        return out

    with _sparql_lock:
        g = _get_local_dataset()
        qres = g.query(query)
        out: list[dict[str, Any]] = []
        for row in qres:
            if hasattr(row, "asdict"):
                out.append({str(k): str(v) for k, v in row.asdict().items()})
            else:
                out.append({"result": str(row)})
        return out


def _ensure_writable_backend() -> None:
    if use_fuseki_backend():
        return
    settings = get_settings()
    if settings.ontology_local_store_enabled or settings.fuseki_fallback_memory:
        return
    raise RuntimeError(
        "Fuseki 未就绪且未启用本地/内存回退。"
        "请运行 ./scripts/fuseki.sh start 或设置 FUSEKI_FALLBACK_MEMORY=true"
    )


def insert_graph(graph_iri: str, triples_ttl: str) -> None:
    if not triples_ttl.strip():
        return

    if use_fuseki_backend():
        tmp = Graph()
        tmp.parse(data=triples_ttl, format="turtle")
        if len(tmp) == 0:
            return
        nt = tmp.serialize(format="nt")
        lines = [ln.strip() for ln in nt.splitlines() if ln.strip() and not ln.startswith("#")]
        if not lines:
            return
        body = " .\n".join(lines) + " ."
        _sparql_update(f"INSERT DATA {{ GRAPH <{graph_iri}> {{ {body} }} }}")
        return

    _ensure_writable_backend()
    ds = _get_local_dataset()
    target = ds.graph(URIRef(graph_iri))
    before = len(target)
    target.parse(data=triples_ttl, format="turtle")
    if len(target) > before:
        _persist_local_store()


def delete_graph(graph_iri: str) -> None:
    if use_fuseki_backend():
        _sparql_update(f"CLEAR GRAPH <{graph_iri}>")
        return

    _ensure_writable_backend()
    ds = _get_local_dataset()
    ds.remove_graph(URIRef(graph_iri))
    if get_settings().ontology_local_store_enabled:
        _persist_local_store()


def export_graph_ttl(graph_iri: str | None = None) -> str:
    if use_fuseki_backend() and graph_iri:
        rows = sparql_query(
            f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
        )
        if rows:
            g = Graph()
            for row in rows:
                pass  # CONSTRUCT via JSON not fully wired; fall through to local
    ds = _get_local_dataset()
    if graph_iri:
        g = ds.graph(URIRef(graph_iri))
        return g.serialize(format="turtle")
    return ds.serialize(format="trig")


def add_triple(
    graph_iri: str,
    subject: str,
    predicate: str,
    obj: str | float | bool,
    *,
    obj_is_uri: bool = False,
    lang: str | None = None,
) -> None:
    ttl_lines: list[str] = []
    if obj_is_uri:
        ttl_lines.append(f"<{subject}> <{predicate}> <{obj}> .")
    elif lang:
        escaped = str(obj).replace("\\", "\\\\").replace('"', '\\"')
        ttl_lines.append(f'<{subject}> <{predicate}> "{escaped}"@{lang} .')
    elif isinstance(obj, bool):
        ttl_lines.append(f'<{subject}> <{predicate}> {"true" if obj else "false"}^^<{XSD.boolean}> .')
    elif isinstance(obj, (int, float)):
        ttl_lines.append(f'<{subject}> <{predicate}> "{obj}"^^<{XSD.decimal}> .')
    else:
        escaped = str(obj).replace("\\", "\\\\").replace('"', '\\"')
        ttl_lines.append(f'<{subject}> <{predicate}> "{escaped}" .')
    insert_graph(graph_iri, "\n".join(ttl_lines))


def load_tbox(force: bool = False) -> int:
    global _tbox_loaded, _local_dataset
    if _tbox_loaded and not force:
        return 0

    if force:
        _local_dataset = None
        _tbox_loaded = False

    base = Path(__file__).resolve().parent.parent / "ontology"
    files = ["core.ttl", "physical.ttl", "business.ttl", "lineage.ttl", "provenance.ttl"]
    count = 0
    tbox_graph = get_settings().ontology_tbox_graph
    tbox_uri = URIRef(tbox_graph)

    if use_fuseki_backend():
        g = Graph()
        for name in files:
            path = base / name
            if path.exists():
                before = len(g)
                g.parse(str(path), format="turtle")
                count += len(g) - before
        ttl = g.serialize(format="turtle")
        try:
            delete_graph(tbox_graph)
            insert_graph(tbox_graph, ttl)
        except Exception as exc:
            _logger.warning("Fuseki TBox load skipped: %s", exc)
    else:
        ds = _get_local_dataset()
        tg = ds.graph(tbox_uri)
        for name in files:
            path = base / name
            if path.exists():
                before = len(tg)
                tg.parse(str(path), format="turtle")
                count += len(tg) - before
        _persist_local_store()

    _tbox_loaded = True
    return count


def graph_stats() -> dict[str, Any]:
    settings = get_settings()
    backend = storage_backend()
    path = _local_store_path()
    triple_count: int | None = None

    if use_fuseki_backend():
        try:
            rows = sparql_query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
            triple_count = int(rows[0]["c"]) if rows else 0
        except Exception as exc:
            _logger.warning("Fuseki graph_stats count failed: %s", exc)
    elif backend == "local_file" or settings.fuseki_fallback_memory:
        triple_count = len(_get_local_dataset())

    return {
        "triple_count": triple_count,
        "fuseki_enabled": is_fuseki_enabled(),
        "fuseki_live": use_fuseki_backend(),
        "storage_backend": backend,
        "local_store_path": str(path) if settings.ontology_local_store_enabled else None,
        "local_store_exists": path.is_file() if settings.ontology_local_store_enabled else False,
        "fuseki_url": (settings.fuseki_url or "").strip() or None,
        "fuseki_dataset": settings.fuseki_dataset,
        "tbox_loaded": _tbox_loaded,
    }


# Backward compat for tests / imports
def _get_memory_store() -> Graph:
    return _get_local_dataset()
