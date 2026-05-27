# DataLens 项目全貌（人与 AI 双可读）

> 本文档合并了原 `PROJECT_BRIEF_AI.md`、`IMPLEMENTATION_SPEC_AI.md`、`AI_READER_PROMPT.md`，反映 **2026-05-25** 最新状态（含知识库语义结构化、Copilot 多信号路由、轻量语义关系图）。

---

## AI 阅读指南

如果作为 AI 被要求分析本项目，请按以下顺序阅读：

1. **本文档**（先读完全文建立全局模型）
2. `README.md`（运行方式与端口）
3. 代码入口：`backend/main.py`、`frontend/app/layout.tsx`

**约束：** 不要臆测代码中不存在的能力；结论必须可被文档或代码支持；信息不足时明确标注。

---

## 1. 术语表

| 术语 | 定义 |
|------|------|
| 数据源 | 可连接的数据系统实例（MySQL / PostgreSQL / ClickHouse / Trino / Hive 等 13 种） |
| 数据库 | 数据源中的逻辑库 |
| 数据表 | 数据库中的表对象 |
| 字段语义 | 字段在业务中的含义（如"订单金额""用户ID""下单时间"），含语义类型 metric/dimension/time/id/enum |
| Profiling | 对样本数据做统计分析：空值率、去重数、分位数、top值、枚举检测、风险评分 |
| 表理解 | 前述三步的统称：Schema提取 + Profiling + LLM融合 → 列语义 + 表摘要 |
| RAG | 检索增强生成：向量检索历史语义和知识条目，注入 LLM 上下文提升 SQL 质量 |
| Copilot | 面向自然语言问答的 ChatBI 助手页面，支持生成 SQL + 只读执行 + 结果预览 |
| 业务域 | 用户定义的业务范畴（如"交易域""用户域"），可绑定库表和知识库 |
| 知识库 | 可检索的业务文档集合；支持 Markdown 条目、文档流水线分块、Git/API 同步 |
| 语义角色 (semantic_role) | 知识条目的业务分类：如 `business_metric`、`join_guide`、`column_glossary` 等 |
| 语义关系 (semantic_relations) | 术语/指标/表/概念之间的可遍历边，供 Copilot 图扩展路由 |
| concept_id | 企业薄层统一概念标识（如 `metric.gmv`），支持跨域别名对齐 |
| 业务术语 / 指标口径 | AI 从知识库提取并经审核的结构化资产（`business_terms`、`metric_definitions`） |

## 2. 项目定义

**一句话定义：** DataLens 是一个「数据表智能理解 + 自然语言转 SQL + 只读执行预览」的轻量分析系统。

**核心痛点：** 陌生表字段含义不明 / 不清楚表能分析什么 / 写 SQL 需频繁翻文档。

**目标用户：** 数据分析师 / 数仓开发 / 需要接手陌生数据表的业务分析角色。

## 3. 功能边界

### In Scope（当前已实现）

- 13 种数据源接入：MySQL / MariaDB / Doris / StarRocks / PostgreSQL / Greenplum / SQL Server / SQLite / ClickHouse / Trino / Hive
- 数据源 CRUD、连接测试、库表目录浏览
- 异步表分析：Schema 提取 → Profiling → LLM 列语义 → LLM 表摘要 → 向量持久化
- 表详情页：字段语义、质量指标、表五段式摘要、分析场景推荐
- 业务域管理：创建域、维护描述、选择关联库表、绑定知识库
- 知识库管理：手动条目、文件上传、Git 仓库同步（GitHub/GitLab）、API 源（Notion/飞书等）、代码库分析
- **文档流水线**：extract → clean → chunk → embed → **语义结构化**（`semantic_meta`）→ 索引
- **语义提取流水线**：术语 / 指标口径 / 数据血缘 LLM 提取 + **`semantic_relations` 关系图同步**
- Copilot ChatBI：自然语言 → **多信号表路由** → SQL 生成 → 只读执行 → 结果预览（SSE 流式）
- Copilot 路由：知识 grounding、表/列向量、指标术语、血缘/语义图 1-hop 扩表、梯度 fallback、`routing_trace`
- SQL 安全护栏：sqlglot AST 只读校验 + 前缀白名单双重保护
- LLM 无 Key 兜底：未配置 API Key 时用规则和本地向量提供基本链路可用性
- 大模型多厂商接入：DeepSeek / OpenAI / 自定义兼容端点
- **OWL/RDF 本体引擎**：Apache Jena Fuseki 三元组存储、SPARQL 查询与推理、OWL 2 RL 增量推理
- **本体建模工作台**：术语/指标/关系/层级的可视化浏览与同步管理
- **SHACL 校验写入**：三元组写入前强制校验，通过入 production graph，失败入 quarantine
- **Copilot 本体路由**：OntologyRouter（SPARQL 概念/表路由）、ContextAssembler（LLM 上下文组装）、CopilotPipeline（统一入口）
- **前端本体组件**：ConceptHierarchyTree、RelationGraph、MetricDerivationChain、TripleViewer、QuarantineList、ShaclDashboard、ConfidenceDistribution

