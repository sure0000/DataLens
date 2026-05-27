"""知识库：摘要、API 行结构、向量分块等单元测试（不连数据库）。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from routers import knowledge_bases as kb
from services import embedding_service as emb


def test_plain_excerpt_truncates_with_ellipsis():
    long = "章节内容 " * 120
    ex = kb._plain_excerpt(long, max_len=80)
    assert len(ex) <= 82
    assert ex.endswith("…")


def test_resolved_summary_explicit_over_body():
    body = "自动摘要应来自正文" * 30
    assert kb._resolved_summary("手写简述", body) == "手写简述"


def test_resolved_summary_falls_back_to_excerpt():
    body = "仅正文很长时 " * 100
    r = kb._resolved_summary("", body)
    assert "仅正文很长" in r
    assert len(r) <= 420


def test_entry_row_returns_full_body_and_fields():
    body = "长正文" * 4000
    e = SimpleNamespace(
        id=7,
        knowledge_base_id=3,
        title="标题",
        summary="简述行",
        body=body,
        tags=["demo"],
        sort_order=1,
        source_url=" https://x.example/p ",
        source_meta={"kind": "web", "ref": "https://x.example/p"},
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 2, 12, 0, 0),
    )
    row = kb._entry_row(e)
    assert row["body"] == body
    assert row["summary"] == "简述行"
    assert row["source_url"] == "https://x.example/p"
    assert row["source_meta"]["kind"] == "web"
    for k in (
        "id",
        "title",
        "summary",
        "body",
        "source_url",
        "source_meta",
        "sort_order",
        "knowledge_base_id",
        "created_at",
        "updated_at",
    ):
        assert k in row


def test_knowledge_embed_chunks_splits_long_body():
    title = "T"
    summary = "S"
    body = ("块内容句子。" * 500) + "\n\n尾部唯一标记 KBCHUNK999"
    chunks = emb._knowledge_embed_chunks(title, body, summary)
    assert len(chunks) >= 2
    blob = "\n".join(chunks)
    assert "KBCHUNK999" in blob
    assert all("【知识条目】" in c for c in chunks)
    assert all("简述：S" in c for c in chunks)
