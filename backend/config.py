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
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ORIGINS",
    )
    cors_origin_regex: str | None = Field(
        default=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$",
        alias="CORS_ORIGIN_REGEX",
    )
    db_pool_size: int = Field(default=20, ge=1, le=50, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=30, ge=0, le=100, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=600, ge=60, alias="DB_POOL_RECYCLE")
    # Copilot 未指定业务域时，语义 top_k 硬上限（无域时按表向量筛表，而非按 created_at 全量加载）
    copilot_max_tables_without_domain: int = Field(default=20, ge=1, le=50000, alias="COPILOT_MAX_TABLES_WITHOUT_DOMAIN")
    # 域内语义路由（知识 + 表向量 RRF 融合）后进入 schema 的候选表上限
    copilot_max_candidate_tables: int = Field(default=10, ge=1, le=100, alias="COPILOT_MAX_CANDIDATE_TABLES")
    # 梯度 fallback 第二档：放宽阈值后的候选表上限
    copilot_max_candidate_tables_expanded: int = Field(default=20, ge=1, le=200, alias="COPILOT_MAX_CANDIDATE_TABLES_EXPANDED")
    # 表摘要向量检索 probe 数（在 allowed_table_ids 范围内取 top_k）
    copilot_table_embed_top_k: int = Field(default=15, ge=1, le=200, alias="COPILOT_TABLE_EMBED_TOP_K")
    # 候选表综合分阈值：低于则触发梯度 fallback
    copilot_routing_min_score: float = Field(default=0.012, ge=0.0, alias="COPILOT_ROUTING_MIN_SCORE")
    copilot_routing_min_score_relaxed: float = Field(default=0.006, ge=0.0, alias="COPILOT_ROUTING_MIN_SCORE_RELAXED")
    copilot_routing_weight_knowledge: float = Field(default=1.0, ge=0.0, alias="COPILOT_ROUTING_WEIGHT_KNOWLEDGE")
    copilot_routing_weight_table_emb: float = Field(default=1.0, ge=0.0, alias="COPILOT_ROUTING_WEIGHT_TABLE_EMB")
    copilot_routing_explicit_link_bonus: float = Field(default=0.02, ge=0.0, alias="COPILOT_ROUTING_EXPLICIT_LINK_BONUS")
    # 列向量维表扩表 probe 数
    copilot_column_expand_top_k: int = Field(default=4, ge=0, le=20, alias="COPILOT_COLUMN_EXPAND_TOP_K")
    copilot_routing_weight_column_expand: float = Field(default=0.008, ge=0.0, alias="COPILOT_ROUTING_WEIGHT_COLUMN_EXPAND")
    # P2-1 自动业务域路由
    copilot_auto_domain_enabled: bool = Field(default=True, alias="COPILOT_AUTO_DOMAIN_ENABLED")
    copilot_auto_domain_apply_min_score: float = Field(default=0.55, ge=0.0, le=1.0, alias="COPILOT_AUTO_DOMAIN_APPLY_MIN_SCORE")
    copilot_auto_domain_suggest_min_score: float = Field(default=0.2, ge=0.0, le=1.0, alias="COPILOT_AUTO_DOMAIN_SUGGEST_MIN_SCORE")
    # P2-2 血缘 / JOIN 扩表
    copilot_lineage_expand_top_k: int = Field(default=4, ge=0, le=20, alias="COPILOT_LINEAGE_EXPAND_TOP_K")
    copilot_routing_weight_lineage: float = Field(default=0.006, ge=0.0, alias="COPILOT_ROUTING_WEIGHT_LINEAGE")
    copilot_join_blacklist: str = Field(default="", alias="COPILOT_JOIN_BLACKLIST")
    # 语义流水线：超过此秒数未更新 progress_at 的 running 任务视为卡住（默认 15 分钟）
    pipeline_run_timeout_seconds: int = Field(default=900, ge=60, le=3600, alias="PIPELINE_RUN_TIMEOUT_SECONDS")
    # 单次抽取最多处理的文档分块数（每块 1 次 LLM；4 个 chunk 步骤串行）
    extraction_max_chunks: int = Field(default=20, ge=1, le=80, alias="EXTRACTION_MAX_CHUNKS")
    # RRF 融合常数 k
    rrf_k: int = Field(default=60, ge=1, alias="RRF_K")
    # 知识库分块语义结构化：单文档最多 LLM 处理的 chunk 数
    semantic_chunk_structure_max: int = Field(default=40, ge=1, le=200, alias="SEMANTIC_CHUNK_STRUCTURE_MAX")
    # 术语/指标提取置信度 ≥ 此值时自动 approved（否则 pending_review）
    semantic_auto_approve_confidence: float = Field(default=80.0, ge=0.0, le=100.0, alias="SEMANTIC_AUTO_APPROVE_CONFIDENCE")
    # Ontology / Fuseki — RDF 默认写入 Fuseki（本地或 Docker），不再默认落盘 Trig
    fuseki_url: str = Field(default="http://localhost:3030", alias="FUSEKI_URL")
    fuseki_dataset: str = Field(default="datalens", alias="FUSEKI_DATASET")
    fuseki_admin_password: str = Field(default="admin", alias="FUSEKI_ADMIN_PASSWORD")
    ontology_ns: str = Field(default="https://datalens.local/ontology/", alias="ONTOLOGY_NS")
    ontology_tbox_graph: str = Field(default="https://datalens.local/graph/tbox", alias="ONTOLOGY_TBOX_GRAPH")
    ontology_enabled: bool = Field(default=True, alias="ONTOLOGY_ENABLED")
    fuseki_auto_start: bool = Field(default=True, alias="FUSEKI_AUTO_START")
    fuseki_fallback_memory: bool = Field(default=False, alias="FUSEKI_FALLBACK_MEMORY")
    fuseki_wait_seconds: int = Field(default=30, ge=0, le=120, alias="FUSEKI_WAIT_SECONDS")
    # 仅调试/离线：显式开启才写入 .run/ontology-store/*.trig
    ontology_local_store_enabled: bool = Field(default=False, alias="ONTOLOGY_LOCAL_STORE_ENABLED")
    ontology_local_store_path: str = Field(
        default=".run/ontology-store/datalens.trig",
        alias="ONTOLOGY_LOCAL_STORE_PATH",
    )
    ontology_min_confidence_auto_approve: float = Field(default=85.0, ge=0.0, le=100.0, alias="ONTOLOGY_MIN_CONFIDENCE_AUTO_APPROVE")
    ontology_quarantine_on_ambiguous_link: bool = Field(default=True, alias="ONTOLOGY_QUARANTINE_ON_AMBIGUOUS_LINK")
    ontology_merge_bidirectional_join: bool = Field(default=True, alias="ONTOLOGY_MERGE_BIDIRECTIONAL_JOIN")
    ontology_inferred_max_hops: int = Field(default=3, ge=1, le=10, alias="ONTOLOGY_INFERRED_MAX_HOPS")
    ontology_reconcile_cron_hours: int = Field(default=24, ge=1, alias="ONTOLOGY_RECONCILE_CRON_HOURS")
    # 出站 HTTP 是否读取 HTTP(S)_PROXY / ALL_PROXY；遇 SSL EOF 可设为 false 或关闭失效代理
    http_trust_env: bool = Field(default=True, alias="DATALENS_HTTP_TRUST_ENV")


@lru_cache
def get_settings() -> Settings:
    return Settings()