### Out of Scope（当前不做）

- 完整企业级数据血缘与治理平台（已有轻量 `data_lineage` + `semantic_relations`）
- 复杂权限 / 多租户 / 审计合规
- 团队协作工作流（审批、评审、共享空间）

> **已纳入 Scope（2026-05）**: 基于 Apache Jena Fuseki 的 OWL/RDF 本体引擎、SPARQL 语义路由、SHACL 校验写入门、OWL 2 RL 增量推理。

## 4. 端到端业务流程

```
配置阶段:
  用户录入数据源 ─┐
  用户配置Git/API同步 ─┤→ 文档/条目入库
                       │     ├→ 文档流水线: clean → chunk → embed → 语义结构化
                       │     └→ 语义提取: 术语 / 指标 / 血缘 → semantic_relations
                       ├→ 代码库分析(提取表引用/枚举/聚合) → TableKnowledgeEntry 链接

使用阶段:
  用户选择分析范围 → Schema+样本 → Profiler → LLM 列语义/表摘要 → 向量持久化
    → Copilot 提问（可选业务域 / 单表锁定）
    → routing_bundle 共享检索 → 多信号表路由 + 知识/口径注入
    → LLM 生成 SQL → AST 校验 + sql_review → 只读执行 → 返回结果
```

## 5. 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python + FastAPI + SQLAlchemy (async) |
| 数据库 | PostgreSQL + pgvector 扩展（向量检索） |
| 连接器 | PyMySQL / psycopg2 / clickhouse-driver / trino / pyodbc 等 |
| LLM | DeepSeek（主）/ OpenAI（备）/ 自定义端点 |
| Embedding | text-embedding-3-small (1536维)，无 Key 时本地确定性向量兜底 |
| SQL 护栏 | sqlglot AST 解析，方言随 source_type 映射 |
| 前端 | Next.js App Router + TypeScript + Tailwind CSS |

## 6. 代码结构

