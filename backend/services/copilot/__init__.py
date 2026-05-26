"""Copilot query engine — ontology-driven routing and context assembly (Phase 4)."""

from services.copilot.pipeline import CopilotPipeline
from services.copilot.router import OntologyRouter
from services.copilot.context import ContextAssembler

__all__ = ["CopilotPipeline", "OntologyRouter", "ContextAssembler"]
