"""静态守卫：禁止以位置参数传递 clean_triples 的 kb_id。"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _iter_clean_triples_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "clean_triples":
            continue
        yield node, path


def test_clean_triples_kb_id_must_be_keyword_only():
    violations: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        if ".venv" in path.parts or path.name.startswith("."):
            continue
        try:
            calls = list(_iter_clean_triples_calls(path))
        except SyntaxError:
            continue
        for call, src in calls:
            if len(call.args) > 1:
                violations.append(
                    f"{src.relative_to(BACKEND_ROOT)}:{call.lineno}: "
                    f"clean_triples 第 2 个及以后参数须为关键字（如 kb_id=...），"
                    f"当前有 {len(call.args)} 个位置参数"
                )
            kw_names = {kw.arg for kw in call.keywords if kw.arg}
            if call.args and "kb_id" not in kw_names:
                # 仅有 triples 位置参数时，kb_id 必须在 keywords 里
                if not any(k == "kb_id" for k in kw_names):
                    # 无 kb_id 的调用（若存在）由运行时其它测试覆盖
                    pass

    assert not violations, "发现非法 clean_triples 调用:\n" + "\n".join(violations)
