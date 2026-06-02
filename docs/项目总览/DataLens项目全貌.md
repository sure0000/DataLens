# DataLens 项目全貌

> 最后更新：2026-06-02，反映 OWL/RDF 本体引擎、9 步抽取流水线、SHACL 校验写入、OWL 2 RL 推理、Copilot 本体路由等最新状态。

---

## AI 阅读指南

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
| 表理解 | Schema提取 + Profiling + LLM融合 → 列语义 + 表摘要 |
| RAG | 检索增强生成：向量检索历史语义和知识条目，注入 LLM 上下文提升 SQL 质量 |
| Copilot | 面向自然语言问答的 ChatBI 助手页面，支持生成 SQL + 只读执行 + 结果预览 |
| 业务域 | 用户定义的业务范畴（如"交易域""用户域"），可绑定库表和知识库 |
| 知识库 | 可检索的业务文档集合；支持 Markdown 条目、文档流水线分块、Git/API 同步 |
| 语义角色 (semantic_role) | 知识条目的业务分类：如 `business_metric`、`join_guide`、`column_glossary` 等 |
| 语义关系 (semantic_relations) | 术语/指标/表/概念之间的可遍历边，供 Copilot 图扩展路由 |
| concept_id | 企业薄层统一概念标识（如 `metric.gmv`），支持跨域别名对齐 |
| 业务术语 / 指标口径 | AI 从知识库提取并经审核的结构化资产（`business_terms`、`metric_definitions`） |
| TBox | 本体模式层 — 定义类、属性、公理、约束（OWL 中的 schema） |
| ABox | 本体实例层 — 具体的实体三元组（OWL 中的 instance data） |
| Named Graph | RDF 数据集中的命名子图，按知识库/域隔离，如 `graph/kb/1` |
| SHACL | Shapes Constraint Language — 用于验证 RDF 数据形状的 W3C 标准 |
| OWL 2 RL | OWL 2 规则语言子集，支持通过规则推导新三元组（传递闭包、对称闭包等） |
| RawTriple | 未清洗的原始三元组，经 9 阶段清洗管道处理后入图 |

---

## 2. 项目定义

**一句话定义：** DataLens 是一个「数据表智能理解 + 自然语言转 SQL + 只读执行预览 + OWL 本体知识图谱」的轻量分析系统。

**核心痛点：** 陌生表字段含义不明 / 不清楚表能分析什么 / 写 SQL 需频繁翻文档 / 业务术语口径分散在文档中缺乏统一建模。

**目标用户：** 数据分析师 / 数仓开发 / 需要接手陌生数据表的业务分析角色。

---

## 3. 功能边界

### In Scope

- 13 种数据源接入：MySQL / MariaDB / Doris / StarRocks / PostgreSQL / Greenplum / SQL Server / SQLite / ClickHouse / Trino / Hive
- 数据源 CRUD、连接测试、库表目录浏览
- 异步表分析：Schema 提取 → Profiling → LLM 列语义 → LLM 表摘要 → 向量持久化
- 表详情页：字段语义、质量指标、表五段式摘要、分析场景推荐
- 业务域管理：创建域、维护描述、选择关联库表、绑定知识库
- 知识库管理：手动条目、文件上传、Git 仓库同步（GitHub/GitLab）、API 源（Notion/飞书等）、代码库分析
- **文档流水线**：extract → clean → chunk → embed → 语义结构化（`semantic_meta`）→ 索引
- **语义提取流水线**：术语 / 指标口径 / 数据血缘 LLM 提取 + `semantic_relations` 关系图同步
- Copilot ChatBI：自然语言 → 多信号表路由 → SQL 生成 → 只读执行 → 结果预览（SSE 流式）
- SQL 安全护栏：sqlglot AST 只读校验 + 前缀白名单双重保护
- LLM 无 Key 兜底：未配置 API Key 时用规则和本地向量提供基本链路可用性
- 大模型多厂商接入：DeepSeek / OpenAI / 自定义兼容端点
- **OWL/RDF 本体引擎**：Apache Jena Fuseki 三元组存储、SPARQL 查询与推理、OWL 2 RL 增量推理
- **本体建模与清洗**：9 步抽取编排、9 阶段三元组清洗管道、SHACL 校验、隔离区、五层结果分页 API
- **业务域语义资产浏览**：按侧栏当前业务域聚合绑定知识库的已入图五层资产
- **SHACL 校验写入**：三元组写入前强制校验，通过入 production graph，失败入 quarantine
- **Copilot 本体路由**：OntologyRouter（SPARQL 概念/表路由）、混合路由（substring + embedding + keyword）
- **五维质量评估**：完整度、准确度、一致性、时效性、权威性五维 DQV 评估
- **KGE 知识图谱补全**：基于知识图谱嵌入的缺失关系发现
- **版本与演化管理**：实体版本号、变更说明、弃用标记
- **断言生命周期**：draft → pending_review → approved 状态流转

### Out of Scope

- 完整企业级数据血缘与治理平台（已有轻量 `data_lineage` + `semantic_relations`）
- 复杂权限 / 多租户 / 审计合规
- 团队协作工作流（审批、评审、共享空间）

---

## 4. 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python + FastAPI + SQLAlchemy (async) |
| 数据库 | PostgreSQL + pgvector 扩展（向量检索） |
| 三元组存储 | Apache Jena Fuseki（推荐）/ 本地 Trig 文件（调试回退） |
| 连接器 | PyMySQL / psycopg2 / clickhouse-driver / trino / pyodbc 等 |
| LLM | DeepSeek（主）/ OpenAI（备）/ 自定义端点 |
| Embedding | text-embedding-3-small (1536维)，无 Key 时本地确定性向量兜底 |
| 本体校验 | pyshacl + rdflib |
| 推理 | 自研 OWL 2 RL 规则引擎（rdflib） |
| 实体消歧 | Sentence-BERT (paraphrase-multilingual-MiniLM-L12-v2) |
| SQL 护栏 | sqlglot AST 解析，方言随 source_type 映射 |
| 前端 | Next.js App Router + TypeScript + Tailwind CSS |

---

## 5. 代码结构

