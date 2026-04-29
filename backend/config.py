from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_ENV), extra="ignore")

    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/datalens",
        alias="DATABASE_URL",
    )
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    db_pool_size: int = Field(default=5, ge=1, le=50, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, ge=0, le=100, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=1800, ge=60, alias="DB_POOL_RECYCLE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
