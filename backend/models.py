from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# ---------------------------------------------------------------------------
# Document pipeline models (语义知识库核心)
# ---------------------------------------------------------------------------


class TableMeta(Base):
    __tablename__ = "tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    database_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    datasource_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))
    ddl: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    columns: Mapped[list["ColumnMeta"]] = relationship(back_populates="table")


class ColumnMeta(Base):
    __tablename__ = "columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"))
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    semantic_desc: Mapped[str | None] = mapped_column(Text)
    semantic_type: Mapped[str | None] = mapped_column(Text)
    is_usable: Mapped[bool | None] = mapped_column(Boolean)
    usable_reason: Mapped[str | None] = mapped_column(Text)
    null_ratio: Mapped[float | None] = mapped_column(Float)
    distinct_count: Mapped[int | None] = mapped_column(BigInteger)
    sample_values: Mapped[list | None] = mapped_column(JSON)
    top_values: Mapped[list | None] = mapped_column(JSON)
    quality_metrics: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    table: Mapped["TableMeta"] = relationship(back_populates="columns")


class TableSummary(Base):
    __tablename__ = "table_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    use_cases: Mapped[str | None] = mapped_column(Text)
    key_columns: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QueryExample(Base):
    __tablename__ = "query_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"))
    question: Mapped[str] = mapped_column(Text)
    sql_text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_type: Mapped[str] = mapped_column(Text)
    ref_id: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("name", "host", "database", name="uq_datasource_name_host_db"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RuntimeSetting(Base):
    """键值配置，如数据语义分析所用大模型。"""

    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class BusinessDomain(Base):
    __tablename__ = "business_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BusinessDomainDescription(Base):
    __tablename__ = "business_domain_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("business_domains.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BusinessDomainSelection(Base):
    __tablename__ = "business_domain_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("business_domains.id"))
    datasource_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    database_name: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("name", name="uq_knowledge_base_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pipeline_config: Mapped["PipelineConfig | None"] = relationship(back_populates="knowledge_base", uselist=False)
    documents: Mapped[list["Document"]] = relationship(back_populates="knowledge_base", cascade="all, delete-orphan")


class PipelineConfig(Base):
    """每个知识库的流水线配置：分块策略、清洗规则等。"""

    __tablename__ = "pipeline_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, unique=True)
    # 分块策略: heading | hierarchical | fixed
    chunk_strategy: Mapped[str] = mapped_column(Text, nullable=False, default="heading")
    chunk_size: Mapped[int] = mapped_column(Integer, default=1500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=200)
    # 清洗：最小块字符数，低于此值丢弃
    min_chunk_chars: Mapped[int] = mapped_column(Integer, default=20)
    # 近重复检测阈值（cosine 相似度），超过则跳过入库
    dedup_threshold: Mapped[float] = mapped_column(Float, default=0.97)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="pipeline_config")


class Document(Base):
    """流水线处理的文档单元，对应一次文件上传/Git文件/API页面。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    # 文档标题（文件名或页面标题）
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # 来源类型: file | git | notion | confluence | feishu | manual
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="file")
    source_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 原始文本（提取后，清洗前）
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 字符数统计
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 流水线状态: pending → extracting → cleaning → chunking → embedding → indexed | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 各阶段耗时（毫秒）
    stage_timings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 关联的 KnowledgeEntry（手动条目为 None）
    knowledge_entry_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_entries.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """文档分块后的最小检索单元，替代 Embedding 表中的 knowledge_entry 记录。"""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 在原文中的字符偏移（用于分块浏览器定位）
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 层级分块时的父块 id
    parent_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True)
    # 清洗质量分 0.0-1.0
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 轻量语义元数据：semantic_role、grounding(table_refs/column_refs)、confidence
    semantic_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 向量（与 Embedding 表并存，新文档走此表）
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    # tsvector 由 PostgreSQL GENERATED ALWAYS AS 自动维护，不在 ORM 中映射（避免 INSERT 时冲突）
    # tsv 列存在于 DB 中，仅通过原生 SQL 查询使用
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["Document"] = relationship(back_populates="chunks")


class KnowledgeEntry(Base):
    """单条可检索知识：标题 + 简述（列表）；正文详见 body，Copilot/RAG 使用全文。"""

    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 来源：手动 | 链接 | 文件 | notion/confluence/obsidian 等
    source_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 语义角色分类：table_overview | column_glossary | business_metric | query_pattern | join_guide | data_quality | general_reference
    semantic_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeGitSource(Base):
    """知识库绑定的 GitHub / GitLab 仓库：用于定期或手动同步源码/文档为知识条目。"""

    __tablename__ = "knowledge_git_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # github | gitlab
    api_base: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str] = mapped_column(Text, nullable=False)
    # 空字符串表示每次同步使用远端 default_branch（不固定分支名）
    branch: Mapped[str] = mapped_column(Text, nullable=False, default="")
    path_prefix: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token: Mapped[str] = mapped_column(Text, nullable=False)
    include_globs: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="*.md,*.sql,*.py,*.ts,*.tsx,*.java,*.go,*.rs,*.yml,*.yaml,*.json",
    )
    max_file_kb: Mapped[int] = mapped_column(Integer, default=512)
    max_files: Mapped[int] = mapped_column(Integer, default=200)
    cron_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BusinessDomainKnowledgeBase(Base):
    """业务域 ↔ 知识库（多对多），供 Copilot 按会话业务域拉取知识上下文。"""

    __tablename__ = "business_domain_knowledge_bases"
    __table_args__ = (UniqueConstraint("domain_id", "knowledge_base_id", name="uq_business_domain_kb"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("business_domains.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TableKnowledgeBase(Base):
    """数据表 ↔ 知识库（多对多）。"""

    __tablename__ = "table_knowledge_bases"
    __table_args__ = (UniqueConstraint("table_id", "knowledge_base_id", name="uq_table_kb"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TableKnowledgeEntry(Base):
    """数据表 ↔ 知识库条目（多对多），固定将全文注入上下文。"""

    __tablename__ = "table_knowledge_entries"
    __table_args__ = (UniqueConstraint("table_id", "knowledge_entry_id", name="uq_table_knowledge_entry"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), nullable=False)
    knowledge_entry_id: Mapped[int] = mapped_column(ForeignKey("knowledge_entries.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LlmConnection(Base):
    """用户配置的一条大模型接入（厂商 + Endpoint + Key + 固定模型）。"""

    __tablename__ = "llm_connections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_label: Mapped[str] = mapped_column(Text, nullable=False)
    custom_name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImportLog(Base):
    """统一的导入日志：记录所有来源的导入事件。"""

    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    entries_created: Mapped[int] = mapped_column(Integer, default=0)
    entries_updated: Mapped[int] = mapped_column(Integer, default=0)
    entries_deleted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeApiSource(Base):
    """官方 API 导入源（Notion / Confluence / 飞书），全局配置。kb_id 非空时为旧版 KB 绑定。"""

    __tablename__ = "knowledge_api_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    integration: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# 语义层模型 — 清洗流水线产出（术语、指标、血缘）
# ---------------------------------------------------------------------------


class BusinessTerm(Base):
    """AI 从文档中提取的业务术语，支持人工审核。"""

    __tablename__ = "business_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # metric | enum | time | dimension | other
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    source_entry_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_entries.id", ondelete="SET NULL"), nullable=True)
    related_fields: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    concept_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")  # pending_review | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MetricDefinition(Base):
    """AI 从文档中提取的指标口径定义，支持人工审核。"""

    __tablename__ = "metric_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    caliber: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_entry_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_entries.id", ondelete="SET NULL"), nullable=True)
    related_terms: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    bound_table_refs: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    concept_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")  # pending_review | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DataLineage(Base):
    """数据血缘关系 — 从代码库（dbt/SQL/ORM）自动解析的表间依赖。"""

    __tablename__ = "data_lineage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    git_source_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_git_sources.id", ondelete="SET NULL"), nullable=True)
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_field: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_field: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer: Mapped[str] = mapped_column(Text, nullable=False)  # ODS | DWD | DWS | ADS
    transform_logic: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")  # done | processing | pending
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineRun(Base):
    """记录每次语义清洗流水线的执行状态。"""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")  # running | completed | failed
    source_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SemanticRelation(Base):
    """轻量语义关系图：术语/指标/表/概念之间的可遍历边（域内厚、企业薄层 concept_id）。"""

    __tablename__ = "semantic_relations"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "relation_type",
            "source_type",
            "source_ref",
            "target_type",
            "target_ref",
            name="uq_semantic_relation_edge",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    # term_column | metric_table | table_join | concept_alias
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)  # term | metric | table | concept
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)  # column | table | concept
    target_ref: Mapped[str] = mapped_column(Text, nullable=False)
    concept_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    join_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True)
    source_entry_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_entries.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="approved")  # draft | approved | deprecated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeMcpSource(Base):
    """MCP 工具源 — 通过 Model Context Protocol 导入外部工具的知识。"""

    __tablename__ = "knowledge_mcp_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mcp_transport: Mapped[str] = mapped_column(Text, nullable=False)
    mcp_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcp_env: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mcp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcp_tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcp_tool_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mcp_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_mode: Mapped[str] = mapped_column(Text, nullable=False)
    max_entry_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    last_import_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_import_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_import_entries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_import_kb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