```
├── backend/
│   ├── main.py                       # FastAPI 应用入口，路由注册
│   ├── config.py                     # 全局配置（Pydantic Settings）
│   ├── database.py                   # DB session/engine，建表
│   ├── models.py                     # ORM 模型（30+ 表）
│   ├── security.py                   # Bearer Token 鉴权
│   │
│   ├── ontology/                     # 本体定义（TBox + SHACL 形状）
│   │   ├── __init__.py               # 命名空间与 IRI 构造辅助函数
│   │   ├── tbox/core.ttl             # 核心 TBox — 类层级、属性、公理
│   │   ├── tbox/enterprise.ttl       # 企业层概念体系
│   │   ├── tbox/governance.ttl       # 治理元数据
│   │   └── shacl/                    # 11 个 SHACL 形状文件
│   │
│   ├── routers/
│   │   ├── ontology.py               # 本体层 API（SPARQL、三元组、建模流水线、五层视图）
│   │   ├── domain_ontology.py        # 业务域语义资产浏览 API
│   │   ├── copilot.py                # 问答 + SSE 流式
│   │   ├── datasources.py            # 数据源 CRUD
│   │   ├── tables.py                 # 表详情聚合
│   │   ├── analyze.py                # 异步分析入口
│   │   ├── connect.py                # 连接测试
│   │   ├── business_domains.py       # 业务域 CRUD
│   │   ├── knowledge_bases.py        # 知识库管理
│   │   ├── knowledge_git_sources.py  # Git 同步源管理
│   │   ├── knowledge_api_sources.py  # API 源管理
│   │   ├── knowledge_database_imports.py # 数据库导入
│   │   ├── knowledge_ingestion.py    # 知识摄入
│   │   ├── knowledge_semantic.py     # 语义提取
│   │   ├── llm_settings.py           # LLM 配置
│   │   └── diagnostics.py            # 诊断接口
│   │
│   ├── services/
│   │   ├── ontology/                 # 本体操作层（核心模块）
│   │   │   ├── writer.py             # 统一写入接口（clean → SHACL → production）
│   │   │   ├── reader.py             # SPARQL 读取（含推理图）
│   │   │   ├── reasoner.py           # OWL 2 RL 推理引擎
│   │   │   ├── validator.py          # SHACL 校验
│   │   │   ├── quarantine.py         # 隔离区管理
│   │   │   ├── modeling_layers.py    # 五层建模结果查询
│   │   │   ├── modeling_status.py    # 建模状态聚合
│   │   │   ├── domain_aggregation.py # 业务域跨 KB 数据聚合
│   │   │   ├── views.py              # SPARQL 只读视图
│   │   │   ├── hierarchy_view.py     # 层级树视图
│   │   │   ├── provenance.py         # 实体溯源
│   │   │   ├── governance.py         # 五维质量评估
│   │   │   ├── assertion_lifecycle.py # 断言生命周期
│   │   │   ├── copilot_validation.py  # Copilot 验证
│   │   │   ├── relation_predicates.py # 关系谓词枚举
│   │   │   ├── entity_embedder.py     # 实体嵌入
│   │   │   ├── kge_completer.py       # KGE 知识图谱补全
│   │   │   └── quarantine_templates.py # 隔离区修复模板
│   │   │
│   │   ├── extraction/               # LLM 知识提取层
│   │   │   ├── orchestrator.py       # 9 步提取流水线编排
│   │   │   ├── term_extractor.py     # 术语提取
│   │   │   ├── metric_extractor.py   # 指标提取
│   │   │   ├── dimension_extractor.py # 维度提取
│   │   │   ├── relation_extractor.py # 关系提取
│   │   │   ├── rule_extractor.py     # 业务规则提取
│   │   │   ├── hierarchy_builder.py  # 层级构建
│   │   │   ├── lineage_extractor.py  # 血缘提取
│   │   │   ├── join_extractor.py     # JOIN 提取
│   │   │   ├── domain_term_extractor.py # 领域术语提取
│   │   │   ├── step_cache.py         # 步骤缓存与断点续跑
│   │   │   ├── chunk_progress.py     # 分块进度回调
│   │   │   ├── pipeline_status.py    # 流水线状态管理
│   │   │   ├── git_entry_chunks.py   # Git 条目转 LLM 输入
│   │   │   └── code_patterns/        # 代码解析器（SQL/YAML/DBT/Python/Spark）
│   │   │
│   │   ├── copilot/                  # Copilot 查询引擎
│   │   │   ├── pipeline.py           # 查询流水线编排
│   │   │   ├── router.py             # OntologyRouter（SPARQL + 混合路由）
│   │   │   ├── ontology_match.py     # 本体知识匹配与映射描述生成
│   │   │   ├── ontology_concept_match.py # 混合概念路由（substring + embedding + keyword）
│   │   │   └── context.py            # 上下文组装
│   │   │
│   │   ├── triple_store/             # 三元组存储层
│   │   │   └── store.py              # Fuseki SPARQL 客户端 / 本地 Trig 存储
│   │   │
│   │   ├── ontology_triple_cleaner.py # 9 阶段三元组清洗管道
│   │   ├── ontology_entity_linker.py  # 实体链接（表名→IRI）
│   │   ├── ontology_entity_embedder.py # 实体嵌入消歧
│   │   ├── ontology_store.py          # 存储底层操作
│   │   ├── ontology_loader.py         # 本体初始化
│   │   ├── ontology_population.py     # 本体填充
│   │   ├── ontology_rdf_browser.py    # RDF 浏览视图
│   │   ├── ontology_validation.py     # 校验入口
│   │   ├── ontology_reasoning.py      # 推理入口
│   │   ├── ontology_sync_service.py   # 同步服务
│   │   ├── ontology_entity_linker.py  # 实体链接解析
│   │   │
│   │   ├── routing_bundle.py          # 共享 KB 检索 bundle
│   │   ├── routing/                   # metric / lineage / graph / domain 路由
│   │   ├── context_builder.py         # Copilot 上下文：表路由、知识聚合
│   │   ├── knowledge_pipeline_service.py # 文档 clean/chunk/embed/structuring
│   │   ├── chunk_semantic_structuring.py # chunk semantic_meta
│   │   ├── semantic_extraction.py     # 术语/指标/血缘 LLM 提取
│   │   ├── semantic_relation_sync.py  # semantic_relations 同步
│   │   ├── semantic_grounding.py      # grounding 解析、role 推断
│   │   ├── retrieval_service.py       # Entry + Chunk 混合检索 (RRF)
│   │   ├── schema_extractor.py        # Schema/样本/只读 SQL 执行
│   │   ├── profiler.py                # 列统计画像
│   │   ├── llm_service.py             # 列语义、表摘要、SQL 生成
│   │   ├── rag_service.py             # 问答主流程
│   │   ├── embedding_service.py       # 向量服务
│   │   ├── codebase_analyzer.py       # 代码库分析
│   │   ├── sql_ast_guard.py           # sqlglot 只读校验
│   │   ├── git_knowledge_sync.py      # Git 同步
│   │   └── git_schedule.py            # Git 定时调度
│   │
│   ├── prompts/                       # LLM prompt 模板
│   │   ├── term_extraction_system.txt # 术语提取系统提示
│   │   ├── metric_extraction_system.txt # 指标提取系统提示
│   │   ├── dimension_extraction_system.txt # 维度提取系统提示
│   │   ├── relation_extraction_system.txt # 关系提取系统提示
│   │   ├── rule_extraction_system.txt # 规则提取系统提示
│   │   ├── hierarchy_extraction_system.txt # 层级提取系统提示
│   │   ├── lineage_extraction_system.txt # 血缘提取系统提示
│   │   ├── join_extraction_system.txt # JOIN 提取系统提示
│   │   ├── sql_generation_system.txt  # SQL 生成系统提示
│   │   ├── sql_repair_system.txt      # SQL 修复系统提示
│   │   ├── chunk_semantic_structuring_system.txt # 分块语义结构化
│   │   └── ...
│   │
│   └── tests/                         # pytest
│
├── frontend/
│   ├── app/                           # Next.js App Router
│   │   ├── copilot/page.tsx           # Copilot 对话
│   │   ├── ontology/page.tsx          # 语义资产浏览
│   │   ├── datasources/               # 数据源管理
│   │   ├── table/[id]/page.tsx        # 表详情
│   │   ├── business-domains/          # 业务域管理
│   │   ├── knowledge-bases/           # 知识库管理 + 建模与质量
│   │   └── settings/page.tsx          # LLM 偏好
│   ├── components/
│   │   ├── ontology/                  # DomainFiveLayerBrowse、ConceptHierarchyPanel 等
│   │   ├── CopilotChat.tsx            # Copilot 对话容器
│   │   ├── CopilotExecutionTrace.tsx  # 执行链路可视化
│   │   └── ...
│   └── lib/
│       ├── api.ts                     # 前端 API 封装
│       └── copilotStream.ts           # SSE 流处理
```

