"""文档分块策略：按标题、层级、固定大小三种模式。"""
from __future__ import annotations

import re

# 默认参数
_DEFAULT_CHUNK_SIZE = 1500
_DEFAULT_OVERLAP = 200
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_by_heading(text: str, max_chars: int = _DEFAULT_CHUNK_SIZE) -> list[str]:
    """按 Markdown 标题分块。每个标题及其正文作为一个 chunk；超长时再按固定大小切割。"""
    if not text.strip():
        return []

    # 找到所有标题位置
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return chunk_fixed(text, max_chars, _DEFAULT_OVERLAP)

    sections: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)

    # 前置无标题内容
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.insert(0, preamble)

    # 超长 section 再切割
    result: list[str] = []
    for sec in sections:
        if len(sec) <= max_chars:
            result.append(sec)
        else:
            # 保留标题行作为每个子块的前缀
            lines = sec.splitlines()
            heading_line = lines[0] if lines else ""
            body = "\n".join(lines[1:]).strip()
            sub_chunks = chunk_fixed(body, max_chars - len(heading_line) - 1, _DEFAULT_OVERLAP)
            for j, sub in enumerate(sub_chunks):
                if j == 0:
                    result.append(f"{heading_line}\n{sub}")
                else:
                    result.append(f"{heading_line}（续）\n{sub}")
    return result


def chunk_hierarchical(text: str, parent_size: int = 1500, child_size: int = 400, overlap: int = 80) -> list[dict]:
    """层级分块：父块 ~parent_size 字，子块 ~child_size 字。
    返回 list of dict: {content, parent_index, child_index}
    parent_index=-1 表示父块本身。
    """
    if not text.strip():
        return []

    parent_chunks = chunk_fixed(text, parent_size, overlap)
    result: list[dict] = []
    for pi, parent in enumerate(parent_chunks):
        result.append({"content": parent, "parent_index": pi, "child_index": -1})
        children = chunk_fixed(parent, child_size, overlap // 2)
        for ci, child in enumerate(children):
            result.append({"content": child, "parent_index": pi, "child_index": ci})
    return result


def chunk_fixed(text: str, max_chars: int = _DEFAULT_CHUNK_SIZE, overlap: int = _DEFAULT_OVERLAP) -> list[str]:
    """固定大小分块，带重叠。"""
    b = (text or "").strip()
    if not b:
        return []
    if len(b) <= max_chars:
        return [b]
    chunks: list[str] = []
    stride = max(64, max_chars - overlap)
    i = 0
    while i < len(b):
        end = min(i + max_chars, len(b))
        piece = b[i:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(b):
            break
        i += stride
    return chunks


def chunk_text(
    text: str,
    strategy: str = "heading",
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """统一入口：根据策略分块，返回纯文本列表（层级分块也展平为文本列表）。"""
    if strategy == "heading":
        return chunk_by_heading(text, chunk_size)
    if strategy == "hierarchical":
        items = chunk_hierarchical(text, chunk_size, chunk_size // 4, chunk_overlap)
        return [item["content"] for item in items]
    return chunk_fixed(text, chunk_size, chunk_overlap)
