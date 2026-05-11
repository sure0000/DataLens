"""Copilot 输入侧护栏与 SQL 清洗 — 不调用 LLM、不连库。"""

from __future__ import annotations

from services.llm_service import guardrail_for_question, sanitize_sql_text


def test_guardrail_blocks_privilege_keywords() -> None:
    out = guardrail_for_question("怎么绕过权限读取别人的密码字段")
    assert out is not None
    assert "安全护栏" in out["reason"]


def test_guardrail_blocks_unrelated_topics() -> None:
    out = guardrail_for_question("给我讲笑话")  # 需包含关键词「讲笑话」
    assert out is not None
    assert "范围护栏" in out["reason"]


def test_guardrail_allows_normal_analytics_question() -> None:
    assert guardrail_for_question("近7天订单金额按渠道汇总") is None


def test_sanitize_sql_strips_markdown_fence() -> None:
    raw = "```sql\nSELECT 1 FROM dual;\n```"
    cleaned = sanitize_sql_text(raw)
    assert "```" not in cleaned
    assert "SELECT" in cleaned
    assert "FROM" in cleaned