---

## 6. 核心数据流

### 6.1 知识库文档流水线

```
文件 / API / Git 同步
  │
  ▼
knowledge_pipeline_service.run_pipeline()
  ├── clean_text()              # 去噪声、标点归一化
  ├── chunk_text()              # 按标题 / 固定长度分块
  ├── embed → DocumentChunk     # 向量 + tsvector 全文索引
  └── structure_document_chunks()
        ├── semantic_meta: semantic_role + grounding + join_edges
        ├── KnowledgeEntry.semantic_role 回写
        ├── data_lineage 同步
        └── MetricDefinition.bound_table_refs 回填
```

### 6.2 表理解生成

```
COLUMN_NAME ─┐
DATA_TYPE  ─┤
COLUMN_TYPE─┤
sample_data─┼→ profile_column() → profiles[]
            │   ├── null_ratio                     ▼
            │   ├── distinct_count           ColumnMeta.semantic_desc
            │   ├── top_values               ColumnMeta.semantic_type
            │   ├── quality_metrics           ColumnMeta.is_usable
            │   │   ├── risk_level
            │   │   ├── enum {kind, values}
            │   │   ├── distribution {p25,p50,p75}
            │   │   ├── zero_ratio / outlier_count
            │   │   └── aggregation_hint
            │   └── analyze_column() ← domain_contexts
            │                              ← domain_knowledge_entries
            ▼
      rows_for_summary[] → analyze_table() → TableSummary (5章节)
                           ↑ business_context
```

### 6.3 Copilot 问答链路

```
用户问题 + 可选 table_id / business_domain_id
  │
  ├→ guardrail_for_question()
  ├→ classify_question_intent()
  │
  ├→ [若 general_qa] → answer_general_question()
  │
  └→ [若 sql_query]
      ├→ build_routing_search_bundle()   # 单次 embed + 统一 KB hybrid 检索
      │
      ├→ collect_knowledge_context_text()
      │     ├→ 固定全文: TableKnowledgeEntry
      │     └→ 混合检索: Entry + DocumentChunk（RRF）
      │
      ├→ run_ontology_match()            # 本体知识匹配
      │     ├→ OntologyRouter.full_route()
      │     │   ├→ hybrid_route_concepts()  # substring + embedding + keyword
      │     │   ├→ route_tables()           # SPARQL: concept → table
      │     │   └→ expand_lineage()         # transformsFrom / joinableWith 1-hop
      │     └→ 组装 mapping / context_text / trace
      │
      ├→ build_priority_context()        # 多信号表路由
      │     ├→ 知识 grounding / 表名匹配 / 显式链接
      │     ├→ 表摘要向量直搜 + RRF 融合
      │     ├→ 指标/术语路由
      │     ├→ 列向量维表扩表
      │     ├→ 血缘 + semantic_relations 1-hop
      │     └→ 梯度 fallback + routing_trace
      │
      ├→ generate_sql() → AST 校验 → execute_readonly_sql()
      └→ sql_review（域外表检测，review 标签）
```

### 6.4 本体建模数据流（详见 §7）

```
文档/代码 → LLM 语义提取 → RawTriple[] → 9 阶段清洗管道 → SHACL 校验
                                              │
                                              ├→ 通过 → production named graph
                                              └→ 失败 → quarantine named graph
                                                          │
                                              OWL 2 RL 推理 → inferred graph
                                                          │
                                              PG 缓存刷新 (全文索引/向量)
```

---

## 7. 本体建模模块（详细逻辑）

### 7.1 架构总览

本体模块是 DataLens 的语义中枢，采用 **TBox/ABox 严格分离** 的四层架构：

```
Layer 0: Enterprise Ontology (企业本体)
  Named Graph: graph/enterprise
  跨所有业务域共享的顶层概念、属性、公理

Layer 1: Domain Ontology (领域本体)
  Named Graph: graph/domain/{id}
  每个业务域的 TBox 扩展 — 领域特定概念、SHACL 形状

Layer 2: Application Ontology (知识库本体)
  Named Graph: graph/kb/{id}        ← ABox (实例)
  Named Graph: graph/quarantine/{id} ← 隔离区
  知识库级别的实例数据 — 术语、指标、血缘、物理表映射

Layer 3: Inference Graph (推理闭包)
  Named Graph: graph/inferred/{scope}
  OWL 2 RL 推理机生成的推导三元组，每次写入后自动刷新
```

**核心原则：**
- **本体即中枢** — RDF 知识图谱是语义数据的唯一真相源，PostgreSQL 退化为性能缓存
- **SHACL 守门** — 所有写操作经 SHACL 校验，通过→生产图，失败→隔离区
- **OWL 2 RL 推理** — 查询管线内置 subclass、property path、transitive 推理
- **事件驱动** — 文档导入 → LLM 提取 → 直接写 RDF → SHACL → 推理 → PG 缓存刷新

### 7.2 IRI 命名空间

所有 IRI 基于 `https://datalens.local/` 前缀，由 `backend/ontology/__init__.py` 统一管理：

| 命名空间 | 前缀 | 示例 |
|---------|------|------|
| 本体命名空间 | `https://datalens.local/ontology/` | `dl:BusinessTerm` |
| 数据命名空间 | `https://datalens.local/data/` | 表 IRI: `data/table/{id}` |
| 图命名空间 | `https://datalens.local/graph/` | KB 图: `graph/kb/{id}` |

