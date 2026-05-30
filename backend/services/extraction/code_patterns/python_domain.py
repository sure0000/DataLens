"""Extract business domain terms from Python Enum and dataclass definitions."""

from __future__ import annotations

import ast
import re

from services.extraction.code_patterns.ir import DomainTerm, ExtractionHits

_RE_SPLIT_LABEL = re.compile(r"\s*[-–—|]\s*")


def _class_bases_enum(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Enum":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Enum":
            return True
    return False


def _class_is_dataclass(node: ast.ClassDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return True
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "dataclass":
            return True
    return False


def _label_from_docstring(doc: str | None, fallback: str) -> tuple[str, str]:
    text = (doc or "").strip()
    if not text:
        return fallback, fallback
    first_line = text.splitlines()[0].strip()
    parts = _RE_SPLIT_LABEL.split(first_line, maxsplit=1)
    label = parts[0].strip() or fallback
    return label, text


def _field_names(node: ast.ClassDef) -> list[str]:
    names: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names.append(item.target.id)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
    return names


def extract_python_domain_terms(body: str) -> tuple[list[DomainTerm], ExtractionHits]:
    """Parse Python source and return domain terms from Enum / dataclass classes."""
    hits = ExtractionHits()
    terms: list[DomainTerm] = []
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return terms, hits

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        doc = ast.get_docstring(node)
        if _class_bases_enum(node):
            label, definition = _label_from_docstring(doc, node.name)
            terms.append(
                DomainTerm(
                    name=label,
                    definition=definition,
                    code_name=node.name,
                    term_type="enum",
                    related_fields=_field_names(node),
                    provenance="ast:python_enum",
                )
            )
        elif _class_is_dataclass(node):
            label, definition = _label_from_docstring(doc, node.name)
            terms.append(
                DomainTerm(
                    name=label,
                    definition=definition,
                    code_name=node.name,
                    term_type="entity",
                    related_fields=_field_names(node),
                    provenance="ast:python_dataclass",
                )
            )

    return terms, hits