```
backend/
├── main.py                     # 应用入口，路由注册
├── database.py                 # DB session/engine，建表
├── models.py                   # ORM 模型（20+ 表）
├── routers/
│   ├── analyze.py              # 异步分析入口 + 业务上下文构造
│   ├── connect.py              # 连接测试、库表列表
│   ├── copilot.py              # 问答 + SSE 流式
│   ├── datasources.py          # 数据源 CRUD、目录浏览
│   ├── tables.py               # 表详情聚合
│   ├── business_domains.py     # 业务域 CRUD + 选择
│   ├── knowledge_bases.py      # 知识库 CRUD + 条目 + 文件上传 + 文档流水线
│   ├── knowledge_git_sources.py # Git 同步源管理
│   ├── knowledge_api_sources.py # Notion/飞书等 API 源
│   ├── knowledge_semantic.py   # 术语/指标/血缘 CRUD + 语义流水线
│   ├── llm_settings.py         # 大模型偏好设置
│   └── diagnostics.py          # 诊断接口
├── services/
│   ├── context_builder.py      # Copilot 上下文：表路由、知识聚合
│   ├── routing_bundle.py       # 共享 KB 检索 bundle
│   ├── routing/                # metric / lineage / graph / domain 路由
│   ├── knowledge_pipeline_service.py  # 文档 clean/chunk/embed/structuring
│   ├── chunk_semantic_structuring.py  # chunk semantic_meta
│   ├── semantic_extraction.py  # 术语/指标/血缘 LLM 提取
│   ├── semantic_relation_sync.py # semantic_relations 同步
│   ├── semantic_grounding.py   # grounding 解析、role 推断
│   ├── retrieval_service.py    # Entry + Chunk 混合检索 (RRF)
│   ├── schema_extractor.py     # Schema/样本/只读 SQL 执行
│   ├── profiler.py             # 列统计画像
│   ├── llm_service.py          # 列语义、表摘要、SQL 生成
│   ├── rag_service.py          # 问答主流程
│   ├── codebase_analyzer.py    # 代码库分析
│   ├── embedding_service.py    # 向量检索
│   ├── document_cleaner.py     # 文档清洗
│   ├── document_chunker.py     # 文档分块
│   ├── sql_ast_guard.py        # sqlglot 只读校验
│   ├── git_knowledge_sync.py   # Git 同步
│   └── git_schedule.py         # Git 定时调度
├── prompts/                    # LLM prompt 模板
└── tests/                      # pytest

frontend/
├── app/                        # Next.js App Router 页面
│   ├── page.tsx                # 首页（业务域列表）
│   ├── copilot/page.tsx        # Copilot 对话
│   ├── datasources/            # 数据源管理、目录浏览
│   ├── table/[id]/page.tsx     # 表详情画像
│   ├── business-domains/       # 业务域详情
│   ├── knowledge-bases/        # 知识库管理
│   └── settings/page.tsx       # LLM 偏好设置
├── components/                 # 通用组件
│   ├── CopilotChat.tsx         # Copilot 对话容器
│   ├── CopilotExecutionTrace.tsx # 执行链路可视化
│   ├── ColumnCard.tsx          # 列信息卡片
│   ├── SqlBlock.tsx            # SQL 代码块
│   └── ...
└── lib/
    ├── api.ts                  # 前端 API 封装
    └── copilotStream.ts        # SSE 流处理
```

## 7. 核心数据流

### 7.0 知识库文档流水线

```
文件 / API / Git 同步
  │
  ▼
knowledge_pipeline_service.run_pipeline()
  ├── clean_text()           # 去噪声、标点归一化
  ├── chunk_text()           # 按标题 / 固定长度分块
  ├── embed → DocumentChunk  # 向量 + tsvector 全文索引
  └── structure_document_chunks()   # Stage 5（需 LLM）
        ├── semantic_meta: semantic_role + grounding + join_edges
        ├── KnowledgeEntry.semantic_role 回写
        ├── data_lineage 同步（join_guide）
        ├── MetricDefinition.bound_table_refs 回填
        └── semantic_relations 同步
  │
  ▼（后台）
semantic_extraction.run_semantic_pipeline()
  ├── 术语提取 → business_terms (+ concept_id)
  ├── 指标提取 → metric_definitions (+ bound_table_refs)
  ├── 血缘提取 → data_lineage（Git 源）
  └── semantic_relations 全量同步
```

### 7.0.1 代码库分析管道

```
GitHub / GitLab 仓库
  │
  ▼
git_knowledge_sync.py
  ├── 拉取匹配文件 → KnowledgeEntry (kind=git_file)
  ├── 生成 pgvector 嵌入
  └── 同步完成后触发 ──────────────────┐
                                        ▼
                              codebase_analyzer.py
                                ├── 预过滤 (regex)
                                │   · SQL: FROM/JOIN/INTO table
                                │   · ORM: __tablename__ / table_name
                                │   · DBT: ref('...') / source('...')
                                │   · YAML: table: xxx
                                │
                                ├── LLM 提取 (有 LLM 时)
                                │   · table_name → 解析出的物理表名
                                │   · columns → 代码中引用的列名
                                │   · enum_values → WHERE col IN ('a','b')
                                │   · aggregation_hints → SUM/AVG/COUNT 方式
                                │   · join_with → JOIN 关联的表
                                │
                                └── 正则兜底 (无 LLM 时)
                                    · 提取表名用于创建链接

                              ▼ 持久化
                              ├── TableKnowledgeEntry 链接 (代码文件 ↔ TableMeta)
                              ├── ColumnMeta.quality_metrics.enum (代码中的枚举值)
                              ├── ColumnMeta.quality_metrics.aggregation_hint (聚合方式)
                              └── KnowledgeEntry.source_meta.pending_table_refs
                                  (若表尚未登记，暂存等表分析后补填)
```