**核心 IRI 构造函数：**
- `term_iri(domain_id, slug)` → `data/domain/{id}/term/{slug}`
- `metric_iri(domain_id, slug)` → `data/domain/{id}/metric/{slug}`
- `dimension_iri(domain_id, slug)` → `data/domain/{id}/dimension/{slug}`
- `rule_iri(domain_id, slug)` → `data/domain/{id}/rule/{slug}`
- `table_iri(table_id)` → `data/table/{id}`
- `kb_graph_iri(kb_id)` → `graph/kb/{id}`
- `quarantine_graph_iri(kb_id)` → `graph/quarantine/{id}`

### 7.3 TBox 本体模型（类层级）

TBox 定义在 `backend/ontology/tbox/core.ttl`（核心）、`enterprise.ttl`（企业层）、`governance.ttl`（治理层）。

```
owl:Thing
├── dl:BusinessConcept          (业务概念 — 所有业务语义的基类)
│   ├── rdfs:subClassOf skos:Concept
│   │
│   ├── dl:BusinessTerm         (业务术语)
│   │   ├── dl:mapsToColumn  → dl:PhysicalColumn
│   │   ├── dl:dependsOn     → dl:BusinessTerm
│   │   └── dl:groundedBy    → dl:DocumentChunk
│   │
│   ├── dl:Metric               (指标)
│   │   ├── dl:formula           xsd:string
│   │   ├── dl:caliber           xsd:string
│   │   ├── dl:computedFromTable → dl:PhysicalTable
│   │   ├── dl:derivedFrom       → dl:Metric
│   │   └── dl:aggregatesOver    → dl:Dimension
│   │
│   ├── dl:Dimension            (维度)
│   │   └── dl:dimensionType     xsd:string {time|geo|category|hierarchy}
│   │
│   └── dl:BusinessRule         (业务规则)
│       ├── dl:ruleExpression    xsd:string
│       └── dl:ruleType          xsd:string {shacl_constraint|owl_axiom|swrl_rule|business_rule}
│
├── dl:DataAsset                (数据资产)
│   ├── dl:PhysicalTable        (物理表)
│   │   ├── dl:platformId        xsd:integer
│   │   ├── dl:businessSummary   xsd:string
│   │   ├── dl:rowCount          xsd:integer
│   │   ├── dl:sensitivityLevel  xsd:string
│   │   ├── schema:isPartOf      → dl:DataSource
│   │   ├── dl:hasMeasure        → dl:Metric
│   │   ├── dl:hasDimension      → dl:Dimension
│   │   ├── dl:joinableWith      → dl:PhysicalTable (Symmetric)
│   │   └── dl:transformsFrom    ← dl:PhysicalTable (Transitive)
│   │
│   ├── dl:PhysicalColumn       (物理列)
│   │   ├── schema:isPartOf      → dl:PhysicalTable
│   │   ├── dl:semanticType      xsd:string
│   │   ├── dl:dataType          xsd:string
│   │   └── dl:nullable          xsd:boolean
│   │
│   └── dl:View                 (视图/逻辑表)
│
├── dl:DataSource               (数据源)
├── dl:KnowledgeBase            (知识库)
├── dl:Document                 (文档)
├── dl:DocumentChunk            (文档片段)
├── dl:LineageAssertion         (血缘断言)
├── dl:JoinRelation             (JOIN 关系)
└── dl:QuarantinedAssertion     (隔离区断言)
```

**类互斥公理：**
```turtle
dl:BusinessTerm  owl:disjointWith  dl:Metric .
dl:BusinessTerm  owl:disjointWith  dl:Dimension .
dl:Metric        owl:disjointWith  dl:Dimension .
dl:BusinessConcept  owl:disjointWith  dl:DataAsset .
dl:PhysicalTable  owl:disjointWith  dl:BusinessConcept .
```

**属性特性：**
- `dl:joinableWith` — owl:SymmetricProperty（两表可 JOIN，对称）
- `dl:transformsFrom` — owl:TransitiveProperty（血缘传递）
- `dl:derivedFrom` — owl:TransitiveProperty（指标派生传递）
- `dl:formula` — owl:FunctionalProperty（一个指标一个公式）
- `dl:platformId` — owl:FunctionalProperty（唯一平台 ID）
- `dl:computedFromTable` — owl:FunctionalProperty（唯一数据来源表）

**属性链公理：**
```turtle
# 指标从下游表取数，该表血缘来自上游 → 指标间接依赖上游
[ owl:propertyChainAxiom (dl:computedFromTable dl:transformsFrom) ] .
```

### 7.4 本体清洗五层模型

所有写入知识图谱的 ABox 数据经过清洗管线时，按五个语义层分类和校验：

| 层级 | 名称 | 本体类 | 说明 |
|------|------|--------|------|
| Layer 1 | 词汇层 (Vocabulary) | `dl:BusinessTerm` | 业务术语定义 — "叫什么、是什么意思" |
| Layer 2 | 规则层 (Rule) | `dl:Metric`, `dl:BusinessRule` | 指标口径与业务规则 — "如何计算、如何判断" |
| Layer 3 | 实体概念层 (Entity/Concept) | `dl:BusinessTerm`, `dl:Metric`, `dl:Dimension` | 带层级关系的语义实体 |
| Layer 4 | 关系层 (Relation) | ObjectProperty edges | 概念间语义边 — dependsOn, derivedFrom, relatedTo |
| Layer 5 | 属性层 (Attribute) | DatatypeProperty values | 字面量属性 — formula, caliber, confidence, label |

**查询逻辑**（`modeling_layers.py`）：
- **词汇层**：SPARQL 查询 `rdf:type dl:BusinessTerm` 的 DISTINCT 实体
- **规则层**：UNION 查询 `rdf:type dl:BusinessRule` + `rdf:type dl:Metric`
- **实体概念层**：查询全部 `dl:BusinessConcept` 子类实例，附带 `skos:broader/narrower` 邻居聚合
- **关系层**：查询 `isIRI(?o)` 且谓语在关系白名单中的三元组
- **属性层**：查询 `isLiteral(?o)` 且排除 `rdf:type` 和 `approvalStatus` 的字面量三元组，支持按物理表/列维度筛选

### 7.5 9 步提取流水线（ExtractionOrchestrator）

编排器 `ExtractionOrchestrator.run()` 协调从文档到 RDF 三元组的完整提取流程。

**输入来源：**
- `DocumentChunk`（文档分块，quality_score ≥ 0.4）
- `KnowledgeEntry`（Git 代码文件，经 `git_entries_as_llm_chunks` 转换）

**流水线步骤与执行策略：**

