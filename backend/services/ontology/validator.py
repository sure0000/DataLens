"""SHACL validation service — validates ABox triples against TBox shapes."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rdflib import Graph

_logger = logging.getLogger(__name__)

try:
    from pyshacl import validate as shacl_validate
except ImportError:
    shacl_validate = None  # type: ignore


def _ontology_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "ontology"


def _load_shapes_graph(shapes: list[str] | None = None) -> Graph:
    """Load SHACL shapes from the shacl/ directory.

    Args:
        shapes: Optional list of shape names (without .ttl extension) to load.
                If None, loads all shapes.
    """
    g = Graph()
    shacl_dir = _ontology_root() / "shacl"
    if not shacl_dir.is_dir():
        return g

    for path in sorted(shacl_dir.glob("*.ttl")):
        if shapes and path.stem not in shapes:
            continue
        g.parse(str(path), format="turtle")
    return g


def _load_tbox_graph() -> Graph:
    """Load the full TBox (tbox/ directory) for SHACL validation context."""
    g = Graph()
    tbox_dir = _ontology_root() / "tbox"
    if tbox_dir.is_dir():
        for path in sorted(tbox_dir.glob("*.ttl")):
            g.parse(str(path), format="turtle")
    return g


def validate(
    data: Graph | str,
    *,
    shapes: list[str] | None = None,
    inference: str = "none",
) -> dict[str, Any]:
    """Validate an ABox data graph or Turtle string against SHACL shapes.

    Args:
        data: An rdflib Graph or Turtle string to validate.
        shapes: Optional list of shape names to apply. None = all shapes.
        inference: SHACL inference mode ("none", "rdfs", "owlrl", "both").

    Returns:
        {
            "conforms": bool,
            "violations": list[str],
            "violation_count": int,
            "report": str (truncated to 8000 chars),
            "skipped": bool,
            "message": str | None
        }
    """
    if shacl_validate is None:
        return {"conforms": True, "skipped": True, "message": "pyshacl not installed", "violations": [], "violation_count": 0, "report": ""}

    shapes_graph = _load_shapes_graph(shapes)
    tbox = _load_tbox_graph()

    data_graph: Graph
    if isinstance(data, str):
        data_graph = Graph()
        data_graph.parse(data=data, format="turtle")
    else:
        data_graph = data

    try:
        conforms, report_graph, report_text = shacl_validate(
            data_graph=data_graph,
            shacl_graph=shapes_graph,
            ont_graph=tbox,
            inference=inference,
            abort_on_first=False,
            allow_infos=True,
            allow_warnings=True,
        )
    except Exception as exc:
        _logger.warning("SHACL validation error: %s", exc)
        return {
            "conforms": False,
            "violations": [str(exc)],
            "violation_count": 1,
            "report": f"SHACL validation raised: {exc}",
            "skipped": False,
            "message": None,
        }

    violations: list[str] = []
    if report_graph:
        for s, p, o in report_graph.triples((None, None, None)):
            if "result" in str(s).lower() or "ValidationResult" in str(o):
                violations.append(str(o)[:500])

    return {
        "conforms": bool(conforms),
        "violations": violations[:50],
        "violation_count": len(violations),
        "report": report_text[:8000] if report_text else "",
        "skipped": False,
        "message": None,
    }


def validate_ttl(ttl: str, shapes: list[str] | None = None) -> dict[str, Any]:
    """Validate a Turtle string against SHACL shapes."""
    return validate(ttl, shapes=shapes)
