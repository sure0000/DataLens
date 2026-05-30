"""导入源级文档索引就绪检查（语义清洗前置条件）。"""

from __future__ import annotations

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from models import Document, KnowledgeApiSource, KnowledgeEntry

from services.document_index_policy import MAX_AUTO_INDEX_ATTEMPTS

_INDEXED_OK = frozenset({"indexed"})


def _entry_ids_for_git_source(db: Session, kb_id: int, git_source_id: int) -> list[int]:
    rows = db.scalars(
        select(KnowledgeEntry.id).where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            cast(KnowledgeEntry.source_meta, JSONB)["kind"].astext == "git_file",
            cast(KnowledgeEntry.source_meta, JSONB)["git_source_id"].astext == str(git_source_id),
        )
    ).all()
    return list(rows)


def _entries_for_api_source(db: Session, kb_id: int, src: KnowledgeApiSource) -> list[KnowledgeEntry]:
    kind = f"{(src.integration or '').strip().lower()}_api"
    oid = (src.object_id or "").strip()
    rows = db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.knowledge_base_id == kb_id)
    ).scalars().all()
    matched: list[KnowledgeEntry] = []
    for entry in rows:
        meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
        if meta.get("kind") != kind:
            continue
        if str(meta.get("api_source_id") or "") == str(src.id):
            matched.append(entry)
            continue
        if oid and str(meta.get("ref") or "") == oid:
            matched.append(entry)
            continue
        if not oid and not meta.get("api_source_id"):
            matched.append(entry)
    return matched


def _documents_for_entry_ids(db: Session, kb_id: int, entry_ids: list[int]) -> list[Document]:
    if not entry_ids:
        return []
    return list(
        db.scalars(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id.in_(entry_ids),
            )
        ).all()
    )


def _assert_any_indexed(docs: list[Document], *, empty_hint: str) -> None:
    if not docs:
        raise ValueError(empty_hint)
    indexed = [d for d in docs if d.status in _INDEXED_OK]
    if indexed:
        return
    for doc in docs:
        msg = _describe_document_block(doc)
        if msg:
            raise ValueError(msg)
    raise ValueError("文档尚未完成索引，请稍候或先完成索引")


def assert_document_indexed_for_semantic_clean(
    db: Session,
    kb_id: int,
    source_id: int,
    source_type: str,
) -> None:
    """按导入源类型检查是否具备语义清洗所需的已索引文档。"""
    st = (source_type or "").strip().lower()

    if st == "database":
        return

    if st == "git":
        entry_ids = _entry_ids_for_git_source(db, kb_id, source_id)
        if not entry_ids:
            raise ValueError("该 Git 源暂无已同步文件，请先执行「同步仓库」")
        # 代码库清洗直接读取 git_file 条目正文（血缘/JOIN），不要求文档分块索引。
        return

    if st == "api":
        src = db.get(KnowledgeApiSource, source_id)
        if not src:
            raise ValueError("API 源不存在")
        if src.knowledge_base_id is not None and src.knowledge_base_id != kb_id:
            raise ValueError("API 源不属于该知识库")
        entries = _entries_for_api_source(db, kb_id, src)
        if not entries:
            raise ValueError("该 API 源暂无关联条目，请先「重新导入」")
        entry_ids = [e.id for e in entries]
        docs = _documents_for_entry_ids(db, kb_id, entry_ids)
        _assert_any_indexed(
            docs,
            empty_hint="API 条目已导入但尚无文档索引，请在详情页「设置 → 重新索引」",
        )
        return

    if st in {"file", "api_entry", "manual"}:
        doc = db.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id,
                Document.knowledge_entry_id == source_id,
            )
        ).scalars().first()
        if doc is None:
            raise ValueError("该源尚无文档索引记录，请等待导入流水线完成或使用「重新索引」")
        msg = _describe_document_block(doc)
        if msg:
            raise ValueError(msg)
        return

    raise ValueError(f"不支持的导入源类型：{source_type}")


def _describe_document_block(doc: Document) -> str | None:
    if doc.status in _INDEXED_OK:
        return None
    if doc.status == "failed":
        attempts = int(doc.index_attempts or 0)
        if attempts >= MAX_AUTO_INDEX_ATTEMPTS:
            return (
                f"文档索引已失败 {attempts} 次，请先使用「手动索引」完成索引后再进行语义清洗"
            )
        return f"文档索引失败（{doc.error_message or '未知原因'}），请先重试索引"
    if doc.status != "indexed":
        return f"文档尚未完成索引（当前：{doc.status}），请稍候或先完成索引"
    return None