```
阶段 1（并行执行 — 有文档分块时）:
  ├── Step 1: term_extraction    # 术语提取 (term_extractor.py)
  ├── Step 2: metric_extraction  # 指标口径提取 (metric_extractor.py)
  ├── Step 3: dimension_extraction # 维度提取 (dimension_extractor.py)
  └── Step 4: rule_extraction    # 业务规则提取 (rule_extractor.py)

阶段 2（并行执行 — 有 Git 条目时）:
  ├── Step 5: data_lineage       # 血缘提取 (lineage_extractor.py)
  ├── Step 6: join_extraction    # JOIN 提取 (join_extractor.py)
  └── Step 7: domain_term_extraction # 领域术语提取 (domain_term_extractor.py)

阶段 3（串行 — 依赖阶段1产物，有概念实体时）:
  ├── Step 8: relation_extraction # 关系提取 (relation_extractor.py)
  └── Step 9: hierarchy_building  # 层级构建 (hierarchy_builder.py)

最后:
  └── OntologyWriter.write_many() → 9 阶段清洗 → SHACL → production/quarantine
```

**关键设计点：**
- **本体上下文注入**：`_build_ontology_injection_context()` 在每次 LLM 调用前查询现有知识图谱中的已知实体和关系类型，注入到提示词中，使 LLM 能够复用已有 IRI 而非创建重复实体
- **断点续跑**：通过 `step_cache.save_step_triples()` 在每个步骤完成后缓存中间三元组，失败重跑时 `_try_resume_step()` 从缓存恢复已完成的步骤
- **流水线超时**：`asyncio.wait_for` 包裹整个编排，超时自动记录当前步骤并标记失败
- **步骤进度**：每个步骤通过 `ChunkProgressCallback` 实时报告 `done/total` 进度并持久化到 `PipelineRun.steps`
- **置信度门控**：`auto_approve_confidence`（默认 80）以上自动 `approved`，以下 `draft`
- **数据库 Schema 同步**：除语义提取外，`run_database_schema_pipeline()` 将已分析物理表同步入本体图

#### 7.5.1 术语提取器（term_extractor.py）

**逻辑流程：**
1. 遍历每个文档分块，将 `ontology_context + content` 传给 LLM
2. LLM 按 `term_extraction_system.txt` 提示词返回 JSON：`{"terms": [{name, definition, type, confidence, synonyms, parent_concept, related_fields}]}`
3. 对每个提取出的术语：
   - 通过 `concept_slug(name, "term")` 生成唯一 slug
   - 构造 `term_iri(kb_id, slug)` IRI
   - 生成三元组：`rdf:type dl:BusinessTerm`、`skos:prefLabel`、`skos:definition`、`dl:termType`、`dl:approvalStatus`、`dl:confidence`、`dl:belongsToDomain`
   - 处理 synonyms → `skos:altLabel`
   - 处理 parent_concept → `skos:broader`
   - 处理 related_fields → `dl:mapsToColumn`
   - 附加 `dl:groundedBy` → 来源 chunk IRI

#### 7.5.2 指标提取器（metric_extractor.py）

**逻辑流程：**
1. 遍历每个文档分块，LLM 提取指标
2. 对于每个指标：
   - 从 chunk.semantic_meta.grounding.table_refs 获取绑定的表引用
   - 生成 `rdf:type dl:Metric`、`dl:formula`、`dl:caliber`（口径说明）
   - related_terms → `dl:dependsOn`
   - derived_from → `dl:derivedFrom`（指标派生链）
   - aggregates_over → `dl:aggregatesOver`（聚合维度）
   - bound_table_refs → `dl:computedFromTable`

#### 7.5.3 维度提取器（dimension_extractor.py）

**逻辑流程：**
1. 遍历分块，LLM 提取维度定义
2. 生成 `rdf:type dl:Dimension`、`dl:dimensionType`（time/geo/category/hierarchy）

#### 7.5.4 关系提取器（relation_extractor.py）

**逻辑流程：**
1. 接收阶段 1 产生的 `term_iris` 和 `metric_iris` 字典
2. 将已知概念名列表（最多 50 个）注入用户消息上下文
3. LLM 根据 `relation_extraction_system.txt` 识别关系：`dependsOn`, `related`, `derivedFrom`, `aggregatesOver`, `precedes`, `generalizes`, `usedBy`
4. 在 term_iris/metric_iris 中查找 source 和 target 的 IRI
5. 关系类型映射到 `dl:` 命名空间谓词 IRI

#### 7.5.5 层级构建器（hierarchy_builder.py）

**逻辑流程：**
1. 接收已提取的所有概念 IRI 及标签
2. LLM 分析概念间的层级关系
3. 生成 `skos:broader` / `skos:narrower` 三元组
4. 由推理器自动推导传递闭包

### 7.6 OntologyWriter — 统一写入接口

`OntologyWriter` 是所有语义数据写入本体图的唯一入口。每种写入方法遵循相同模式：

```
输入数据 → 构造 RawTriple[] → clean_triples() → SHACL 校验 → persist_clean_result()
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    ↓                               ↓
                                              通过 → insert_graph()          失败 → quarantine graph
                                              (production graph)
```

**写入方法：**

| 方法 | 输入 | 产出 |
|------|------|------|
| `write_term(kb_id, TermInput)` | name, definition, term_type, related_fields, confidence, chunk_id | dl:BusinessTerm 三元组 |
| `write_metric(kb_id, MetricInput)` | name, formula, caliber, bound_table_ids, derived_from | dl:Metric 三元组 |
| `write_dimension(kb_id, DimensionInput)` | name, dim_type, confidence | dl:Dimension 三元组 |
| `write_relation(RelationInput)` | subject_iri, predicate, object_iri | 关系三元组 |
| `write_lineage(LineageInput)` | source/target table, fields, layer, logic | dl:LineageAssertion 三元组 |
| `write_physical_table(kb_id, PhysicalTableInput)` | table_id, datasource_id, name, summary | dl:PhysicalTable 三元组 |
| `write_quality_report(kb_id, entity_iri, scores)` | 五维质量分 | DQV 质量报告三元组 |
| `write_domain_tbox(domain_id, subclasses, shapes)` | 域特有子类/SHACL | domain graph TBox 扩展 |
| `write_many(kb_id, triples[])` | 批量 RawTriple | 批量清洗写入 |

### 7.7 9 阶段三元组清洗管道（clean_triples）

`clean_triples()` 是写入 pipeline 的核心，位于 `backend/services/ontology_triple_cleaner.py`，依次执行 9 个阶段：

