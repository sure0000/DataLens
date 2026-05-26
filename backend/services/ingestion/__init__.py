"""Ingestion layer — evidence packages and events."""

from services.ingestion.connectors import (
    CONNECTOR_REGISTRY,
    register_evidence_from_import,
    resolve_asset_connector,
)
from services.ingestion.evidence import list_evidence_packages
from services.ingestion.registry import list_all_packages, normalize_package, register_package
from services.ingestion.events import emit, subscribe

__all__ = [
    "CONNECTOR_REGISTRY",
    "list_evidence_packages",
    "list_all_packages",
    "register_package",
    "normalize_package",
    "register_evidence_from_import",
    "resolve_asset_connector",
    "emit",
    "subscribe",
]
