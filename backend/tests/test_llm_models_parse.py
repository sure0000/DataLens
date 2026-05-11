"""模型引用解析 — 与 HTTP/数据库无关的纯函数路径。"""

from __future__ import annotations

import pytest

from services.llm_models import parse_model_ref


def test_parse_model_ref_ok() -> None:
    assert parse_model_ref("deepseek:deepseek-chat") == ("deepseek", "deepseek-chat")
    assert parse_model_ref("openai:gpt-4o-mini") == ("openai", "gpt-4o-mini")


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "no-colon",
        ":only-right",
        "only-left:",
        "bad:provider:model",
        "azure:gpt-4",
    ],
)
def test_parse_model_ref_invalid(ref: str) -> None:
    with pytest.raises(ValueError):
        parse_model_ref(ref)
