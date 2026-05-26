from collections.abc import Generator
from datetime import datetime, date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import get_settings


class BaseModel:
    """所有 ORM 模型的基类，提供通用序列化方法。"""

    def to_dict(self) -> dict:
        """将模型实例序列化为 dict，自动处理 datetime/date → isoformat。"""
        result: dict = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, (datetime, date)):
                val = val.isoformat()
            result[col.name] = val
        return result


settings = get_settings()
# 避免本机未启动 Postgres 时 init_db 长时间挂死，导致 uvicorn 一直停在 application startup
_pg_connect_args: dict = {"connect_timeout": 12}
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    connect_args=_pg_connect_args,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base(cls=BaseModel)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import models  # noqa: F401 — 注册 ORM 元数据

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    Base.metadata.create_all(bind=engine)

    # 分步提交：约束失败（如重复知识库名）不应回滚列/索引补丁
    with engine.begin() as conn:
        _ensure_safety_columns(conn)
    with engine.begin() as conn:
        _ensure_safety_indexes(conn)
    with engine.begin() as conn:
        _ensure_safety_constraints(conn)
    with engine.begin() as conn:
        _run_data_migrations(conn)


def _ensure_safety_columns(conn) -> None:
    """确保旧有迁移中添加的列存在——ADD COLUMN IF NOT EXISTS 无副作用。"""
    _cols = [
        ("data_sources", "description", "TEXT"),
        ("tables", "datasource_id", "INT"),
        ("columns", "quality_metrics", "JSONB"),
        ("business_domain_selections", "table_name", "TEXT"),
        ("knowledge_entries", "source_meta", "JSONB"),
        ("knowledge_entries", "summary", "TEXT NOT NULL DEFAULT ''"),
        ("knowledge_entries", "source_url", "TEXT"),
        ("knowledge_entries", "semantic_role", "TEXT"),
        ("knowledge_entries", "tags", "JSON"),
        ("knowledge_bases", "category", "TEXT"),
        ("knowledge_api_sources", "tags", "JSON"),
        ("knowledge_git_sources", "category", "TEXT"),
        ("knowledge_git_sources", "tags", "JSON"),
        ("document_chunks", "semantic_meta", "JSONB"),
        ("pipeline_runs", "source_id", "INT"),
        # Legacy semantic table columns (removed in Phase 1 ontology refactoring)
        # ("metric_definitions", "bound_table_refs", "JSONB"),
        # ("business_terms", "concept_id", "TEXT"),
        # ("metric_definitions", "concept_id", "TEXT"),
    ]
    for table, col, col_type in _cols:
        conn.execute(
            text(f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS {col} {col_type};")
        )
    # knowledge_api_sources 旧有 nullable 调整
    conn.execute(
        text("ALTER TABLE knowledge_api_sources ALTER COLUMN knowledge_base_id DROP NOT NULL;")
    )
    conn.execute(
        text("ALTER TABLE knowledge_api_sources ALTER COLUMN object_id DROP NOT NULL;")
    )


def _ensure_safety_indexes(conn) -> None:
    """确保关键查询索引存在（CREATE INDEX IF NOT EXISTS 无副作用）。"""
    _indexes = [
        ("idx_document_chunks_kb", "document_chunks", "knowledge_base_id"),
        ("idx_document_chunks_doc", "document_chunks", "document_id"),
        # Legacy semantic table indexes (removed in Phase 1 ontology refactoring)
        # ("idx_business_terms_kb", "business_terms", "knowledge_base_id"),
        # ("idx_metric_definitions_kb", "metric_definitions", "knowledge_base_id"),
        # ("idx_data_lineage_kb", "data_lineage", "knowledge_base_id"),
        # ("idx_data_lineage_git", "data_lineage", "git_source_id"),
        ("idx_pipeline_runs_kb", "pipeline_runs", "knowledge_base_id"),
        # ("idx_semantic_relations_kb", "semantic_relations", "knowledge_base_id"),
        # ("idx_semantic_relations_concept", "semantic_relations", "concept_id"),
    ]
    for idx_name, table, col in _indexes:
        conn.execute(
            text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({col});")
        )
    # HNSW 向量索引
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding "
            "ON document_chunks USING hnsw(embedding vector_cosine_ops);"
        )
    )
    # GIN 全文检索索引
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_tsv "
            "ON document_chunks USING gin(tsv);"
        )
    )


def _ensure_safety_constraints(conn) -> None:
    """添加唯一约束（无副作用）；存在重复数据时跳过对应约束，避免阻断列迁移。"""
    conn.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_datasource_name_host_db') THEN
                ALTER TABLE data_sources ADD CONSTRAINT uq_datasource_name_host_db UNIQUE (name, host, database);
            END IF;
        END $$;
    """))
    conn.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_knowledge_base_name') THEN
                IF NOT EXISTS (
                    SELECT 1 FROM knowledge_bases GROUP BY name HAVING COUNT(*) > 1
                ) THEN
                    ALTER TABLE knowledge_bases ADD CONSTRAINT uq_knowledge_base_name UNIQUE (name);
                END IF;
            END IF;
        END $$;
    """))


def _run_data_migrations(conn) -> None:
    """一次性数据修复——UPDATE 已在生产环境执行过，仅对新增数据生效。"""
    conn.execute(
        text(
            "UPDATE knowledge_entries SET summary = trim(substring(regexp_replace(trim(body), '[\\n\\r\\t]+', ' ', 'g') from 1 for 420)) "
            "WHERE trim(coalesce(summary, '')) = '' AND body IS NOT NULL AND trim(body) <> '';"
        )
    )
    conn.execute(
        text(
            "UPDATE knowledge_entries SET source_url = trim((source_meta->>'ref')) "
            "WHERE source_url IS NULL AND source_meta IS NOT NULL "
            "AND trim(coalesce(source_meta->>'kind','')) IN ('web','notion','confluence','obsidian') "
            "AND trim(coalesce(source_meta->>'ref','')) ~ '^https?://';"
        )
    )
