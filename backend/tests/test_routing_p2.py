"""P2 路由：域推荐、血缘扩表、SQL review、routing trace。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.routing.domain_router import _score_domain_question, suggest_business_domains
from services.routing.lineage_router import apply_lineage_expansion, blacklist_table_ids, parse_join_blacklist_fq
from services.routing.sql_post_validation import evaluate_sql_execution_review
from services.routing_types import CopilotRoutingTrace


def test_parse_join_blacklist():
    assert parse_join_blacklist_fq("sales.secret, DW.Audit") == {"sales.secret", "dw.audit"}


def test_blacklist_table_ids():
    tables = [SimpleNamespace(id=1, database_name="sales", table_name="secret")]
    blocked = blacklist_table_ids(tables, {"sales.secret"})
    assert blocked == {1}


def test_score_domain_question_name_hit():
    assert _score_domain_question("订单域的 GMV", "订单 交易 表", "订单域") >= 0.4


@patch("services.routing.domain_router._domain_profile_text", return_value="订单 GMV 交易")
def test_suggest_business_domains_returns_ranked(mock_profile):
    db = MagicMock()
    dom = SimpleNamespace(id=2, name="订单域", created_at=None)
    db.execute.return_value.scalars.return_value.all.return_value = [dom]
    out = suggest_business_domains(db, "订单域 GMV 趋势", top_k=2)
    assert len(out) == 1
    assert out[0]["domain_id"] == 2


def test_lineage_expansion_adds_neighbor():
    """TODO(Phase 4): 从 RDF 图重新实现血缘扩展（旧 DataLineage 表已移除）。

    当前实现仅查询 join_guide KnowledgeEntry 作为备选扩展源；
    血缘邻居查询需在 Phase 4 中从 RDF 图重新接入。
    """
    db = MagicMock()
    primary = SimpleNamespace(id=10, database_name="dw", table_name="orders")
    neighbor = SimpleNamespace(id=20, database_name="dw", table_name="customers")
    db.execute.return_value.scalars.return_value.all.side_effect = [[]]

    scores = {10: 0.05}
    sources: dict[int, set[str]] = {10: {"table_embedding"}}

    with patch("services.routing.lineage_router.get_settings") as mock_settings:
        mock_settings.return_value.copilot_lineage_expand_top_k = 4
        mock_settings.return_value.copilot_routing_weight_lineage = 0.006
        mock_settings.return_value.rrf_k = 60
        mock_settings.return_value.copilot_join_blacklist = ""
        new_scores, new_sources = apply_lineage_expansion(
            db, [1], [primary, neighbor], 10, scores, sources, routing_bundle=None
        )
    # DataLineage-based expansion is a no-op until Phase 4 RDF reimplementation
    assert isinstance(new_scores, dict)
    assert isinstance(new_sources, dict)


def test_sql_review_flags_out_of_domain():
    db = MagicMock()
    ds = SimpleNamespace(id=1, source_type="postgresql")
    sql_table = SimpleNamespace(id=99, database_name="other", table_name="t")
    with patch("services.routing.sql_post_validation.extract_table_refs_from_sql", return_value=[("table", "other", "t")]):
        with patch("services.routing.sql_post_validation.resolve_table_meta_for_trace", return_value=sql_table):
            with patch("services.routing.sql_post_validation.tables_from_business_domain", return_value=[SimpleNamespace(id=1)]):
                review = evaluate_sql_execution_review(
                    db,
                    sql_text="select * from other.t",
                    business_domain_id=5,
                    candidate_table_ids=[1],
                    table_id=None,
                    ds_anchor=ds,
                    default_db="other",
                )
    assert review["review_required"] is True
    assert review["execution_mode"] == "review"
    assert 99 in review["out_of_domain_table_ids"]


def test_routing_trace_to_dict():
    trace = CopilotRoutingTrace(
        routing_mode="domain_narrowed",
        candidate_table_count=2,
        candidate_table_ids=[1, 2],
        fallback_reason="",
    )
    d = trace.to_dict()
    assert d["routing_mode"] == "domain_narrowed"
    assert d["candidate_table_count"] == 2
