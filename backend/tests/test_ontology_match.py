"""本体匹配模块单元测试。"""
from unittest.mock import MagicMock, patch

from services.copilot.ontology_match import run_ontology_match


def test_ontology_match_no_kb_ids():
    db = MagicMock()
    with patch("services.copilot.ontology_match._resolve_kb_ids", return_value=[]):
        result = run_ontology_match(db, "GMV 是多少", business_domain_id=1)
    assert result.matched is False
    assert "未绑定业务域" in result.summary or "知识库" in result.summary


def test_ontology_match_disabled():
    db = MagicMock()
    with patch("services.copilot.ontology_match.get_settings") as gs:
        gs.return_value.ontology_enabled = False
        result = run_ontology_match(db, "hello", None)
    assert result.skipped is True
