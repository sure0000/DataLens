"""文档文本提取：从 knowledge_ingest.py 拆出纯提取逻辑，不含 DB 操作。"""
from __future__ import annotations

from services.knowledge_ingest import file_to_plain, normalize_filename, title_from_filename

__all__ = ["extract_from_bytes", "title_from_filename", "normalize_filename"]


def extract_from_bytes(filename: str, data: bytes) -> tuple[str, str]:
    """从文件字节提取 (title, plain_text)。复用 knowledge_ingest 的解析逻辑。"""
    title = title_from_filename(normalize_filename(filename))
    text = file_to_plain(filename, data)
    return title, text
