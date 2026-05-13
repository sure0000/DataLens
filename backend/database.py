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
        # MCP 源全局化迁移：knowledge_base_id 改为可选，删除 cron/状态 字段
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ALTER COLUMN knowledge_base_id DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources DROP COLUMN IF EXISTS cron_expression;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources DROP COLUMN IF EXISTS enabled;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources DROP COLUMN IF EXISTS last_sync_at;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources DROP COLUMN IF EXISTS last_sync_status;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources DROP COLUMN IF EXISTS last_error;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ADD COLUMN IF NOT EXISTS mcp_args JSONB;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ADD COLUMN IF NOT EXISTS last_import_status TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ADD COLUMN IF NOT EXISTS last_import_error TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ADD COLUMN IF NOT EXISTS last_import_entries INT;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ADD COLUMN IF NOT EXISTS last_import_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE IF EXISTS knowledge_mcp_sources ADD COLUMN IF NOT EXISTS last_import_kb_id INT;"))

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
