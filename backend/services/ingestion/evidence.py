"""EvidencePackage — unified view over file/git/api/database imports (no separate DB table yet)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    Document,
    KnowledgeDatabaseImport,
    KnowledgeEntry,
    KnowledgeGitSource,
)

ASSET_LABELS: dict[str, str] = {
    "semantic_doc": "业务语义",
    "physical_schema": "物理 Schema",
    "processing_code": "加工逻辑",
    "relation_lineage": "关系血缘",
    "governance": "治理上下文",
    "ttl_bundle": "结构化本体",
}

CONNECTOR_LABELS: dict[str, str] = {
    "file": "文件",
    "api": "官方 API",
    "git": "代码库",
    "database": "数据源",
    "manual": "手动条目",
    "ttl": "TTL 包",
}


def _processing_state(doc_indexed: int, doc_total: int, pipeline_status: str | None) -> str:
    if doc_total == 0:
        return "registered"
    if doc_indexed < doc_total:
        return "normalized"
    if pipeline_status == "running":
        return "ready_for_extraction"
    if pipeline_status in ("completed", "failed"):
        return "ready_for_extraction"
    return "indexed"


def list_evidence_packages(db: Session, kb_id: int) -> list[dict[str, Any]]:
    """Build evidence package list from existing KB sources (read-only synthesis)."""
    packages: list[dict[str, Any]] = []
    seq = 0

    # File / manual / API entries (grouped loosely per entry batch)
    entries = db.execute(
        select(KnowledgeEntry)
        .where(KnowledgeEntry.knowledge_base_id == kb_id)
        .order_by(KnowledgeEntry.id.desc())
    ).scalars().all()

    doc_stats = dict(
        db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .group_by(Document.status)
        ).all()
    )
    indexed = int(doc_stats.get("indexed", 0))
    total_docs = sum(int(v) for v in doc_stats.values())

    for entry in entries:
        meta = entry.source_meta if isinstance(entry.source_meta, dict) else {}
        kind = (meta.get("kind") or "file").lower()
        if kind == "git_file":
            continue
        if kind in ("notion", "confluence", "feishu", "api"):
            connector = "api"
            asset_kind = "semantic_doc"
        elif kind == "manual":
            connector = "manual"
            asset_kind = "semantic_doc"
        elif kind == "ttl":
            connector = "ttl"
            asset_kind = "ttl_bundle"
        else:
            connector = "file"
            asset_kind = "semantic_doc"

        seq += 1
        packages.append(
            {
                "id": f"entry-{entry.id}",
                "kb_id": kb_id,
                "display_id": f"EP-{1000 + seq}",
                "asset_kind": asset_kind,
                "asset_label": ASSET_LABELS.get(asset_kind, asset_kind),
                "connector": connector,
                "connector_label": CONNECTOR_LABELS.get(connector, connector),
                "title": entry.title,
                "source_ref": {"entry_id": entry.id, "kind": kind, **{k: v for k, v in meta.items() if k != "kind"}},
                "processing_state": "indexed" if total_docs else "registered",
                "linked_entry_ids": [entry.id],
                "document_count": 0,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
        )

    # Git sources → processing_code + relation_lineage virtual packages
    git_sources = db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id)
    ).scalars().all()
    for gs in git_sources:
        for asset_kind in ("processing_code", "relation_lineage"):
            seq += 1
            sync = gs.last_sync_status or "pending"
            state = "normalized" if sync == "ok" else "registered"
            packages.append(
                {
                    "id": f"git-{gs.id}-{asset_kind}",
                    "kb_id": kb_id,
                    "display_id": f"EP-{1000 + seq}",
                    "asset_kind": asset_kind,
                    "asset_label": ASSET_LABELS[asset_kind],
                    "connector": "git",
                    "connector_label": CONNECTOR_LABELS["git"],
                    "title": gs.name,
                    "source_ref": {
                        "git_source_id": gs.id,
                        "provider": gs.provider,
                        "owner": gs.owner,
                        "repo": gs.repo,
                        "branch": gs.branch,
                    },
                    "processing_state": state,
                    "linked_entry_ids": [],
                    "document_count": 0,
                    "created_at": gs.created_at.isoformat() if gs.created_at else None,
                }
            )

    # Database imports → physical_schema
    db_imports = db.execute(
        select(KnowledgeDatabaseImport).where(KnowledgeDatabaseImport.knowledge_base_id == kb_id)
    ).scalars().all()
    for di in db_imports:
        seq += 1
        packages.append(
            {
                "id": f"db-{di.id}",
                "kb_id": kb_id,
                "display_id": f"EP-{1000 + seq}",
                "asset_kind": "physical_schema",
                "asset_label": ASSET_LABELS["physical_schema"],
                "connector": "database",
                "connector_label": CONNECTOR_LABELS["database"],
                "title": f"{di.datasource_name}: {', '.join(di.database_names or [])}",
                "source_ref": {
                    "datasource_id": di.datasource_id,
                    "database_names": di.database_names,
                },
                "processing_state": "ready_for_extraction" if di.status == "imported" else "registered",
                "linked_entry_ids": [],
                "raw_location": {"table_meta_refs": True},
                "created_at": di.created_at.isoformat() if di.created_at else None,
            }
        )

    # KB-level document pipeline summary (synthetic package for indexed docs)
    if total_docs > 0:
        seq += 1
        packages.insert(
            0,
            {
                "id": f"kb-{kb_id}-documents",
                "kb_id": kb_id,
                "display_id": f"EP-{1000 + seq}",
                "asset_kind": "semantic_doc",
                "asset_label": ASSET_LABELS["semantic_doc"],
                "connector": "file",
                "connector_label": "文档流水线",
                "title": f"已登记文档 ({indexed}/{total_docs} 已索引)",
                "source_ref": {"document_pipeline": True},
                "processing_state": _processing_state(indexed, total_docs, None),
                "linked_entry_ids": [],
                "document_count": total_docs,
                "indexed_document_count": indexed,
                "created_at": datetime.utcnow().isoformat(),
            },
        )

    return packages