### 7.1 表理解生成

```
原始数据                         中间数据                        表理解数据
───────────────────────────────────────────────────────────────────────────
COLUMN_NAME ─┐
DATA_TYPE  ─┤
COLUMN_TYPE─┤                             ┌→ ColumnMeta.semantic_desc
sample_data─┼→ profile_column() ─→ profiles[] ─→┤→ ColumnMeta.semantic_type
            │   · null_ratio                │→ ColumnMeta.is_usable
            │   · distinct_count            │
            │   · top_values                └→ analyze_column()
            │   · quality_metrics               ↑ domain_contexts
            │     ├─ risk_level                 ↑ domain_knowledge_entries
            │     ├─ enum {kind, values}        ↑ (来自代码库分析的
            │     ├─ distribution {p25,p50,p75} ↑  列使用模式与枚举值)
            │     ├─ zero_ratio / outlier_count
            │     └─ aggregation_hint ←────────── 由 codebase_analyzer 补填
            │
代码库分析 ──┤                                     rows_for_summary[]
(codebase    │                                           │
 analyzer)   │     BusinessDomain ─┐                      ▼
  ·提取表引用─┤     BusinessDomain  ┤               analyze_table()
  ·提取枚举值─┤     Description     ┤                   ↑ business_context
  ·提取聚合  ─┤     KnowledgeEntry  ┤                   │
              │       (via                          ▼
  ┌─ 表已登记 → TableKnowledgeEntry     TableSummary.summary (5章节)
  │            ColumnMeta.quality_metrics           TableSummary.use_cases
  └─ 表未登记 → pending_table_refs (暂存)          TableSummary.key_columns
                      │                            TableSummary.warnings
                      ▼
              catch_up_pending_refs()
              (表分析完成后调用，补填之前暂存的列提示)
```

**关键优化（2026-05）：**
- 列级分位数（P25/P50/P75）帮助 LLM 理解数据分布
- 零值率、负值率、IQR 异常值检测、字符串长度范围等新增维度
- 空值率 >95% 或单值列跳过 LLM，节省调用
- 知识条目按与表名/列名的关键词匹配度排序（相关条目正文 3000 字，不相关 800 字）
- 列分析失败不回滚整表，单列兜底
- 宽表（>50列）按 metric > time > id > enum > dimension 优先级裁剪
- key_columns 与真实列名交集校验，防止幻觉
- 表摘要缺失章节先尝试 LLM 定向补全，不可用时规则兜底
- **代码库分析增强**：Git 同步后自动分析代码文件，提取表引用+枚举值+聚合方式
- **暂存-补填机制**：代码库先于数据源接入时，引用暂存，表分析后自动匹配补填 ColumnMeta

### 7.2 Copilot 问答链路

```
用户问题 + 可选 table_id / business_domain_id
  │
  ├→ guardrail_for_question()
  ├→ classify_question_intent()          # 意图前置：general_qa 跳过全量 schema
  │
  ├→ [若 general_qa] → answer_general_question()
  │
  └→ [若 sql_query]
      ├→ build_routing_search_bundle()   # 单次 embed + 统一 KB hybrid 检索
      │
      ├→ collect_knowledge_context_text()
      │     ├→ 固定全文: TableKnowledgeEntry
      │     └→ 混合检索: Entry + DocumentChunk（RRF），按 semantic_role 分流加权
      │
      ├→ build_priority_context()        # 多信号表路由
      │     ├→ 知识 grounding / 表名匹配 / 显式链接
      │     ├→ 表摘要向量直搜 + RRF 融合
      │     ├→ 指标/术语路由（metric_router，含 concept_alias）
      │     ├→ 列向量维表扩表
      │     ├→ apply_graph_expansion()   # lineage + semantic_relations 1-hop
      │     └→ 梯度 fallback + routing_trace
      │
      ├→ generate_sql() → AST 校验 → execute_readonly_sql()
      └→ sql_review（域外表检测，review 标签）
```

