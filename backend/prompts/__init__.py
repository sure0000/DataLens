"""Prompt 模板加载器。所有 LLM prompt 从本目录的 .txt 文件加载，便于非开发人员调优。"""

import os
from functools import lru_cache

_PROMPTS_DIR = os.path.dirname(__file__)


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """按名称加载 prompt 模板文件（自动缓存）。"""
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    with open(path, encoding="utf-8") as f:
        return f.read()
