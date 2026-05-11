"""pytest 收集时保证可从 `backend/` 根导入 `services`、`routers` 等包。"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