详见 [`COPILOT_ROUTING_OPTIMIZATION.md`](./COPILOT_ROUTING_OPTIMIZATION.md)。

## 8. 关键数据模型

| 模型 | 表名 | 核心字段 | 用途 |
|------|------|----------|------|
| DataSource | data_sources | name, source_type, host, port, database, username, password, description | 数据源连接配置 |
| TableMeta | tables | table_name, database_name, source_type, datasource_id, ddl, row_count, status | 表分析状态与元数据 |
| ColumnMeta | columns | column_name, data_type, comment, semantic_desc, semantic_type, is_usable, null_ratio, distinct_count, sample_values, quality_metrics | 列语义+质量画像 |
| TableSummary | table_summary | summary, use_cases, key_columns, warnings | 表五段式摘要（业务描述/数据定位/核心口径/使用建议/风险边界） |
| QueryExample | query_examples | question, sql_text, explanation | 历史问答对 |
| Embedding | embeddings | ref_type, ref_id, content, embedding(vector 1536) | 向量检索 |
| BusinessDomain | business_domains | name | 业务域 |
| BusinessDomainDescription | business_domain_descriptions | domain_id, content | 域描述 |
| BusinessDomainSelection | business_domain_selections | domain_id, datasource_id, database_name, table_name | 域→库表关联 |
| KnowledgeBase | knowledge_bases | name, description | 知识库 |
| KnowledgeEntry | knowledge_entries | title, summary, body, semantic_role, tags, source_meta | 知识条目 |
| Document | documents | knowledge_base_id, title, status, raw_text, stage_timings | 文档流水线单元 |
| DocumentChunk | document_chunks | content, quality_score, semantic_meta, embedding | 分块检索单元 |
| BusinessTerm | business_terms | name, type, definition, concept_id, related_fields, status | AI/人工业务术语 |
| MetricDefinition | metric_definitions | name, formula, caliber, concept_id, bound_table_refs, status | 指标口径 |
| DataLineage | data_lineage | source_table, target_table, transform_logic, layer | 表间血缘 |
| SemanticRelation | semantic_relations | relation_type, source/target ref, concept_id, join_key | 轻量语义关系图 |
| PipelineRun | pipeline_runs | knowledge_base_id, steps, status | 语义提取流水线状态 |
| PipelineConfig | pipeline_configs | chunk_strategy, chunk_size, dedup_threshold | 知识库流水线配置 |
| BusinessDomainKnowledgeBase | business_domain_knowledge_bases | domain_id, knowledge_base_id | 域↔知识库 |
| TableKnowledgeBase | table_knowledge_bases | table_id, knowledge_base_id | 表↔知识库 |
| TableKnowledgeEntry | table_knowledge_entries | table_id, knowledge_entry_id | 表↔条目（由 codebase_analyzer 自动创建） |
| LlmConnection | llm_connections | vendor_id, base_url, api_key, provider, model_id | 自定义大模型接入 |
| KnowledgeGitSource | knowledge_git_sources | provider, owner, repo, branch, path_prefix, token, cron_expression | Git 同步源 |

## 9. API 分组

### 连接与分析
- `POST /api/connect` — 测试连接 + 获取库表列表
- `POST /api/analyze/{table_name}` — 触发单表异步分析

### 数据源管理
- `GET/POST/PUT/DELETE /api/datasources` — CRUD
- `POST /api/datasources/test` — 连接测试
- `GET /api/datasources/{id}/catalog` — 数据源目录
- `GET /api/datasources/{id}/databases/{db}/catalog` — 数据库目录
- `POST /api/datasources/{id}/analyze/table/{table_name}` — 按表分析
- `POST /api/datasources/{id}/analyze/database/{database_name}` — 按库分析

### 表详情
- `GET /api/tables` — 表列表
- `GET /api/table/{table_id}` — 表详情聚合

### Copilot
- `POST /api/ask` — 问答
- `POST /api/ask/stream` — SSE 流式问答

### 业务域
- `GET/POST/DELETE /api/business-domains` — CRUD
- `GET /api/business-domains/{id}` — 域详情
- `GET /api/business-domains/options` — 下拉选项

