"""Resolve text refs to PhysicalTable / PhysicalColumn IRIs."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models import TableMeta
from ontology import column_iri, table_iri
from services.semantic_grounding import match_tables_from_grounding

_SHORT_TABLE_NAME_LEN = 6


def _table_ref_variants(table: TableMeta) -> set[str]:
    fq = f"{(table.database_name or '').strip()}.{(table.table_name or '').strip()}".lower()
    tn = (table.table_name or "").strip().lower()
    out: set[str] = set()
    if fq and fq != ".":
        out.add(fq)
    if tn:
        out.add(tn)
    return out


def resolve_table_ref(ref: str, domain_tables: list[TableMeta]) -> tuple[str | None, str, float]:
    """Return (table_iri, link_method, confidence)."""
    grounding = {"table_refs": [ref], "column_refs": []}
    ids = match_tables_from_grounding(
        domain_tables, grounding, already_matched=set(), allowed={t.id for t in domain_tables}
    )
    if len(ids) == 1:
        return table_iri(ids[0]), "exact", 95.0
    if len(ids) > 1:
        return table_iri(ids[0]), "ambiguous", 50.0
    return None, "unresolved", 0.0


def resolve_grounding_to_iris(
    db: Session,
    grounding: dict[str, Any] | None,
    domain_tables: list[TableMeta],
) -> dict[str, Any]:
    """Map grounding dict to linked IRIs."""
    if not grounding or not domain_tables:
        return {"table_iris": [], "column_iris": [], "unresolved": []}

    allowed = {t.id for t in domain_tables}
    table_ids = match_tables_from_grounding(
        domain_tables, grounding, already_matched=set(), allowed=allowed
    )
    table_iris = [table_iri(tid) for tid in table_ids]

    column_iris: list[str] = []
    unresolved: list[str] = []
    id_by_table = {t.id: t for t in domain_tables}

    for raw in grounding.get("column_refs") or []:
        field = str(raw or "").strip()
        if not field:
            continue
        if "." in field:
            table_part, col_part = field.rsplit(".", 1)
            tid = None
            for t in domain_tables:
                variants = _table_ref_variants(t)
                if table_part.lower() in variants or table_part.lower() == (t.table_name or "").lower():
                    tid = t.id
                    break
            if tid is not None:
                column_iris.append(column_iri(tid, col_part))
            else:
                unresolved.append(field)
        else:
            # column name only — attach to matched tables
            attached = False
            for tid in table_ids:
                column_iris.append(column_iri(tid, field))
                attached = True
            if not attached:
                unresolved.append(field)

    for raw in grounding.get("table_refs") or []:
        ref = str(raw or "").strip()
        if not ref:
            continue
        iri, method, _ = resolve_table_ref(ref, domain_tables)
        if iri is None:
            unresolved.append(ref)

    return {
        "table_iris": list(dict.fromkeys(table_iris)),
        "column_iris": list(dict.fromkeys(column_iris)),
        "unresolved": unresolved,
    }


def platform_ids_from_table_iris(iri_list: list[str]) -> list[int]:
    from ontology import platform_id_from_table_iri

    out: list[int] = []
    for iri in iri_list:
        tid = platform_id_from_table_iri(iri)
        if tid is not None:
            out.append(tid)
    return out
