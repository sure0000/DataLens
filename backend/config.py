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
    # 可选；兼容 OpenAI 代理或自建网关（偏好设置中的 URL 优先生效）
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    db_pool_size: int = Field(default=20, ge=1, le=50, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=30, ge=0, le=100, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=600, ge=60, alias="DB_POOL_RECYCLE")
    # Copilot 未指定业务域时，最多带入多少张已登记表的元数据（防极端大库撑爆上下文）；指定业务域时以域内挂载为准、不受此上限约束。
    copilot_max_tables_without_domain: int = Field(default=2000, ge=1, le=50000, alias="COPILOT_MAX_TABLES_WITHOUT_DOMAIN")
    # 语义流水线超时阈值（秒），超过此时间的 running 状态自动标记为 failed
    pipeline_run_timeout_seconds: int = Field(default=300, ge=60, le=3600, alias="PIPELINE_RUN_TIMEOUT_SECONDS")
    # RRF 融合常数 k
    rrf_k: int = Field(default=60, ge=1, alias="RRF_K")


@lru_cache
def get_settings() -> Settings:
    return Settings()
