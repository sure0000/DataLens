from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
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
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE IF EXISTS data_sources ADD COLUMN IF NOT EXISTS description TEXT;"))
        conn.execute(text("ALTER TABLE IF EXISTS tables ADD COLUMN IF NOT EXISTS datasource_id INT;"))
        conn.execute(text("ALTER TABLE IF EXISTS columns ADD COLUMN IF NOT EXISTS quality_metrics JSONB;"))
        conn.execute(text("ALTER TABLE IF EXISTS business_domain_selections ADD COLUMN IF NOT EXISTS table_name TEXT;"))
