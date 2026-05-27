"""OntologyWriter / 入图（ontology_write）路径回归测试。"""
from __future__ import annotations

import pytest

from config import get_settings
from ontology import NS, concept_slug, kb_graph_iri, metric_iri, table_iri
from services.ontology.writer import (
    DimensionInput,
    LineageInput,
    MetricInput,
    OntologyWriter,
    PhysicalTableInput,
    RelationInput,
    TermInput,
)
from services.ontology_triple_cleaner import RawTriple


@pytest.fixture
def memory_ontology_store(monkeypatch):
    monkeypatch.setenv("FUSEKI_FALLBACK_MEMORY", "true")
    monkeypatch.delenv("FUSEKI_URL", raising=False)
    get_settings.cache_clear()

    from services import ontology_store as osmod

    osmod.reset_triple_store()
    yield
    osmod.reset_triple_store()
    get_settings.cache_clear()


def _make_writer() -> OntologyWriter:
    from services.ontology.quarantine import QuarantineManager
    from services.ontology.validator import validate as shacl_validate
    from services.triple_store import get_triple_store

    store = get_triple_store()
    return OntologyWriter(
        store=store,
        validator=shacl_validate,
        quarantine_manager=QuarantineManager(store),
    )


def _join_triple(kb_id: int, a: int, b: int) -> RawTriple:
    return RawTriple(
        table_iri(a),
        f"{NS}joinableWith",
        table_iri(b),
        True,
        graph=kb_graph_iri(kb_id),
        confidence=90.0,
    )


def test_write_many_raw_triples(memory_ontology_store):
    writer = _make_writer()
    triples = [_join_triple(1, 10, 11), _join_triple(1, 11, 10)]
    result = writer.write_many(1, triples)
    assert isinstance(result, dict)
    assert "written" in result
    assert "stats" in result
    assert result.get("reason") is None


def test_write_many_dict_triples_like_step_cache(memory_ontology_store):
    """流水线 step cache 反序列化后为 dict，入图须能构造 RawTriple。"""
    writer = _make_writer()
    payload = {
        "subject": table_iri(5),
        "predicate": f"{NS}joinableWith",
        "object": table_iri(6),
        "object_is_uri": True,
        "graph": kb_graph_iri(7),
        "confidence": 85.0,
        "source_type": "document",
    }
    result = writer.write_many(7, [payload])
    assert "written" in result
    assert result["stats"]["input"] == 1


def test_write_many_empty(memory_ontology_store):
    writer = _make_writer()
    result = writer.write_many(1, [])
    assert result["written"] == 0
    assert result["stats"]["input"] == 0


def test_write_relation(memory_ontology_store):
    writer = _make_writer()
    rel = RelationInput(
        kb_id=2,
        subject_iri=table_iri(1),
        predicate=f"{NS}joinableWith",
        object_iri=table_iri(2),
        is_uri=True,
        confidence=88.0,
    )
    result = writer.write_relation(rel)
    assert "written" in result


def test_write_term(memory_ontology_store):
    writer = _make_writer()
    term = TermInput(
        domain_id=1,
        name="GMV",
        definition="成交总额",
        related_fields=[],
        confidence=90.0,
        status="approved",
    )
    result = writer.write_term(3, term)
    assert "written" in result


def test_write_metric(memory_ontology_store):
    writer = _make_writer()
    metric = MetricInput(
        domain_id=1,
        name="日活",
        formula="count(distinct user_id)",
        bound_table_ids=[42],
        confidence=90.0,
        status="approved",
    )
    result = writer.write_metric(4, metric)
    assert "written" in result
    assert metric_iri(1, concept_slug("日活", "metric")).startswith("https://")


def test_write_dimension(memory_ontology_store):
    writer = _make_writer()
    dim = DimensionInput(domain_id=1, name="地区", dim_type="geo", confidence=90.0)
    result = writer.write_dimension(5, dim)
    assert "written" in result


def test_write_lineage(memory_ontology_store):
    writer = _make_writer()
    lin = LineageInput(
        kb_id=6,
        source_table_id=1,
        target_table_id=2,
        layer="DWD",
        confidence=90.0,
    )
    result = writer.write_lineage(lin)
    assert "written" in result


def test_write_physical_table(memory_ontology_store):
    writer = _make_writer()
    pt = PhysicalTableInput(
        table_id=99,
        datasource_id=1,
        table_name="orders",
        row_count=1000,
    )
    result = writer.write_physical_table(8, pt)
    assert "written" in result


def test_ontology_write_step_contract(memory_ontology_store):
    """与 orchestrator 入图步相同：write_many → steps.ontology_write 结构。"""
    writer = _make_writer()
    triples = [_join_triple(9, 1, 2)]
    try:
        write_result = writer.write_many(9, triples)
        step = {"status": "done", "total": len(triples), **write_result}
    except Exception as exc:
        step = {"status": "failed", "total": len(triples), "reason": str(exc)}

    assert step["status"] == "done", step.get("reason")
    assert step["total"] == 1
    assert "written" in step
    assert "stats" in step
