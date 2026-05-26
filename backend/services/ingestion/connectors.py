"""Connector registry — maps import channels to evidence package metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.registry import register_package

# Import route → (asset_kind, connector) for unified evidence registration
CONNECTOR_REGISTRY: dict[str, tuple[str, str]] = {
    "import-file": ("semantic_doc", "file"),
    "api-sources/import": ("semantic_doc", "api"),
    "database-imports": ("physical_schema", "database"),
    "git-sources": ("processing_code", "git"),
    "manual-entry": ("semantic_doc", "manual"),
    "ontology/import": ("ttl_bundle", "ttl"),
}

SOURCE_KIND_MAP: dict[str, tuple[str, str]] = {
    "file": ("semantic_doc", "file"),
    "notion": ("semantic_doc", "api"),
    "confluence": ("semantic_doc", "api"),
    "feishu": ("semantic_doc", "api"),
    "manual": ("semantic_doc", "manual"),
    "ttl": ("ttl_bundle", "ttl"),
    "git_file": ("processing_code", "git"),
}


def resolve_asset_connector(
    *,
    route_key: str | None = None,
    source_kind: str | None = None,
    asset_kind: str | None = None,
    connector: str | None = None,
) -> tuple[str, str]:
    """Resolve asset_kind + connector from route or explicit overrides."""
    if asset_kind and connector:
        return asset_kind, connector
    if route_key and route_key in CONNECTOR_REGISTRY:
        return CONNECTOR_REGISTRY[route_key]
    if source_kind and source_kind in SOURCE_KIND_MAP:
        return SOURCE_KIND_MAP[source_kind]
    return ("semantic_doc", source_kind or "file")


def register_evidence_from_import(
    db: Session,
    kb_id: int,
    *,
    title: str,
    route_key: str | None = None,
    source_kind: str | None = None,
    asset_kind: str | None = None,
    connector: str | None = None,
    source_ref: dict[str, Any] | None = None,
    linked_entry_ids: list[int] | None = None,
    linked_document_id: int | None = None,
    processing_state: str = "registered",
) -> dict[str, Any]:
    """Register an evidence package after any connector import completes."""
    ak, conn = resolve_asset_connector(
        route_key=route_key,
        source_kind=source_kind,
        asset_kind=asset_kind,
        connector=connector,
    )
    row = register_package(
        db,
        kb_id,
        asset_kind=ak,
        connector=conn,
        title=title,
        source_ref=source_ref or {},
        linked_entry_ids=linked_entry_ids or [],
        linked_document_id=linked_document_id,
        processing_state=processing_state,
    )
    from services.ingestion.registry import _row_to_dict

    return _row_to_dict(row)