```
输入: RawTriple[]
  │
  ├── Stage 1: 语法规范化 (syntax_normalize)
  │   ├── Unicode NFKC 正规化
  │   ├── 去除空白
  │   ├── 过滤空 subject / predicate / object
  │   └── 置信度 clamp 到 [0, 100]
  │
  ├── Stage 2: 实体链接 (entity_link)
  │   ├── 针对表引用谓词（computedFromTable、joinableWith 等）
  │   ├── resolve_table_ref(): 表名 → table_iri
  │   │   ├── 精确匹配 → exact, conf=1.0
  │   │   ├── 关键词匹配 → keyword, conf=0.85
  │   │   └── 模糊匹配 → ambiguous（可配置隔离）
  │   └── 附加 dl:linkMethod / dl:linkConfidence 元数据
  │
  ├── Stage 2a: 实体嵌入消歧 (entity_disambiguate)
  │   ├── 对 NEW 实体的 label 与 existing_entities 做 Sentence-BERT 余弦相似度
  │   ├── 相似度 ≥ 0.85 → auto_link: 融合到已有实体 IRI
  │   ├── 0.60 ≤ 相似度 < 0.85 → arbitrate: 进隔离区等人工裁决
  │   └── < 0.60 → pass through: 作为新实体
  │
  ├── Stage 3: TBox 谓词检查 (tbox_check)
  │   ├── 精确匹配 _TBOX_PREDICATES 白名单（150+ 已知谓词）→ pass
  │   ├── 以 dl: 命名空间前缀开头 → pass（命名空间信任）
  │   ├── 否则 → 谓词嵌入语义匹配
  │   │   ├── Sentence-BERT 编码未知谓词标签 → 与已知谓词标签 cosine
  │   │   ├── 相似度 ≥ 0.85 → auto-map 到已知谓词 IRI
  │   │   ├── 0.60 ≤ 相似度 < 0.85 → 隔离 + top-3 建议
  │   │   └── < 0.60 → 隔离 (unknown_predicate)
  │
  ├── Stage 4a: 多源冲突检测与贝叶斯置信度融合 (conflict_resolve)
  │   ├── 分组 (subject, predicate, object)
  │   ├── 同一 (s,p,o) 多源 → 贝叶斯融合: fused_conf = 1 - ∏(1 - c_i/100)
  │   ├── 同一 (s,p) 不同 object → 冲突检测
  │   │   ├── 3+ 源: 多数投票 majority vote
  │   │   ├── 2 源: 高置信度胜出，低置信度隔离
  │   │   └── 按 (不同源数量, 最高置信度) 排序
  │   └── 胜出者贝叶斯融合，失败者进隔离区 (reason: conflict_detected)
  │
  ├── Stage 5: 去重 (deduplicate)
  │   ├── 标准三元组: (graph, s, p, o, is_uri) 去重
  │   ├── joinableWith: (a, b) 对称去重 → 统一为 (min, max)
  │   └── 保留首次出现的三元组
  │
  ├── Stage 7: 状态门控 (status_gate)
  │   ├── 计算每个 subject 的置信度
  │   ├── 置信度 ≥ ontology_min_confidence_auto_approve (默认 80) → "approved"
  │   └── 置信度 < 阈值 → "draft"
  │
  └── 输出: CleanResult { production: RawTriple[], quarantine: dict[], stats }
```

**设计要点：**
- 每个阶段的统计信息记录在 `stats` 字典中（`after_syntax`, `quarantine_link`, `quarantine_tbox`, `quarantine_conflict`, `production`）
- 隔离区条目统一带有 `reason`、`suggestedFix` 字段
- 谓词嵌入缓存：所有已知谓词的 Sentence-BERT 嵌入在模块初始化时一次性计算并缓存

### 7.8 SHACL 校验（validator.py）

`validate()` 函数执行 SHACL 校验，位于 `backend/services/ontology/validator.py`：

**输入：**
- `data`: rdflib Graph 或 Turtle 字符串
- `shapes`: 可选的形状文件名列表（不传则加载 `shacl/` 目录下全部 .ttl）
- `inference`: 推理模式（"none"/"rdfs"/"owlrl"/"both"）

**校验流程：**
1. 加载 SHACL 形状图：从 `backend/ontology/shacl/` 加载 11 个形状文件
2. 加载 TBox 本体图：从 `backend/ontology/tbox/` 加载作为校验上下文
3. 调用 `pyshacl.validate()` 执行校验
4. 返回 `{conforms, violations[], violation_count, report, skipped}`

**现有 SHACL 形状：**

| 形状文件 | 目标类 | 校验规则 |
|---------|--------|---------|
| `term.shacl.ttl` | dl:BusinessTerm | prefLabel≥1, definition≥1, belongsToDomain≥1 |
| `metric.shacl.ttl` | dl:Metric | prefLabel≥1, formula≥1, computedFromTable≥1 |
| `dimension.shacl.ttl` | dl:Dimension | prefLabel≥1, dimensionType∈枚举 |
| `hierarchy.shacl.ttl` | dl:BusinessConcept | broader无自环, 层级深度≤6 |
| `business_rule.shacl.ttl` | dl:BusinessRule | ruleExpression≥1, ruleType∈枚举 |
| `lineage.shacl.ttl` | dl:LineageAssertion | sourceField≥1 或 targetField≥1 |
| `join.shacl.ttl` | dl:JoinRelation | leftTable≥1, rightTable≥1, joinKey≥1 |
| `table.shacl.ttl` | dl:PhysicalTable | platformId≥1, belongsToDataSource≥1 |
| `cross_entity_integrity.shacl.ttl` | 跨实体 | 实体完整性约束 |
| `event.shacl.ttl` | dl:BusinessEvent | 事件约束 |
| `quality_report.shacl.ttl` | dl:QualityReport | 质量报告约束 |

### 7.9 persist_clean_result — 写入分发

清洗完成后，`persist_clean_result()` 将结果分写入生产图和隔离图：

```
CleanResult
  │
  ├── production triples
  │    ├── triples_to_ttl() 序列化为 Turtle
  │    ├── validate_ttl() SHACL 校验
  │    ├── 通过 → insert_graph(kb_graph_iri) 写入生产图
  │    └── 失败 → shacl_blocked=true, 不写入生产图
  │
  └── quarantine items
       ├── 每个隔离条目构造 QuarantinedAssertion 实例
       ├── 写入 dl:rejectReason、dl:rawTriple、dl:suggestedFix
       └── insert_graph(quarantine_graph_iri) 写入隔离图
```

### 7.10 隔离区管理（quarantine.py）

`QuarantineManager` 管理隔离区中的三元组：

- **list_items(kb_id)**：SPARQL 查询隔离图中所有 `QuarantinedAssertion`，解析 rawTriple JSON 为结构化数据
- **resolve(kb_id, item_idx, approved)**：
  - 批准（approved=true）：将 rawTriple 重新经过 `clean_triples() + persist_clean_result()` 入生产图
  - 拒绝（approved=false）：从隔离图 DELETE 该条目
- **修复模板**：`quarantine_templates.py` 提供按 reason 类型的自动修复策略（如将未知谓词映射到最佳候选、用已登记表名替换未解析引用等）

### 7.11 OWL 2 RL 推理引擎（reasoner.py）

`OntologyReasoner` 在每次 ABox 写入后触发增量推理，将推导的三元组写入 `graph/inferred/{scope}`。

**推理规则集（`_default_rules()`）：**

