"""DataLens OWL ontology namespace and IRI helpers."""
from __future__ import annotations

import re
from urllib.parse import quote

NS = "https://datalens.local/ontology/"
DATA_NS = "https://datalens.local/data/"
GRAPH_NS = "https://datalens.local/graph/"
ENTERPRISE_GRAPH = f"{GRAPH_NS}enterprise"
INFERRED_GRAPH_PREFIX = f"{GRAPH_NS}inferred/"


def ontology_iri(local: str) -> str:
    return f"{NS}{local.lstrip(':')}"


def table_iri(table_id: int) -> str:
    return f"{DATA_NS}table/{table_id}"


def column_iri(table_id: int, column_name: str) -> str:
    safe = quote(column_name.strip(), safe="")
    return f"{DATA_NS}table/{table_id}/column/{safe}"


def legacy_table_iri(table_id: int) -> str:
    """Historical bug wrote tables under ontology/data/ instead of data/."""
    return f"{NS}data/table/{table_id}"


def legacy_column_iri(table_id: int, column_name: str) -> str:
    safe = quote(column_name.strip(), safe="")
    return f"{NS}data/table/{table_id}/column/{safe}"


def term_iri(domain_id: int, slug: str) -> str:
    return f"{GRAPH_NS}domain/{domain_id}/term/{slug}"


def metric_iri(domain_id: int, slug: str) -> str:
    return f"{GRAPH_NS}domain/{domain_id}/metric/{slug}"


def concept_iri(slug: str) -> str:
    return f"{DATA_NS}concept/{slug}"


def kb_graph_iri(kb_id: int) -> str:
    return f"{GRAPH_NS}kb/{kb_id}"


def domain_graph_iri(domain_id: int) -> str:
    return f"{GRAPH_NS}domain/{domain_id}"


def quarantine_graph_iri(kb_id: int) -> str:
    return f"{GRAPH_NS}quarantine/{kb_id}"


def chunk_iri(chunk_id: int) -> str:
    return f"{DATA_NS}chunk/{chunk_id}"


def concept_slug(name: str, prefix: str = "term") -> str:
    n = re.sub(r"\s+", "_", (name or "").strip().lower())
    n = re.sub(r"[^\w\u4e00-\u9fff._-]", "", n)
    return f"{prefix}.{n}" if n else ""


def dimension_iri(domain_id: int, slug: str) -> str:
    return f"{GRAPH_NS}domain/{domain_id}/dimension/{slug}"


def rule_iri(domain_id: int, slug: str) -> str:
    return f"{GRAPH_NS}domain/{domain_id}/rule/{slug}"


def view_iri(view_id: int) -> str:
    return f"{DATA_NS}view/{view_id}"


def datasource_iri(ds_id: int) -> str:
    return f"{DATA_NS}datasource/{ds_id}"


def document_iri(doc_id: int) -> str:
    return f"{DATA_NS}document/{doc_id}"


def domain_iri(domain_id: int) -> str:
    return f"{DATA_NS}domain/{domain_id}"


def organization_iri(org_slug: str) -> str:
    return f"{DATA_NS}organization/{org_slug}"


def team_iri(team_slug: str) -> str:
    return f"{DATA_NS}team/{team_slug}"


def platform_id_from_table_iri(iri: str) -> int | None:
    m = re.match(rf"^{re.escape(DATA_NS)}table/(\d+)$", iri or "")
    return int(m.group(1)) if m else None
