#!/usr/bin/env python3
"""清理遗留孤立数据：证据包、孤儿文档/条目、失效流水线、无分块引用的 RDF 断言。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from database import SessionLocal
from services.source_cascade_cleanup import cleanup_legacy_orphans


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 DataLens 遗留孤立数据")
    parser.add_argument(
        "--kb-id",
        type=int,
        default=None,
        help="仅清理指定知识库；省略则处理全部知识库",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅统计将删除的数据，不写入数据库",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = cleanup_legacy_orphans(db, kb_id=args.kb_id, dry_run=args.dry_run)
        if not args.dry_run:
            db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
