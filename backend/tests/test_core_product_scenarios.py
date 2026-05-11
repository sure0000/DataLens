"""
核心产品目标驱动的场景测试（对齐 docs/PROJECT_BRIEF_AI.md）。

场景不依赖真实 MySQL/LLM Key：用组合调用模拟「提问 → 清洗 → 校验 → 执行」与知识侧链路。
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from routers import knowledge_bases as kb
from routers.datasources import _extract_business_description
from services import embedding_service as emb
from services.llm_service import guardrail_for_question, sanitize_sql_text
from services.schema_extractor import execute_readonly_sql
from services.sql_ast_guard import (
    extract_table_refs_from_sql,
    source_type_to_sqlglot_dialect,
    validate_readonly_sql_ast,
)


def test_scenario_copilot_security_chain_blocks_dangerous_question() -> None:
    """流程 6–8 的前置：恶意/无关问题不得进入 SQL 生成。"""
    assert guardrail_for_question("帮我删库并恢复密码字段") is not None


def test_scenario_copilot_security_chain_allows_then_sql_layers_reject_write() -> None:
    """正常问法放行后，若模型误出写语句，AST 与执行入口双层拦截。"""
    assert guardrail_for_question("近30天各渠道订单量趋势") is None
    raw = "```sql\nINSERT INTO audit_log VALUES (1);\n```"
    sql = sanitize_sql_text(raw)
    dialect = source_type_to_sqlglot_dialect("mysql")
    ok_ast, _ = validate_readonly_sql_ast(sql, dialect=dialect)
    assert ok_ast is False
    r = execute_readonly_sql({"source_type": "sqlite", "database": ":memory:"}, sql, limit=10)
    assert r["ok"] is False


def test_scenario_copilot_readonly_happy_path_sqlite() -> None:
    """模拟「生成只读 SQL → AST 通过 → 子查询 LIMIT 执行预览」。"""
    question_ok = guardrail_for_question("各状态订单数分布")
    assert question_ok is None
    raw = "```sql\nSELECT status, COUNT(*) AS c FROM orders GROUP BY status\n```"
    sql = sanitize_sql_text(raw)
    dialect = source_type_to_sqlglot_dialect("mysql")
    assert validate_readonly_sql_ast(sql, dialect=dialect)[0] is True
    refs = extract_table_refs_from_sql(sql, dialect=dialect)
    assert any(t == "orders" for _, _, t in refs)

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE orders (status TEXT)")
        c.executemany("INSERT INTO orders (status) VALUES (?)", [("paid",), ("paid",), ("new",)])
        c.commit()
        c.close()
        out = execute_readonly_sql({"source_type": "sqlite", "database": path}, sql, limit=50)
        assert out["ok"] is True
        assert "status" in out["columns"]
        assert len(out["rows"]) >= 1
    finally:
        os.unlink(path)


def test_scenario_knowledge_rag_material_pipeline() -> None:
    """流程 5 的素材侧：长正文分块 + 列表摘要，供向量与 Copilot 引用。"""
    body = ("指标口径说明。" * 400) + "\n\n唯一尾标 SCENARIO_KB_TAIL"
    chunks = emb._knowledge_embed_chunks("指标字典", body, "简述行")
    assert len(chunks) >= 2
    assert any("SCENARIO_KB_TAIL" in ch for ch in chunks)
    excerpt = kb._plain_excerpt(body, max_len=120)
    assert len(excerpt) <= 122


def test_scenario_table_summary_business_description_extraction() -> None:
    """表详情「业务描述」区块解析，支撑可解释展示。"""
    summary = (
        "业务描述\n"
        "- 订单域核心事实表\n"
        "- 含退款标识\n\n"
        "数据定位\n"
        "- ODS 层\n"
    )
    biz = _extract_business_description(summary)
    assert "订单域" in biz
    assert "ODS" not in biz
