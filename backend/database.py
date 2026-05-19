from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import get_settings

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
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import models  # noqa: F401 — 注册 ORM 元数据（含 llm_connections 等新表）

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE IF EXISTS data_sources ADD COLUMN IF NOT EXISTS description TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS tables ADD COLUMN IF NOT EXISTS datasource_id INT;"))
        conn.execute(text("ALTER TABLE IF EXISTS columns ADD COLUMN IF NOT EXISTS quality_metrics JSONB;"))
        conn.execute(text("ALTER TABLE IF EXISTS business_domain_selections ADD COLUMN IF NOT EXISTS table_name TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_entries ADD COLUMN IF NOT EXISTS source_meta JSONB;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_entries ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_entries ADD COLUMN IF NOT EXISTS source_url TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_entries ADD COLUMN IF NOT EXISTS semantic_role TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_entries ADD COLUMN IF NOT EXISTS tags JSON;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS category TEXT;"))
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


        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_git_sources (
                    id SERIAL PRIMARY KEY,
                    knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    api_base TEXT,
                    owner TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    branch TEXT NOT NULL DEFAULT 'main',
                    path_prefix TEXT NOT NULL DEFAULT '',
                    token TEXT NOT NULL,
                    include_globs TEXT NOT NULL DEFAULT '*.md,*.sql,*.py,*.ts,*.tsx,*.java,*.go,*.rs,*.yml,*.yaml,*.json',
                    max_file_kb INT NOT NULL DEFAULT 512,
                    max_files INT NOT NULL DEFAULT 200,
                    cron_expression TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    last_sync_at TIMESTAMP,
                    last_sync_status TEXT,
                    last_error TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                    updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS import_logs (
                    id SERIAL PRIMARY KEY,
                    knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                    source_type TEXT NOT NULL,
                    source_id INT,
                    source_name TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    entries_created INT NOT NULL DEFAULT 0,
                    entries_updated INT NOT NULL DEFAULT 0,
                    entries_deleted INT NOT NULL DEFAULT 0,
                    error_message TEXT,
                    started_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_api_sources (
                    id SERIAL PRIMARY KEY,
                    knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    integration TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    extra JSONB,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    last_sync_at TIMESTAMP,
                    last_sync_status TEXT,
                    last_error TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                    updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
                );
                """
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_api_sources ALTER COLUMN knowledge_base_id DROP NOT NULL;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_api_sources ALTER COLUMN object_id DROP NOT NULL;"
            )
        )
        conn.execute(text("ALTER TABLE knowledge_api_sources ADD COLUMN IF NOT EXISTS tags JSON;"))
        # 语义知识库新表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pipeline_configs (
                id SERIAL PRIMARY KEY,
                knowledge_base_id INT NOT NULL UNIQUE REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                chunk_strategy TEXT NOT NULL DEFAULT 'heading',
                chunk_size INT NOT NULL DEFAULT 1500,
                chunk_overlap INT NOT NULL DEFAULT 200,
                min_chunk_chars INT NOT NULL DEFAULT 20,
                dedup_threshold FLOAT NOT NULL DEFAULT 0.97,
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'file',
                source_meta JSONB,
                raw_text TEXT,
                char_count INT,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                stage_timings JSONB,
                knowledge_entry_id INT REFERENCES knowledge_entries(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                chunk_index INT NOT NULL,
                content TEXT NOT NULL,
                char_start INT,
                char_end INT,
                parent_chunk_id INT REFERENCES document_chunks(id) ON DELETE SET NULL,
                quality_score FLOAT,
                embedding vector(1536),
                tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_kb ON document_chunks(knowledge_base_id);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_doc ON document_chunks(document_id);"
        ))
        # 迁移：将旧的 tsv TEXT 列升级为 tsvector GENERATED 列（必须在建 GIN 索引前执行）
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='document_chunks' AND column_name='tsv'
                    AND data_type='text'
                ) THEN
                    ALTER TABLE document_chunks DROP COLUMN tsv;
                    ALTER TABLE document_chunks
                        ADD COLUMN tsv tsvector
                        GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
                ELSIF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='document_chunks' AND column_name='tsv'
                ) THEN
                    ALTER TABLE document_chunks
                        ADD COLUMN tsv tsvector
                        GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
                END IF;
            END $$;
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_tsv ON document_chunks USING gin(tsv);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks USING hnsw(embedding vector_cosine_ops);"
        ))
        conn.execute(text(
            "ALTER TABLE knowledge_git_sources ADD COLUMN IF NOT EXISTS category TEXT;"
        ))
        conn.execute(text(
            "ALTER TABLE knowledge_git_sources ADD COLUMN IF NOT EXISTS tags JSON;"
        ))
        # ── 语义层模型（术语、指标、血缘、流水线运行记录） ──
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS business_terms (
                id SERIAL PRIMARY KEY,
                knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                definition TEXT NOT NULL,
                source_entry_id INT REFERENCES knowledge_entries(id) ON DELETE SET NULL,
                related_fields JSONB DEFAULT '[]',
                confidence FLOAT NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'pending_review',
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_business_terms_kb ON business_terms(knowledge_base_id);"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS metric_definitions (
                id SERIAL PRIMARY KEY,
                knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                formula TEXT NOT NULL,
                caliber TEXT,
                source_entry_id INT REFERENCES knowledge_entries(id) ON DELETE SET NULL,
                related_terms JSONB DEFAULT '[]',
                confidence FLOAT NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'pending_review',
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_metric_definitions_kb ON metric_definitions(knowledge_base_id);"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS data_lineage (
                id SERIAL PRIMARY KEY,
                knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                git_source_id INT REFERENCES knowledge_git_sources(id) ON DELETE SET NULL,
                source_table TEXT NOT NULL,
                target_table TEXT NOT NULL,
                source_field TEXT,
                target_field TEXT,
                layer TEXT NOT NULL,
                transform_logic TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_data_lineage_kb ON data_lineage(knowledge_base_id);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_data_lineage_git ON data_lineage(git_source_id);"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id SERIAL PRIMARY KEY,
                knowledge_base_id INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'running',
                source_type TEXT,
                steps JSONB,
                started_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                completed_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_kb ON pipeline_runs(knowledge_base_id);"
        ))