```
├── SubClassOfRule        # rdfs:subClassOf 层级闭包 + 类型传播
│   ├── ?a rdfs:subClassOf ?b ∧ ?b rdfs:subClassOf ?c → ?a rdfs:subClassOf ?c
│   └── ?x rdf:type ?a ∧ ?a rdfs:subClassOf ?b → ?x rdf:type ?b
│
├── SubPropertyOfRule     # rdfs:subPropertyOf 层级闭包 + 属性传播
│   └── ?x ?p ?y ∧ ?p rdfs:subPropertyOf ?q → ?x ?q ?y
│
├── EquivalentClassRule   # owl:equivalentClass 双向推导
│   └── ?x rdf:type ?a ∧ ?a owl:equivalentClass ?b → ?x rdf:type ?b
│
├── TransitivePropertyRule(derivedFrom)    # 指标派生链传递闭包
├── TransitivePropertyRule(transformsFrom) # 血缘传递闭包
├── TransitivePropertyRule(precedes)       # 顺承关系传递闭包
│
├── SymmetricPropertyRule(joinableWith)    # JOIN 对称闭包
├── SymmetricPropertyRule(exactMatch)      # 等价匹配对称闭包
│
├── InversePropertyRule(broader ↔ narrower)
├── InversePropertyRule(groundedBy ↔ asserts)
├── InversePropertyRule(computedFromTable ↔ usedBy)
│
└── SWRLStyleRule         # 自定义业务规则（body patterns → head）
```

**推理流程：**
1. 加载生产图 + 已有推理图 → 合并为工作图
2. 迭代执行所有推理规则（最多 `max_iterations=3` 轮）
3. 每轮统计每个规则的新推导三元组数
4. 无新三元组时达到不动点（fixpoint），提前终止
5. 只将**不在生产图中的新推导三元组**写入推理图
6. 先 `delete_graph` 清空旧推理图，再 `insert_graph` 写入新结果

### 7.12 OntologyReader — SPARQL 读取

`OntologyReader` 提供支持推理图的 SPARQL 查询封装：

- **list_terms(kb_id, include_inferred)**：查询 `dl:BusinessTerm` 实例
- **list_metrics(kb_id, include_inferred)**：查询 `dl:Metric` 实例
- **list_dimensions(kb_id, include_inferred)**：查询 `dl:Dimension` 实例
- **list_physical_tables(kb_id)**：查询 `dl:PhysicalTable` 实例
- **get_concept_neighborhood(concept_iri, kb_id, radius=1)**：1-hop 图邻域，返回 nodes + edges
- **kb_stats(kb_id)**：生产图 + 隔离图的统计信息

开启 `include_inferred=True` 时，SPARQL 查询通过 UNION 同时检索生产图和推理图。

### 7.13 Copilot 本体路由（OntologyRouter）

`OntologyRouter` 位于 `backend/services/copilot/router.py`，将用户自然语言问题映射到 RDF 知识图谱中的概念和物理表。

**路由策略（full_route）：**

```
Step 1: route_concepts(kb_ids, question) → concepts[]
  调用 hybrid_route_concepts() (ontology_concept_match.py)
  ├── 策略 1: SPARQL 子串匹配
  │   └── ?s skos:prefLabel|skos:altLabel|skos:definition ?label
  │       FILTER(CONTAINS(LCASE(?label), LCASE("keyword")))
  ├── 策略 2: pgvector 余弦相似度
  │   └── 问题 embedding ↔ entity embedding，阈值 0.45
  ├── 策略 3: 关键词重叠
  │   └── question_tokens ∩ concept_label_tokens 的 Jaccard 系数
  └── 融合排序: 子串=0.5, 嵌入=0.35, 关键词=0.15

Step 2: route_tables(kb_ids, concept_iris) → tables[]
  SPARQL: 沿 computedFromTable / mapsToColumn 边找到关联的 PhysicalTable
  附带 prefLabel, businessSummary, platformId

Step 3: expand_lineage(kb_ids, table_iris) → expanded_tables[]
  SPARQL: 沿 transformsFrom / joinableWith 做 1-hop 扩展
```

**本体匹配结果组装（ontology_match.py）：**
- 概念去重展示：标签子串包含的去重（长标签覆盖短标签）
- 匹配类型标注：exact（精确） vs semantic（语义推断）
- 上下文文本生成：从全部概念（未去重）生成 `ontology_context_text`（指标口径 + 业务术语 + 关联物理表），注入 SQL 生成 prompt
- 缓存：同一问题 + 同一 KB 集合 5 分钟内复用

### 7.14 业务域语义资产聚合（domain_aggregation.py）

跨知识库聚合业务域的本体资产：

- **domain_overview(db, domain_id)**：遍历域内所有 KB，聚合 term_count、metric_count、triple_count、quarantine_count、SHACL 通过率
- **domain_layers_summary(db, domain_id)**：合并所有 KB 的五层计数
- **domain_layer_detail(db, domain_id, layer_key)**：分页明细分页，附带实体溯源 origin
- **domain_terms/metrics/dimensions/rules**：分别查询各 KB 并合并排序
- **domain_graph(db, domain_id)**：合并所有 KB 的节点和关系边
- **domain_lineage(db, domain_id)**：合并所有 KB 的血缘边

### 7.15 五维质量评估（governance.py）

`OntologyQualityAssessor` 实现 W3C DQV 对齐的五维质量评估：

| 维度 | 算法 | 权重 |
|------|------|------|
| 完整度 (Completeness) | 有定义的实体数 / 总实体数 | 25% |
| 准确度 (Accuracy) | SHACL 通过的三元组 / 总三元组 | 30% |
| 一致性 (Consistency) | 无冲突的多源实体 / 多源实体数 | 20% |
| 时效性 (Timeliness) | 90 天内更新的实体 / 总实体数 | 10% |
| 权威性 (Authority) | 人工审批通过 / 总实体数 | 15% |

综合评分：`A (≥0.90) / B (≥0.75) / C (≥0.60) / D (≥0.40) / F (<0.40)`

---

## 8. 关键数据模型

| 模型 | 表名 | 核心字段 | 用途 |
|------|------|----------|------|
| DataSource | data_sources | name, source_type, host, port, database | 数据源连接配置 |
| TableMeta | tables | table_name, database_name, datasource_id, ddl, row_count, status | 表分析状态与元数据 |
| ColumnMeta | columns | column_name, data_type, semantic_desc, semantic_type, quality_metrics | 列语义+质量画像 |
| TableSummary | table_summary | summary, use_cases, key_columns, warnings | 表五段式摘要 |
| Embedding | embeddings | ref_type, ref_id, content, embedding(vector 1536) | 向量检索 |
| BusinessDomain | business_domains | name | 业务域 |
| BusinessDomainKnowledgeBase | business_domain_knowledge_bases | domain_id, knowledge_base_id | 域↔知识库 |
| KnowledgeBase | knowledge_bases | name, description | 知识库 |
| KnowledgeEntry | knowledge_entries | title, body, semantic_role, source_meta | 知识条目 |
| Document | documents | knowledge_base_id, title, status, raw_text | 文档流水线单元 |
| DocumentChunk | document_chunks | content, quality_score, semantic_meta, embedding | 分块检索单元 |
| PipelineRun | pipeline_runs | knowledge_base_id, steps, status | 语义提取流水线状态 |
| KnowledgeGitSource | knowledge_git_sources | provider, owner, repo, branch, token, cron_expression | Git 同步源 |
| KnowledgeDatabaseImport | knowledge_database_imports | datasource_id, database_names | 数据库导入记录 |