### 知识库
- `CRUD /api/knowledge-bases` — 知识库管理
- `CRUD /api/knowledge-bases/{id}/entries` — 条目管理
- `POST /api/knowledge-bases/{id}/upload` — 文件上传（触发文档流水线）
- `GET /api/knowledge-bases/{id}/documents` — 文档列表与分块
- `POST /api/knowledge-bases/{id}/git-sources` — Git 同步源
- `POST /api/knowledge-bases/{id}/git-sources/{sid}/sync` — 手动同步
- `POST /api/knowledge-bases/{id}/analyze-codebase` — 代码库分析
- `GET/POST/PUT/DELETE /api/knowledge-bases/{id}/terms` — 业务术语
- `GET/POST/PUT/DELETE /api/knowledge-bases/{id}/metrics` — 指标口径
- `GET /api/knowledge-bases/{id}/lineage` — 数据血缘
- `GET /api/knowledge-bases/{id}/semantic-stats` — 语义流水线统计
- `POST /api/knowledge-bases/{id}/run-semantic-pipeline` — 触发语义提取

### LLM & 诊断
- `GET/POST /api/llm-settings` — 大模型配置
- `GET /api/diagnostics` — 系统诊断

## 10. 前端路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | 首页 | 业务域列表 |
| `/copilot` | Copilot 对话 | ChatBI 助手 |
| `/copilot/result` | Copilot 结果 | 历史对话结果 |
| `/datasources` | 数据源管理 | 列表+增删改 |
| `/datasources/[id]` | 数据源目录 | 库表浏览+分析触发 |
| `/datasources/[id]/database/[db]` | 数据库目录 | 库级别分析 |
| `/table/[id]` | 表详情 | 列信息+摘要 |
| `/business-domains/[id]` | 业务域详情 | 描述+库表选择 |
| `/knowledge-bases` | 知识库列表 | 管理入口 |
| `/knowledge-bases/[id]` | 知识库详情 | 导入源（语义清洗）+ 证据包登记 + `#modeling` 建模与质量（流水线 / 五层结果 / 质量与隔离，见 [ONTOLOGY_LAYER_UI_OPTIMIZATION §5.3.1](./ONTOLOGY_LAYER_UI_OPTIMIZATION.md)） |
| `/settings` | 设置 | LLM偏好 |

## 11. 现有限制与风险

| 风险项 | 等级 | 说明 |
|--------|------|------|
| 密码明文存储 | 高 | `DataSource.password` 明文存于 DB |
| 异步任务非队列化 | 中 | 进程内线程/协程，不适合高并发 |
| XSS 风险 | 中 | 前端存在 `dangerouslySetInnerHTML` 渲染点 |
| SQL 校验覆盖 | 低 | 复杂方言可能误伤或漏过，需逐步调参 |
| 向量维度锁死 | 低 | 固定 1536 维，换模型需迁移 |

## 12. 推荐演进路线

**P0：** 数据源凭据加密 / 异步任务队列化 / 线上 routing fallback 率观测

**P1：** semantic_relations 可视化编辑 / concept_id 跨域手动对齐 UI

**P2：** 多用户与权限体系 / 2-hop 语义图扩展

---

## 13. 相关专题文档

| 文档 | 内容 |
|------|------|
| [企业语义层与域内自治实践](./企业语义层与域内自治实践.md) | 理念、存储、联邦治理 |
| [本体建模：企业数据来源与自动化抽取](./ONTOLOGY_ENTERPRISE_DATA_SOURCES.md) | 本体要素全景、企业数据源映射矩阵、LLM 自动抽取流水线 |
| [COPILOT_ROUTING_OPTIMIZATION](./COPILOT_ROUTING_OPTIMIZATION.md) | 路由 backlog、配置项、trace |
| [SEMANTIC_LAYER_OPTIMIZATION_BACKLOG](./SEMANTIC_LAYER_OPTIMIZATION_BACKLOG.md) | 语义层能力状态 |
| [本体三层架构与 UI 优化方案](./ONTOLOGY_LAYER_UI_OPTIMIZATION.md) | 企业数据分类、导入/清洗/展示层设计、UI 线框、演进优先级 |

---

*最后更新：2026-05-26，反映知识库语义结构化（Phase 1~3）、Copilot 多信号路由与 semantic_relations 关系图。*
