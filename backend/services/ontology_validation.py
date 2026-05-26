"""SHACL validation for ontology triples."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rdflib import Graph

try:
    from pyshacl import validate as shacl_validate
except ImportError:
    shacl_validate = None  # type: ignore


def _load_shapes_graph() -> Graph:
    g = Graph()
    base = Path(__file__).resolve().parent.parent / "ontology" / "shacl"
    for path in sorted(base.glob("*.ttl")):
        g.parse(str(path), format="turtle")
    return g


def _load_tbox_graph() -> Graph:
    """Load all TBox files (tbox/ directory + legacy root) for SHACL validation."""
    g = Graph()
    base = Path(__file__).resolve().parent.parent / "ontology"
    tbox_dir = base / "tbox"
    if tbox_dir.is_dir():
        for path in sorted(tbox_dir.glob("*.ttl")):
            g.parse(str(path), format="turtle")
    else:
        for name in ["core.ttl", "physical.ttl", "business.ttl", "lineage.ttl", "provenance.ttl"]:
            path = base / name
            if path.exists():
                g.parse(str(path), format="turtle")
    return g


def validate_data_graph(data: Graph, *, inference: str = "none") -> dict[str, Any]:
    """Validate ABox graph against SHACL shapes. Returns report dict."""
    if shacl_validate is None:
        return {"conforms": True, "skipped": True, "message": "pyshacl not installed"}

    shapes = _load_shapes_graph()
    tbox = _load_tbox_graph()

    conforms, report_graph, report_text = shacl_validate(
        data_graph=data,
        shacl_graph=shapes,
        ont_graph=tbox,
        inference=inference,
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    violations = []
    if report_graph:
        for s, p, o in report_graph.triples((None, None, None)):
            if "result" in str(s).lower() or "ValidationResult" in str(o):
                violations.append(str(o))

    return {
        "conforms": bool(conforms),
        "skipped": False,
        "violations": violations[:50],
        "report": report_text[:8000] if report_text else "",
    }


def validate_ttl(ttl: str) -> dict[str, Any]:
    g = Graph()
    g.parse(data=ttl, format="turtle")
    return validate_data_graph(g)