---

## 9. API 分组

### 本体层

- `GET /api/ontology/health` — 本体存储健康检查
- `POST /api/ontology/sparql` — 执行 SPARQL 查询
- `GET /api/ontology/knowledge-bases/{id}/export` — 导出 TTL
- `POST /api/ontology/knowledge-bases/{id}/import` — 导入 TTL（经 SHACL）
- `GET /api/ontology/knowledge-bases/{id}/rdf-view` — RDF 浏览视图
- `GET /api/ontology/knowledge-bases/{id}/graph` — 图数据（nodes + edges）
- `GET /api/ontology/knowledge-bases/{id}/modeling/status` — 建模状态
- `GET /api/ontology/knowledge-bases/{id}/modeling/layers/{key}` — 五层明细分页
- `POST /api/ontology/knowledge-bases/{id}/modeling/runs` — 触发 9 步抽取
- `GET /api/ontology/knowledge-bases/{id}/views/*` — 只读 SPARQL 视图（overview/terms/graph/lineage/hierarchy/triples）
- `GET /api/ontology/knowledge-bases/{id}/quarantine` — 隔离区列表
- `POST /api/ontology/knowledge-bases/{id}/quarantine/{idx}/resolve` — 隔离项裁决
- `POST /api/ontology/knowledge-bases/{id}/quarantine/{idx}/apply-fix` — 应用修复模板
- `GET|POST /api/ontology/knowledge-bases/{id}/terms` — 术语 CRUD
- `GET|POST /api/ontology/knowledge-bases/{id}/metrics` — 指标 CRUD
- `GET /api/ontology/knowledge-bases/{id}/dimensions` — 维度列表
- `GET /api/ontology/knowledge-bases/{id}/rules` — 规则列表
- `GET /api/ontology/knowledge-bases/{id}/provenance` — 实体溯源链
- `GET /api/ontology/knowledge-bases/{id}/quality-assessment` — 五维质量评估
- `POST /api/ontology/knowledge-bases/{id}/kge/discover` — KGE 知识图谱补全
- `POST /api/ontology/knowledge-bases/{id}/assertions/promote` — 断言生命周期提升
- `POST /api/ontology/knowledge-bases/{id}/deprecate` — 标记实体弃用

### 业务域语义资产

- `GET /api/business-domains/{id}/ontology/overview` — 域内各 KB 建模摘要
- `GET /api/business-domains/{id}/ontology/layers` — 五层摘要（可选 `?kb=`）
- `GET /api/business-domains/{id}/ontology/layers/{key}` — 单层明细分页
- `GET /api/business-domains/{id}/ontology/terms|metrics|dimensions|rules` — 语义实体列表
- `GET /api/business-domains/{id}/ontology/graph|lineage|assets` — 关系图、血缘、物理表

### Copilot

- `POST /api/ask` — 问答
- `POST /api/ask/stream` — SSE 流式问答

### 数据源与表

- `CRUD /api/datasources` — 数据源 CRUD
- `GET /api/tables` / `GET /api/table/{id}` — 表列表/详情

### 知识库

- `CRUD /api/knowledge-bases` — 知识库管理
- `POST /api/knowledge-bases/{id}/upload` — 文件上传
- `POST /api/knowledge-bases/{id}/git-sources` — Git 同步源
- `POST /api/knowledge-bases/{id}/run-semantic-pipeline` — 触发语义提取

---

## 10. 前端路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | 首页 | 业务域列表 |
| `/copilot` | Copilot 对话 | ChatBI 助手 |
| `/datasources` | 数据源管理 | 列表+增删改 |
| `/datasources/[id]` | 数据源目录 | 库表浏览+分析触发 |
| `/table/[id]` | 表详情 | 列信息+摘要 |
| `/business-domains/[id]` | 业务域详情 | 描述+库表选择+知识库绑定 |
| `/ontology` | 语义资产 | 侧栏当前业务域五层浏览 |
| `/knowledge-bases` | 知识库列表 | 管理入口 |
| `/knowledge-bases/[id]` | 知识库详情 | 导入源 + 建模与质量 |
| `/settings` | 设置 | LLM偏好 |

---

## 11. 现有限制与风险

| 风险项 | 等级 | 说明 |
|--------|------|------|
| 密码明文存储 | 高 | `DataSource.password` 明文存于 DB |
| 异步任务非队列化 | 中 | 进程内线程/协程，不适合高并发 |
| XSS 风险 | 中 | 前端存在 `dangerouslySetInnerHTML` 渲染点 |
| SQL 校验覆盖 | 低 | 复杂方言可能误伤或漏过 |
| 向量维度锁死 | 低 | 固定 1536 维，换模型需迁移 |

---

## 12. 推荐演进路线

**P0：** 数据源凭据加密 / 异步任务队列化 / 线上 routing fallback 率观测

**P1：** semantic_relations 可视化编辑 / concept_id 跨域手动对齐 UI

**P2：** 多用户与权限体系 / 2-hop 语义图扩展

---

## 13. 相关专题文档

| 文档 | 内容 |
|------|------|
| [本体建模理论标准](../本体建模/本体建模理论标准.md) | **新增** — W3C 技术栈、方法论、OWL/SHACL/SWRL 分工 |
| [DataLens 本体建模优化方案](../本体建模/DataLens本体建模优化方案.md) | **新增** — P0–P3 优化路线、差距分析与实施方案 |
| [本体三层架构与 UI 优化方案](../本体建模/本体三层架构与UI优化.md) | 导入层、清洗层、展示层设计 |
| [企业语义层与域内自治实践](企业语义层与域内自治实践.md) | 理念、存储、联邦治理 |
| [本体建模：企业数据来源与自动化抽取](../本体建模/企业数据来源与自动化抽取.md) | 本体要素全景、企业数据源映射 |
| [COPILOT_ROUTING_OPTIMIZATION](../路由与抽取/Copilot语义路由优化.md) | 路由 backlog、配置项、trace |
| [SEMANTIC_LAYER_OPTIMIZATION_BACKLOG](./语义层能力清单.md) | 语义层能力状态 |
| [本体驱动重构方案](../本体建模/本体驱动重构方案.md) | TBox 完整设计、实现阶段分解 |
