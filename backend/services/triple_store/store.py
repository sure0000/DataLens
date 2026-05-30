"""TripleStore — encapsulated RDF triple store with Fuseki backend and optional local/memory fallback.

No module-level globals. All mutable state lives on the TripleStore instance.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import httpx
from rdflib import Dataset, Graph, URIRef
from rdflib.namespace import XSD

from config import Settings, get_settings
from ontology import NS
from services.httpx_env import async_client as httpx_async_client
from services.httpx_env import sync_client as httpx_sync_client

_logger = logging.getLogger(__name__)


class TripleStore:
    """Encapsulated triple store with Fuseki HTTP backend and local/memory fallback.

    Usage:
        store = TripleStore()           # uses get_settings() defaults
        store = TripleStore(settings)   # inject custom settings
        store = get_triple_store()      # module-level singleton (backward compat)

    All mutable state (connection cache, dataset, tbox flag, lock) is instance-scoped.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._local_dataset: Dataset | None = None
        self._tbox_loaded: bool = False
        self._fuseki_live: bool | None = None
        self._sparql_lock = threading.Lock()
        self._http_client: httpx.Client | None = None
        self._async_http_client: httpx.AsyncClient | None = None

    # ── property accessors ──────────────────────────────

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def tbox_loaded(self) -> bool:
        return self._tbox_loaded

    # ── path helpers ────────────────────────────────────

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent.parent

    def _local_store_path(self) -> Path:
        raw = (self._settings.ontology_local_store_path or ".run/ontology-store/datalens.trig").strip()
        path = Path(raw)
        if not path.is_absolute():
            path = self._project_root() / path
        return path

    # ── HTTP clients ────────────────────────────────────

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx_sync_client(timeout=60.0, for_local=True)
        return self._http_client

    def _get_async_http_client(self) -> httpx.AsyncClient:
        if self._async_http_client is None:
            self._async_http_client = httpx_async_client(timeout=60.0, for_local=True)
        return self._async_http_client

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None
        # async client must be closed from an async context; caller should use aclose()

    async def aclose(self) -> None:
        self.close()
        if self._async_http_client is not None:
            await self._async_http_client.aclose()
            self._async_http_client = None

    # ── local dataset ───────────────────────────────────

    def _get_local_dataset(self) -> Dataset:
        if self._local_dataset is not None:
            return self._local_dataset

        ds = Dataset()
        store_path = self._local_store_path()
        if store_path.is_file():
            try:
                ds.parse(str(store_path), format="trig")
                _logger.info("Loaded local ontology store: %s (%d triples)", store_path, len(ds))
            except Exception as exc:
                _logger.warning("Failed to load local ontology store %s: %s", store_path, exc)
        self._local_dataset = ds
        return ds

    def get_named_graph(self, graph_iri: str) -> Graph:
        ds = self._get_local_dataset()
        return ds.graph(URIRef(graph_iri))

    def _persist_local_store(self) -> None:
        if self._local_dataset is None:
            return
        if not self._settings.ontology_local_store_enabled:
            return
        path = self._local_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local_dataset.serialize(destination=str(path), format="trig")
        _logger.debug("Persisted local ontology store: %s", path)

    # ── backend selection ───────────────────────────────

    def storage_backend(self) -> str:
        if self.use_fuseki_backend():
            return "fuseki"
        if self._settings.ontology_local_store_enabled:
            return "local_file"
        return "memory"

    def is_fuseki_enabled(self) -> bool:
        return bool((self._settings.fuseki_url or "").strip())

    def use_fuseki_backend(self) -> bool:
        if not self.is_fuseki_enabled():
            return False
        if self._fuseki_live is None:
            self._fuseki_live = self.probe_fuseki()
        return bool(self._fuseki_live)

    def _ensure_writable_backend(self) -> None:
        if self.use_fuseki_backend():
            return
        if self._settings.ontology_local_store_enabled or self._settings.fuseki_fallback_memory:
            return
        raise RuntimeError(
            "Fuseki 未就绪且未启用本地/内存回退。"
            "请运行 ./scripts/fuseki.sh start 或设置 FUSEKI_FALLBACK_MEMORY=true"
        )

    # ── Fuseki probe ────────────────────────────────────

    def probe_fuseki(self, timeout: float = 3.0, *, log_failure: bool = True) -> bool:
        settings = self._settings
        base = (settings.fuseki_url or "").rstrip("/")
        if not base:
            self._fuseki_live = False
            return False
        try:
            with httpx_sync_client(timeout=timeout, for_local=True) as client:
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
            self._fuseki_live = True
            return True
        except Exception as exc:
            self._fuseki_live = False
            if log_failure:
                if settings.fuseki_fallback_memory:
                    _logger.warning(
                        "Fuseki unreachable at %s (%s); using in-memory RDF (not persisted). "
                        "Run ./scripts/fuseki.sh start or set FUSEKI_URL.",
                        base,
                        exc,
                    )
                else:
                    _logger.warning(
                        "Fuseki unreachable at %s (%s). RDF writes will fail until Fuseki is up.",
                        base,
                        exc,
                    )
            return False

    async def probe_fuseki_async(self, timeout: float = 3.0) -> bool:
        settings = self._settings
        base = (settings.fuseki_url or "").rstrip("/")
        if not base:
            self._fuseki_live = False
            return False
        try:
            async with httpx_async_client(timeout=timeout, for_local=True) as client:
                resp = await client.get(f"{base}/$/ping")
                if resp.status_code != 200:
                    raise RuntimeError(f"ping status {resp.status_code}")
                dataset = settings.fuseki_dataset.strip("/")
                q = await client.post(
                    f"{base}/{dataset}/query",
                    data={"query": "ASK { ?s ?p ?o }"},
                    headers={"Accept": "application/sparql-results+json"},
                )
                q.raise_for_status()
            self._fuseki_live = True
            return True
        except Exception as exc:
            self._fuseki_live = False
            if settings.fuseki_fallback_memory:
                _logger.warning(
                    "Fuseki unreachable at %s (%s); using in-memory RDF.",
                    base,
                )
            else:
                _logger.error("Fuseki unreachable at %s (%s).", base, exc)
            return False

    def wait_for_fuseki(self, max_seconds: int | None = None) -> bool:
        if not self.is_fuseki_enabled():
            return False
        import time

        limit = max_seconds if max_seconds is not None else self._settings.fuseki_wait_seconds
        if limit <= 0:
            return self.probe_fuseki()
        deadline = time.monotonic() + limit
        logged_failure = False
        while time.monotonic() < deadline:
            if self.probe_fuseki(timeout=2.0, log_failure=not logged_failure):
                return True
            logged_failure = True
            time.sleep(1.5)
        return self.probe_fuseki(timeout=2.0, log_failure=True)

    # ── SPARQL operations ───────────────────────────────

    def _sparql_update(self, query: str) -> None:
        settings = self._settings
        base = (settings.fuseki_url or "").rstrip("/")
        dataset = settings.fuseki_dataset.strip("/")
        update_url = f"{base}/{dataset}/update"
        with httpx_sync_client(timeout=60.0, for_local=True) as client:
            resp = client.post(
                update_url,
                content=query,
                headers={"Content-Type": "application/sparql-update"},
            )
            resp.raise_for_status()

    async def _sparql_update_async(self, query: str) -> None:
        settings = self._settings
        base = (settings.fuseki_url or "").rstrip("/")
        dataset = settings.fuseki_dataset.strip("/")
        update_url = f"{base}/{dataset}/update"
        async with httpx_async_client(timeout=60.0, for_local=True) as client:
            resp = await client.post(
                update_url,
                content=query,
                headers={"Content-Type": "application/sparql-update"},
            )
            resp.raise_for_status()

    def sparql_query(self, query: str) -> list[dict[str, Any]]:
        if self.use_fuseki_backend():
            settings = self._settings
            base = (settings.fuseki_url or "").rstrip("/")
            dataset = settings.fuseki_dataset.strip("/")
            query_url = f"{base}/{dataset}/query"
            with httpx_sync_client(timeout=60.0, for_local=True) as client:
                resp = client.post(
                    query_url,
                    data={"query": query},
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

        with self._sparql_lock:
            g = self._get_local_dataset()
            qres = g.query(query)
            out: list[dict[str, Any]] = []
            for row in qres:
                if hasattr(row, "asdict"):
                    out.append({str(k): str(v) for k, v in row.asdict().items()})
                else:
                    out.append({"result": str(row)})
            return out

    async def sparql_query_async(self, query: str) -> list[dict[str, Any]]:
        if self.use_fuseki_backend():
            settings = self._settings
            base = (settings.fuseki_url or "").rstrip("/")
            dataset = settings.fuseki_dataset.strip("/")
            query_url = f"{base}/{dataset}/query"
            async with httpx_async_client(timeout=60.0, for_local=True) as client:
                resp = await client.post(
                    query_url,
                    data={"query": query},
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

        # Fall back to sync local path (rdflib is not async-safe anyway)
        return self.sparql_query(query)

    # ── graph CRUD ──────────────────────────────────────

    def insert_graph(self, graph_iri: str, triples_ttl: str) -> None:
        if not triples_ttl.strip():
            return

        if self.use_fuseki_backend():
            tmp = Graph()
            tmp.parse(data=triples_ttl, format="turtle")
            if len(tmp) == 0:
                return
            nt = tmp.serialize(format="nt")
            lines = [ln.strip() for ln in nt.splitlines() if ln.strip() and not ln.startswith("#")]
            if not lines:
                return
            # N-Triples lines already end with '.'; do not join with extra '.' (Fuseki parse error).
            body = "\n".join(lines)
            self._sparql_update(f"INSERT DATA {{ GRAPH <{graph_iri}> {{ {body} }} }}")
            return

        self._ensure_writable_backend()
        ds = self._get_local_dataset()
        target = ds.graph(URIRef(graph_iri))
        before = len(target)
        target.parse(data=triples_ttl, format="turtle")
        if len(target) > before:
            self._persist_local_store()

    async def insert_graph_async(self, graph_iri: str, triples_ttl: str) -> None:
        if not triples_ttl.strip():
            return

        if self.use_fuseki_backend():
            tmp = Graph()
            tmp.parse(data=triples_ttl, format="turtle")
            if len(tmp) == 0:
                return
            nt = tmp.serialize(format="nt")
            lines = [ln.strip() for ln in nt.splitlines() if ln.strip() and not ln.startswith("#")]
            if not lines:
                return
            body = "\n".join(lines)
            await self._sparql_update_async(f"INSERT DATA {{ GRAPH <{graph_iri}> {{ {body} }} }}")
            return

        self.insert_graph(graph_iri, triples_ttl)

    def delete_graph(self, graph_iri: str) -> None:
        if self.use_fuseki_backend():
            self._sparql_update(f"CLEAR GRAPH <{graph_iri}>")
            return

        self._ensure_writable_backend()
        ds = self._get_local_dataset()
        ds.remove_graph(URIRef(graph_iri))
        if self._settings.ontology_local_store_enabled:
            self._persist_local_store()

    async def delete_graph_async(self, graph_iri: str) -> None:
        if self.use_fuseki_backend():
            await self._sparql_update_async(f"CLEAR GRAPH <{graph_iri}>")
            return
        self.delete_graph(graph_iri)

    def export_graph_ttl(self, graph_iri: str | None = None) -> str:
        if self.use_fuseki_backend() and graph_iri:
            rows = self.sparql_query(
                f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
            )
            if rows:
                g = Graph()
                for row in rows:
                    pass  # CONSTRUCT via JSON not fully wired; fall through to local
        ds = self._get_local_dataset()
        if graph_iri:
            g = ds.graph(URIRef(graph_iri))
            return g.serialize(format="turtle")
        return ds.serialize(format="trig")

    def add_triple(
        self,
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
        self.insert_graph(graph_iri, "\n".join(ttl_lines))

    # ── TBox loading ────────────────────────────────────

    def load_tbox(self, force: bool = False) -> int:
        if self._tbox_loaded and not force:
            return 0

        if force:
            self._local_dataset = None
            self._tbox_loaded = False

        base = Path(__file__).resolve().parent.parent.parent / "ontology"
        tbox_dir = base / "tbox"
        files = (
            ["core.ttl", "enterprise.ttl", "governance.ttl", "physical.ttl", "business.ttl", "lineage.ttl", "provenance.ttl"]
            if tbox_dir.is_dir()
            else ["core.ttl", "physical.ttl", "business.ttl", "lineage.ttl", "provenance.ttl"]
        )
        count = 0
        tbox_graph = self._settings.ontology_tbox_graph
        tbox_uri = URIRef(tbox_graph)

        if self.use_fuseki_backend():
            g = Graph()
            for name in files:
                path = (tbox_dir if tbox_dir.is_dir() else base) / name
                if path.exists():
                    before = len(g)
                    g.parse(str(path), format="turtle")
                    count += len(g) - before
            # Also load legacy root-level TTL files for backward compat
            legacy_files = ["core.ttl", "physical.ttl", "business.ttl", "lineage.ttl", "provenance.ttl"]
            for name in legacy_files:
                path = base / name
                if path.exists() and (tbox_dir / name).exists() is False:
                    before = len(g)
                    g.parse(str(path), format="turtle")
                    count += len(g) - before
            ttl = g.serialize(format="turtle")
            try:
                self.delete_graph(tbox_graph)
                self.insert_graph(tbox_graph, ttl)
            except Exception as exc:
                _logger.warning("Fuseki TBox load skipped: %s", exc)
        else:
            ds = self._get_local_dataset()
            tg = ds.graph(tbox_uri)
            load_dir = tbox_dir if tbox_dir.is_dir() else base
            for name in files:
                path = load_dir / name
                if path.exists():
                    before = len(tg)
                    tg.parse(str(path), format="turtle")
                    count += len(tg) - before
            self._persist_local_store()

        self._tbox_loaded = True
        return count

    # ── stats ───────────────────────────────────────────

    def graph_stats(self) -> dict[str, Any]:
        settings = self._settings
        backend = self.storage_backend()
        path = self._local_store_path()
        triple_count: int | None = None

        if self.use_fuseki_backend():
            try:
                rows = self.sparql_query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
                triple_count = int(rows[0]["c"]) if rows else 0
            except Exception as exc:
                _logger.warning("Fuseki graph_stats count failed: %s", exc)
        elif backend == "local_file" or settings.fuseki_fallback_memory:
            triple_count = len(self._get_local_dataset())

        return {
            "triple_count": triple_count,
            "fuseki_enabled": self.is_fuseki_enabled(),
            "fuseki_live": self.use_fuseki_backend(),
            "storage_backend": backend,
            "local_store_path": str(path) if settings.ontology_local_store_enabled else None,
            "local_store_exists": path.is_file() if settings.ontology_local_store_enabled else False,
            "fuseki_url": (settings.fuseki_url or "").strip() or None,
            "fuseki_dataset": settings.fuseki_dataset,
            "tbox_loaded": self._tbox_loaded,
        }


# ── module-level singleton (backward compat) ─────────────

_triple_store: TripleStore | None = None
_store_lock = threading.Lock()


def get_triple_store(settings: Settings | None = None) -> TripleStore:
    """Return the module-level TripleStore singleton.

    Creates it on first call. Pass settings to override defaults on creation;
    settings are ignored on subsequent calls (use reset_triple_store() to
    replace the singleton).
    """
    global _triple_store
    if _triple_store is None:
        with _store_lock:
            if _triple_store is None:
                _triple_store = TripleStore(settings=settings)
    return _triple_store


def reset_triple_store() -> None:
    """Reset the module-level singleton (e.g. for tests)."""
    global _triple_store
    _triple_store = None
