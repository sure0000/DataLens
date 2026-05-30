"""Unit tests for code_patterns rule extractors."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.extraction.code_patterns.router import extract_joins_from_entry, extract_lineage_from_entry
from services.extraction.code_patterns.sql import extract_sql_joins, extract_sql_lineage

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "codebases"


class _Entry:
    def __init__(self, ref: str, body: str):
        self.title = ref.rsplit("/", 1)[-1]
        self.body = body
        self.source_meta = {"ref": ref, "kind": "git_file"}


def _load(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")


def test_pure_sql_lineage_and_joins():
    body = _load("pure_sql/orders_join.sql")
    lineage = extract_sql_lineage(body)
    joins = extract_sql_joins(body)
    assert len(lineage) >= 1
    assert len(joins) >= 1
    assert any(j.left_table == "orders" or j.right_table == "orders" for j in joins)


def test_python_etl_pandas_merge_and_lineage():
    body = _load("python_etl/load_orders.py")
    entry = _Entry("etl/load_orders.py", body)
    lineage, _ = extract_lineage_from_entry(entry)
    joins, hits = extract_joins_from_entry(entry)
    assert len(joins) >= 1
    assert hits.pandas_merge >= 1 or hits.sql >= 1
    assert len(lineage) >= 1 or hits.pandas_read_sql >= 1


def test_python_app_no_table_relations():
    body = _load("python_app/main.py")
    entry = _Entry("app/main.py", body)
    lineage, _ = extract_lineage_from_entry(entry)
    joins, _ = extract_joins_from_entry(entry)
    assert lineage == []
    assert joins == []


def test_dbt_yaml_lineage():
    body = _load("dbt_mini/models/orders.yml")
    entry = _Entry("models/orders.yml", body)
    lineage, hits = extract_lineage_from_entry(entry)
    assert len(lineage) >= 1
    assert hits.dbt_ref >= 1


def test_java_mybatis_join():
    body = _load("java_mybatis/OrderMapper.java")
    entry = _Entry("mapper/OrderMapper.java", body)
    joins, hits = extract_joins_from_entry(entry)
    assert len(joins) >= 1
    assert hits.embedded_sql >= 1


def test_python_domain_enum_and_dataclass():
    from services.extraction.code_patterns.python_domain import extract_python_domain_terms
    from services.extraction.domain_term_extractor import extract_domain_term_triples

    body = _load("python_domain/domain.py")
    entry = _Entry("src/models/domain.py", body)
    terms, _ = extract_python_domain_terms(body)
    assert len(terms) >= 2
    assert any(t.code_name == "CustomerType" and t.term_type == "enum" for t in terms)
    assert any(t.code_name == "Customer" and t.term_type == "entity" for t in terms)

    triples = extract_domain_term_triples(kb_id=1, entries=[entry], domain_id=1)
    assert len(triples) >= 6
    prefs = [t.object for t in triples if t.predicate.endswith("prefLabel")]
    assert "客户类型" in prefs
    assert "用电客户实体" in prefs


def test_git_entry_sort_priority():
    from services.extraction.orchestrator import _git_ext_priority

    assert _git_ext_priority("models/orders.sql") < _git_ext_priority("app/main.py")
    assert _git_ext_priority("app/main.py") < _git_ext_priority("README.md")


@pytest.mark.asyncio
async def test_lineage_extractor_regex_without_llm():
    from services.extraction.lineage_extractor import extract_lineage_triples

    body = _load("pure_sql/orders_join.sql")
    entry = _Entry("models/orders.sql", body)

    async def _no_llm(*_a, **_k):
        raise AssertionError("LLM should not be called when regex succeeds")

    triples = await extract_lineage_triples(
        kb_id=1,
        entries=[entry],
        llm_client=None,
        model_name="test",
        call_llm_json=_no_llm,
        load_prompt=lambda _n: "",
        extraction_config={"enable_regex_extractors": True, "enable_llm_fallback": False},
    )
    assert len(triples) >= 3


@pytest.mark.asyncio
async def test_join_extractor_regex_without_llm():
    from services.extraction.join_extractor import extract_join_triples

    body = _load("pure_sql/orders_join.sql")
    entry = _Entry("models/orders.sql", body)

    async def _no_llm(*_a, **_k):
        raise AssertionError("LLM should not be called when regex succeeds")

    triples = await extract_join_triples(
        kb_id=1,
        entries=[entry],
        llm_client=None,
        model_name="test",
        call_llm_json=_no_llm,
        load_prompt=lambda _n: "",
        extraction_config={"enable_regex_extractors": True, "enable_llm_fallback": False},
    )
    assert len(triples) >= 5


def test_git_diagnostics_to_dict():
    from services.extraction.code_patterns.diagnostics import GitDiagnostics

    d = GitDiagnostics(total_entries=10, processed_limit=10)
    d.record_entry(_Entry("a.sql", "x" * 60), "x" * 60)
    out = d.to_dict()
    assert out["total_entries"] == 10
    assert out["eligible_body_ge_min"] == 1
    assert ".sql" in out["by_ext"]


def test_humanize_no_triples_mentions_diagnostics():
    from services.extraction.pipeline_status import humanize_reason

    msg = humanize_reason("no_triples")
    assert "JOIN" in msg or "join" in msg.lower() or "表间" in msg
    assert "_git_diagnostics" in msg
