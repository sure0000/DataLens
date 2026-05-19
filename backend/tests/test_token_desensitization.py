"""Token 脱敏与凭据安全性测试。"""

from __future__ import annotations

from routers.knowledge_git_sources import _mask_row
from models import KnowledgeGitSource


def test_mask_row_never_exposes_raw_token() -> None:
    """_mask_row 返回的 dict 中 token 字段不应为原始值（应为空或掩码后的值）。"""
    source = KnowledgeGitSource(
        id=1,
        knowledge_base_id=1,
        name="test-repo",
        provider="github",
        owner="acme",
        repo="analytics",
        token="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        branch="main",
    )
    row = _mask_row(source)
    assert "token" in row
    assert row["token"] != "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    # token 应该是掩码后的值（只在查看详情时通过 reveal_secret 获取明文）
    assert len(row["token"]) == 0 or row["token"] != source.token


def test_mask_row_has_token_is_boolean() -> None:
    """has_token 应为布尔值，表示是否配置了 token。"""
    with_token = KnowledgeGitSource(
        id=1, knowledge_base_id=1, name="a", provider="github",
        owner="x", repo="y", token="secret123",
    )
    without_token = KnowledgeGitSource(
        id=2, knowledge_base_id=1, name="b", provider="github",
        owner="x", repo="y", token="",
    )
    assert _mask_row(with_token)["has_token"] is True
    assert _mask_row(without_token)["has_token"] is False


def test_mask_row_excludes_token_from_list_response() -> None:
    """列表接口返回的 token 字段应为空字符串，不能泄露原始 token。"""
    source = KnowledgeGitSource(
        id=1, knowledge_base_id=1, name="repo", provider="github",
        owner="o", repo="r", token="super-secret-token-value",
    )
    row = _mask_row(source)
    assert row["token"] == ""
    assert row["has_token"] is True
