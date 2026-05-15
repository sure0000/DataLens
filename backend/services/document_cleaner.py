"""文档清洗层：噪声过滤、近重复检测、质量评分。"""
from __future__ import annotations

import re
import unicodedata

# 最小有效块字符数（低于此值视为噪声碎片）
_MIN_CHUNK_CHARS = 20
# 最大块字符数（超过此值截断）
_MAX_CHUNK_CHARS = 3000

# 常见 PDF/HTML 噪声模式
_NOISE_PATTERNS = [
    re.compile(r"^\s*第\s*\d+\s*页\s*$", re.MULTILINE),          # PDF 页码
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.MULTILINE),  # 英文页码
    re.compile(r"^\s*©.*版权.*$", re.MULTILINE),                   # 版权声明
    re.compile(r"^\s*Copyright\s+©.*$", re.MULTILINE),
    re.compile(r"^\s*All\s+rights\s+reserved\.?\s*$", re.MULTILINE),
]

# 全角→半角标点映射（仅转标点，保留中文字符）
_FULLWIDTH_MAP = str.maketrans(
    "，。！？；：（）【】《》",
    ",.!?;:()[]<>",
)


def clean_text(text: str) -> str:
    """对原始提取文本做基础清洗：去噪声、归一化标点、合并多余空行。"""
    t = text or ""
    # Unicode 归一化
    t = unicodedata.normalize("NFKC", t)
    # 去除噪声行
    for pat in _NOISE_PATTERNS:
        t = pat.sub("", t)
    # 全角标点归一化（保留中文字符，只转标点）
    t = t.translate(_FULLWIDTH_MAP)
    # 合并连续空行（超过 2 个换行压缩为 2 个）
    t = re.sub(r"\n{3,}", "\n\n", t)
    # 去除行尾空白
    t = "\n".join(line.rstrip() for line in t.splitlines())
    return t.strip()


def score_chunk(content: str) -> float:
    """对单个 chunk 计算质量分 0.0-1.0。"""
    if not content or not content.strip():
        return 0.0
    length = len(content.strip())
    if length < _MIN_CHUNK_CHARS:
        return 0.1
    # 字母/汉字比例（过低说明是乱码或纯符号）
    alpha_count = sum(1 for c in content if c.isalpha())
    alpha_ratio = alpha_count / max(length, 1)
    if alpha_ratio < 0.1:
        return 0.2
    # 长度分（500-2000 字符为最优区间）
    if 500 <= length <= 2000:
        length_score = 1.0
    elif length < 500:
        length_score = length / 500
    else:
        length_score = max(0.5, 1.0 - (length - 2000) / 4000)
    return round(min(1.0, alpha_ratio * 0.4 + length_score * 0.6), 3)


def filter_chunks(chunks: list[str], min_chars: int = _MIN_CHUNK_CHARS) -> list[tuple[str, float]]:
    """过滤低质量块，返回 (content, quality_score) 列表。"""
    result: list[tuple[str, float]] = []
    for chunk in chunks:
        c = chunk.strip()
        if len(c) < min_chars:
            continue
        if len(c) > _MAX_CHUNK_CHARS:
            c = c[:_MAX_CHUNK_CHARS]
        score = score_chunk(c)
        if score >= 0.15:
            result.append((c, score))
    return result
