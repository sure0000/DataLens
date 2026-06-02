# DataLens 设计介绍文档

> 面向新接手人员的系统设计全貌，涵盖核心目标、技术架构、建模理论、底层逻辑与关键设计决策。

---

## 目录

1. [项目概述](#1-项目概述)
2. [核心目标与价值](#2-核心目标与价值)
3. [系统全景架构](#3-系统全景架构)
4. [技术栈选型](#4-技术栈选型)
5. [本体建模理论与底层逻辑](#5-本体建模理论与底层逻辑)
6. [数据模型设计](#6-数据模型设计)
7. [核心数据流](#7-核心数据流)
8. [模块详解](#8-模块详解)
9. [API 路由设计](#9-api-路由设计)
10. [前端架构](#10-前端架构)
11. [关键设计决策](#11-关键设计决策)
12. [质量保障体系](#12-质量保障体系)
13. [部署与运维](#13-部署与运维)
14. [当前状态与演进路线](#14-当前状态与演进路线)

---

## 1. 项目概述

DataLens 是一个 **LLM 驱动的企业级语义知识图谱平台**，本质上是一个轻量级 ChatBI 系统。它连接企业数据源，自动理解表结构和字段的业务含义，构建并维护一个以 RDF 知识图谱为核心的业务语义知识库，最终让用户可以用自然语言提问并获得精确的 SQL 回答。

**一句话定位：** 从"数据库里有啥"到"用户想问啥"之间的语义鸿沟，由 DataLens 自动填补。

### 1.1 核心工作流

```
数据源接入 → 文档索引 → LLM 语义抽取 → 本体知识图谱 → Copilot 智能问答
```

### 1.2 解决的三个核心问题

| 问题 | 传统方式 | DataLens 方式 |
|------|---------|--------------|
| **术语对齐** — 用户说的"GMV"和数据库里 `orders.amount` 的关系 | 靠人肉沟通、Wiki 文档 | 本体自动抽取术语，`dl:mapsToColumn` 建立映射 |
| **表路由** — 用户的问题应该查哪些表 | 靠经验、问 DBA | SPARQL 图遍历 + 向量检索 + RRF 融合排序 |
| **回答可信** — 生成的 SQL 用了哪些口径、经过什么推理 | 黑盒 | 完整路由 trace：概念匹配 → 表路由 → 血缘扩展 → SQL 推导 |

---

## 2. 核心目标与价值

### 2.1 核心目标

1. **自动化语义理解** — 从非结构化文档（PDF、Word、Confluence）和结构化元数据（DDL、ETL 代码）中自动提取业务概念
2. **本体驱动路由** — 用 RDF 知识图谱（而非纯向量检索）作为 Copilot 的查询路由中枢，实现可解释、可追溯的 SQL 生成
3. **质量管控闭环** — SHACL 校验 + 隔离区 + 交叉一致性校验，确保写入图的数据质量
4. **领域级分层治理** — 领域本体 → 知识库本体两层架构，域内自治，跨域通过 SKOS 映射对齐

### 2.2 关键价值

- **降低语义对齐成本** — 80% 的术语定义和映射由 LLM 自动完成
- **可观测的 AI 回答** — 每个 SQL 回答附带完整的路由 trace，可追溯到源文档
- **不取代现有系统** — 作为语义聚合层，消费 BI 工具、数据字典、ETL 代码中的知识
- **渐进式冷启动** — 没有文档时也能靠数据库元数据自动采集提供基础物理表骨架

---

## 3. 系统全景架构

### 3.1 物理拓扑

```
┌──────────────────────────────────────────────────────────┐
│                      Nginx / 浏览器                       │
│                   localhost:3000 (前端)                    │
└─────────────────────┬────────────────────────────────────┘
                      │ HTTP / SSE 流式
┌─────────────────────▼────────────────────────────────────┐
│               FastAPI 后端 (localhost:8000)                │
│                                                          │
│  ┌──────────┬──────────┬──────────┬──────────────────┐   │
│  │ Routers  │ Copilot  │Extraction│    Ontology       │   │
│  │ (17 个)  │ Pipeline │Orchestr. │  Writer/Reader    │   │
│  └──────────┴──────────┴──────────┴──────────────────┘   │
└──────┬──────────────────────────────────────┬───────────┘
       │                                      │
┌──────▼──────┐                      ┌────────▼──────────┐
│ PostgreSQL  │                      │  Apache Jena      │
│ (元数据+向量)│                      │  Fuseki (RDF 图)   │
│             │                      │  localhost:3030    │
│ • 表/列元数据│                     │                    │
│ • 文档/分块  │                     │ • TBox (模式层)     │
│ • pgvector  │                     │ • ABox (实例层)     │
│ • 全文索引   │                     │ • 推理闭包          │
└─────────────┘                     │ • 隔离区            │
                                    └────────────────────┘
```

### 3.2 逻辑分层

```
┌─────────────────────────────────────────────────────────┐
│  消费层 (Consumption)                                    │
│  Copilot 对话 · SPARQL 控制台 · 本体浏览器 · 治理面板      │
├─────────────────────────────────────────────────────────┤
│  本体层 (Ontology)          ← 系统的"大脑"                │
│  RDF 三元组存储 (Fuseki)                                │
│  ┌──────────┬──────────┬──────────┬─────────────────┐   │
│  │ TBox     │ ABox     │ SHACL    │ Inference       │   │
│  │ 类/属性   │ 术语/指标 │ 校验形状  │ 传递/对称闭包    │   │
│  └──────────┴──────────┴──────────┴─────────────────┘   │
├─────────────────────────────────────────────────────────┤
│  抽取层 (Extraction)        ← 系统的"消化系统"            │
│  LLM 流水线: 术语→指标→关系→层级→血缘→Join               │
├─────────────────────────────────────────────────────────┤
│  摄入层 (Ingestion)         ← 系统的"感官"                │
│  文件上传 · Git 同步 · API 集成 · 数据库连接              │
├─────────────────────────────────────────────────────────┤
│  存储层 (Storage)                                        │
│  PostgreSQL (元数据+向量) · Fuseki (RDF 图)               │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 技术栈选型

| 层 | 技术 | 版本/规格 | 选型理由 |
|----|------|----------|----------|
| **后端框架** | FastAPI (Python 3.11+) | — | 异步原生、自动 OpenAPI、流式响应 |
| **前端框架** | Next.js (React 18) | App Router | SSR + 客户端渲染、丰富生态 |
| **关系数据库** | PostgreSQL + pgvector | 15+/16 | 向量检索与元数据存储合一，减少组件 |
| **RDF 存储** | Apache Jena Fuseki | 4.10.0 | 标准 SPARQL 1.1、OWL 2 RL 推理、轻量部署 |
| **LLM 网关** | 多厂商适配 | 18+ 厂商 | DeepSeek(主)、OpenAI(备)、Azure、Anthropic 等 |
| **向量模型** | text-embedding-3-small 等 | 1536d | 通用嵌入 + HNSW 索引 |
| **容器化** | Docker Compose | 3.9 | 一键启动 PG+Fuseki+前后端 |
| **本体序列化** | Turtle / Trig | W3C 标准 | 人类可读、标准互操作 |
| **本体语言** | OWL 2 RL + SKOS + SHACL | W3C 标准 | 计算可判定 + 轻量组织 + 封闭世界校验 |

---

## 5. 本体建模理论与底层逻辑

### 5.1 为什么选择本体（Ontology）？

传统 ChatBI 系统面临的核心困境：**向量检索只能找到"相似的"，找不到"逻辑上相关的"**。

- 用户问"上个月华东区 GMV" → 向量检索可能返回包含"GMV"的文档，但不理解 GMV 由 `orders.amount` 计算，且需要过滤 `refund_flag=0`
- DataLens 的做法：术语"GMV"在图中是一个 `dl:Metric` 节点，通过 `dl:computedFromTable → dl:PhysicalTable` 找到表，通过 `dl:formula` 得到口径，通过 `dl:joinableWith` 扩展关联表

**本体提供了向量不具备的能力：关系遍历、逻辑推导、多层约束。**

### 5.2 W3C 语义网技术栈分层

DataLens 的本体层严格遵循 W3C 技术栈：

```
┌──────────────────────┐
│  SPARQL 1.1          │  ← 查询层：图遍历与检索
├──────────────────────┤
│  SHACL               │  ← 校验层：封闭世界数据验证
├──────────────────────┤
│  SWRL / Datalog      │  ← 规则层：IF-THEN 推导（部分实现）
├──────────────────────┤
│  OWL 2 RL            │  ← 推理层：subClassOf、传递/对称闭包
├──────────────────────┤
│  SKOS                │  ← 组织层：术语标签、同义词、层级
├──────────────────────┤
│  RDFS                │  ← Schema 层：类/属性层级
├──────────────────────┤
│  RDF 1.1             │  ← 数据层：三元组图模型
└──────────────────────┘
```

### 5.3 TBox / ABox / RBox 三元结构

这是理解 DataLens 本体设计的核心概念：

| 组件 | 全称 | 内容 | 示例 |
|------|------|------|------|
| **TBox** | Terminological Box | 模式层 — 类定义、属性定义、公理 | `dl:Metric rdfs:subClassOf dl:BusinessConcept` |
| **ABox** | Assertional Box | 实例层 — 个体断言 | `data:metric/gmv rdf:type dl:Metric` |
| **RBox** | Role Box | 属性特征 — 数学特性 | `dl:joinableWith rdf:type owl:SymmetricProperty` |

**关键原则：TBox/ABox/RBox 严格分离。** TBox 变更通过版本管理，ABox 写入经 SHACL 守门，RBox 与 TBox 同步发布。

### 5.4 三层本体架构

```
Layer 0: Domain Ontology (领域本体)
  Named Graph: graph/domain/{id}
  → 每个业务域的 TBox 扩展与术语定义

Layer 1: Application Ontology (知识库本体)
  Named Graph: graph/kb/{id}         → ABox (生产实例)
  Named Graph: graph/quarantine/{id} → 隔离区 (校验失败)
  → 术语、指标、血缘、物理表映射

Layer 2: Inference Graph (推理闭包)
  Named Graph: graph/inferred/{scope}
  → OWL 2 RL 推理机生成的推导三元组
  → 不污染生产图，仅用于查询加速
```

跨域等价对齐通过 TBox 中定义的 SKOS 映射词汇表（`skos:exactMatch`、`skos:closeMatch` 等）实现，无需独立的企业本体层。

### 5.5 本体清洗五层模型

写入知识图谱的 ABox 数据按五个语义层分类：

| 层 | 名称 | 对应实体 | 提取器 | OWL 元素 |
|----|------|---------|--------|----------|
| **1. 词汇层** | Vocabulary | `dl:BusinessTerm` | `term_extractor.py` | SKOS prefLabel/altLabel/definition |
| **2. 规则层** | Rule | `dl:Metric`, `dl:BusinessRule` | `metric_extractor.py`, `rule_extractor.py` | `dl:formula`, `dl:caliber`, `dl:ruleExpression` |
| **3. 实体概念层** | Entity-Concept | `dl:BusinessConcept` 子类 | `hierarchy_builder.py`, `dimension_extractor.py` | `rdfs:subClassOf`, `skos:broader` |
| **4. 关系层** | Relation | 语义关系边 | `relation_extractor.py`, `lineage_extractor.py`, `join_extractor.py` | `dl:dependsOn`, `dl:derivedFrom`, `dl:joinableWith` |
| **5. 属性层** | Attribute | 实体字面量属性 | 所有提取器共同产出 | `owl:DatatypeProperty` |

### 5.6 OWL 2 RL 推理引擎

DataLens 选择 OWL 2 RL Profile（而非 EL 或 QL），因为 RL 最适合企业知识图谱场景：

**支持的推理能力：**

| 推理类型 | 作用属性 | 效果 |
|---------|---------|------|
| 传递闭包 | `dl:derivedFrom`, `dl:transformsFrom` | A→B, B→C ⇒ A→C |
| 对称闭包 | `dl:joinableWith`, `dl:exactMatch` | A↔B ⇒ B↔A |
| 逆属性 | `skos:broader` ↔ `skos:narrower` | A broader B ⇒ B narrower A |
| 子类传递 | `rdfs:subClassOf` | A ⊑ B, B ⊑ C ⇒ A ⊑ C |

**RL Profile 的限制（需要 SHACL 补充）：**
- 不支持 `owl:minCardinality`（"必须有值"的约束交给 SHACL `sh:minCount`）
- 不支持 `owl:unionOf`、`owl:complementOf`

### 5.7 OWL 与 SHACL 的分工

这是最容易混淆的概念，也是 DataLens 设计的核心洞察：

| 维度 | OWL（推理语言） | SHACL（校验语言） |
|------|---------------|-----------------|
| 世界假设 | **开放世界** — 缺失不等于假 | **封闭世界** — 缺失 = 违规 |
| 目的 | 推导新知识 | 验证数据完整性 |
| 处理缺失 | 不做假设 | 报告违规 |
| DataLens 用途 | 概念分类、属性传递、表 Join 对称 | 术语必填 prefLabel、指标必填 formula、无自环层级 |

**设计原则：写操作必须经过两阶段处理**
```
RawTriple → clean_triples() → SHACL 校验 → 通过 → 生产图
                                          → 失败 → 隔离区
```

### 5.8 SKOS 的定位

SKOS 位于自由文本和形式本体之间，DataLens 用它处理术语组织：

- `skos:prefLabel` — 术语首选标签（如"成交总额"）
- `skos:altLabel` — 同义词（如"GMV"、"总流水"）
- `skos:broader/narrower` — 概念层级（如"GMV" → "经营指标"）
- `skos:exactMatch` — 跨知识库精确等价
- `skos:definition` — 业务定义文本

---

## 6. 数据模型设计

### 6.1 存储分工

DataLens 采用**双存储架构**：

| 存储 | 用途 | 数据类型 |
|------|------|---------|
| **PostgreSQL** | 性能缓存 / 基础设施 | 数据源连接信息、表/列元数据、文档分块、向量嵌入、知识条目、用户配置 |
| **Apache Jena Fuseki** | 语义中枢 / 唯一真相源 (SSOT) | TBox 类/属性定义、ABox 术语/指标实例、血缘关系、SHACL 形状、推理闭包 |

### 6.2 PostgreSQL 核心表

```
┌──────────────────────────────────────────────────────┐
│  业务域与组织                                          │
│  business_domains / business_domain_descriptions       │
│  business_domain_selections / business_domain_knowledge│
├──────────────────────────────────────────────────────┤
│  数据源与 Schema 元数据                                │
│  data_sources → tables → columns                      │
│  table_summary / query_examples                        │
├──────────────────────────────────────────────────────┤
│  知识库与文档管线                                      │
│  knowledge_bases → PipelineConfig                     │
│  knowledge_bases → documents → document_chunks         │
│  knowledge_bases → knowledge_entries                   │
│  knowledge_bases → evidence_packages                   │
├──────────────────────────────────────────────────────┤
│  Git / API 导入源                                      │
│  knowledge_git_sources / knowledge_api_sources         │
│  knowledge_mcp_sources / knowledge_database_imports    │
├──────────────────────────────────────────────────────┤
│  流水线与向量                                          │
│  pipeline_runs / embeddings / document_chunks (embedding)│
├──────────────────────────────────────────────────────┤
│  配置                                                  │
│  runtime_settings / llm_connections / import_logs      │
└──────────────────────────────────────────────────────┘
```

### 6.3 RDF 本体类层级 (TBox)

```
owl:Thing
├── dl:ConceptScheme          ← SKOS 概念体系
│
├── dl:BusinessConcept        ← 业务概念基类 (⊑ skos:Concept)
│   ├── dl:BusinessTerm       ← 业务术语 (词汇层)
│   ├── dl:Metric             ← 指标定义 (规则层)
│   ├── dl:Dimension          ← 分析维度
│   └── dl:BusinessRule       ← 业务规则
│
├── dl:DataAsset              ← 数据资产基类
│   ├── dl:PhysicalTable      ← 物理表
│   ├── dl:PhysicalColumn     ← 物理列
│   └── dl:View               ← 逻辑视图
│
├── dl:DataSource             ← 外部数据源连接
├── dl:KnowledgeBase          ← 知识库
├── dl:Document / dl:DocumentChunk  ← 文档溯源
├── dl:LineageAssertion       ← 血缘断言
├── dl:JoinRelation           ← JOIN 关系
└── dl:QuarantinedAssertion   ← 隔离区断言
```

### 6.4 核心对象属性 (ObjectProperty)

| 属性 | 特征 | 含义 | 示例 |
|------|------|------|------|
| `dl:dependsOn` | — | 概念依赖 | GMV → 订单金额 |
| `dl:derivedFrom` | Transitive | 指标派生 | 客单价 → (GMV, 订单量) |
| `dl:computedFromTable` | — | 计算来源表 | GMV → orders |
| `dl:mapsToColumn` | — | 映射到物理列 | "成交额" → orders.amount |
| `dl:joinableWith` | Symmetric | 表可 JOIN | orders ↔ order_items |
| `dl:transformsFrom` | Transitive | 数据血缘 | dws_order → dwd_order |
| `skos:broader` | (inverseOf narrower) | 上位概念 | VIP客户 → 客户 |
| `skos:exactMatch` | Symmetric + Transitive | 跨库等价 | (KB1)GMV ≡ (KB2)成交总额 |
| `dl:groundedBy` | — | 溯源锚定 | 术语 → 源文档分块 |

---

## 7. 核心数据流

### 7.1 摄入 → 抽取 → 写入 (写路径)

```
                        ┌─────────────┐
  文件上传 / Git / API → │  文本提取    │
                        └──────┬──────┘
                               ↓
                        ┌─────────────┐
                        │  清洗 + 分块  │
                        └──────┬──────┘
                               ↓
                    ┌──────────┴──────────┐
                    ↓                     ↓
            ┌─────────────┐       ┌─────────────┐
            │  向量嵌入     │       │ LLM 语义抽取 │
            │  (pgvector)  │       │ (9 步流水线) │
            └─────────────┘       └──────┬──────┘
                                         ↓
                                  ┌─────────────┐
                                  │  SHACL 校验  │
                                  └──────┬──────┘
                                   ┌─────┴─────┐
                                   ↓           ↓
                            ┌──────────┐ ┌──────────┐
                            │ 生产图    │ │ 隔离区    │
                            │ (ABox)   │ │ (修复)    │
                            └────┬─────┘ └──────────┘
                                 ↓
                          ┌─────────────┐
                          │ OWL 2 RL    │
                          │ 推理引擎    │
                          └──────┬──────┘
                                 ↓
                          ┌─────────────┐
                          │ 推理闭包图   │
                          └─────────────┘
```

### 7.2 Copilot 查询流 (读路径)

```
用户问题: "上个月华东区的GMV是多少?"
    │
    ├── 1. 意图分类 (Intent Classification)
    │      → 识别为"指标查询"
    │
    ├── 2. 语义路由 (Ontology Router)
    │      ├── SPARQL: 匹配概念 "GMV" → dl:Metric + dl:BusinessTerm
    │      ├── SPARQL: 匹配维度 "华东区" → dl:Dimension
    │      └── 向量检索: 候选表摘要匹配 (RRF 融合排序)
    │
    ├── 3. 图扩展 (Graph Expansion)
    │      ├── 概念 → computedFromTable → PhysicalTable "orders"
    │      ├── 物理表 → joinableWith → PhysicalTable "order_items"
    │      └── 血缘传递闭包: transformsFrom 多跳展开
    │
    ├── 4. 上下文组装 (Context Assembly)
    │      ├── 术语定义: "GMV = 成交总额..."
    │      ├── 指标口径: "SUM(amount) WHERE status='paid' AND refund_flag=0"
    │      ├── 表结构: orders(id, amount, status, created_at, region...)
    │      └── 关联表: order_items, regions
    │
    ├── 5. SQL 生成 + 审查
    │      ├── LLM 生成 SQL (含推理步骤说明)
    │      ├── SQL AST 安全校验 (禁止 DROP/ALTER/INSERT)
    │      └── 风险提示
    │
    └── 6. 执行 + 返回
           ├── 只读执行 (READ ONLY 事务)
           ├── 流式返回结果 (SSE)
           └── 附带完整 routing_trace
```

### 7.3 路由 Trace 示例

```json
{
  "routing_trace": {
    "matched_concepts": [
      {"term": "GMV", "iri": "https://datalens.local/ontology/term/gmv", "confidence": 85}
    ],
    "routed_tables": [
      {"table": "orders", "platformId": 42, "via": "computedFromTable"}
    ],
    "expanded_tables": [
      {"table": "order_items", "platformId": 56, "via": "joinableWith"}
    ],
    "context_sections": ["terms", "metrics", "tables", "schema"],
    "strategy": "ontology_sparql"
  }
}
```

---

## 8. 模块详解

### 8.1 后端目录总览

```
backend/
├── main.py                       # FastAPI 入口，注册中间件和路由
├── config.py                     # 配置中心 (Pydantic BaseSettings, 60+ 配置项)
├── database.py                   # PostgreSQL 引擎、连接池、schema 自动补丁
├── models.py                     # SQLAlchemy ORM (30+ 表)
├── security.py                   # Bearer Token 鉴权中间件
│
├── ontology/                     # 本体定义 (静态 TBox)
│   ├── tbox/                     # TBox 文件: core.ttl, governance.ttl, provenance.ttl
│   └── shacl/                    # SHACL 形状: term, metric, hierarchy, lineage, table
│
├── services/                     # 业务逻辑层
│   ├── copilot/                  # Copilot 查询引擎
│   │   ├── pipeline.py           #   查询流水线编排
│   │   ├── router.py             #   SPARQL 本体路由 (概念匹配 + 表路由 + 血缘扩展)
│   │   └── context.py            #   上下文组装
│   │
│   ├── extraction/               # LLM 知识抽取
│   │   ├── orchestrator.py       #   9 步抽取流水线编排
│   │   ├── term_extractor.py     #   术语提取 → BusinessTerm
│   │   ├── metric_extractor.py   #   指标提取 → Metric
│   │   ├── dimension_extractor.py#   维度提取 → Dimension
│   │   ├── rule_extractor.py     #   规则提取 → BusinessRule
│   │   ├── relation_extractor.py #   关系提取 → dependsOn/derivedFrom
│   │   ├── hierarchy_builder.py  #   层级构建 → broader/narrower
│   │   ├── lineage_extractor.py  #   血缘提取 → transformsFrom
│   │   ├── join_extractor.py     #   JOIN 提取 → joinableWith
│   │   ├── cross_entity_validator.py  # P0 交叉一致性校验
│   │   ├── cross_kb_equivalence.py    # P2 跨库等价检测
│   │   └── entity_version_tracker.py  # P3 版本追踪
│   │
│   ├── ontology/                 # 本体操作
│   │   ├── writer.py             #   写入 (经 SHACL → 生产图)
│   │   ├── reader.py             #   读取 (含推理图查询)
│   │   ├── reasoner.py           #   OWL 2 RL 推理引擎
│   │   ├── validator.py          #   SHACL 校验
│   │   └── quarantine.py         #   隔离区管理
│   │
│   ├── triple_store/             # 三元组存储
│   │   ├── store.py              #   Fuseki SPARQL 客户端
│   │   ├── cache.py              #   SPARQL 结果缓存
│   │   └── migrations.py         #   本体版本迁移
│   │
│   ├── retrieval/                # 检索
│   │   ├── hybrid_search.py      #   BM25 + 向量混合检索
│   │   ├── embedding.py          #   向量嵌入服务
│   │   └── ranking.py            #   RRF 融合排序
│   │
│   ├── ingestion/                # 摄入
│   │   ├── evidence.py           #   证据合成视图
│   │   ├── document.py           #   文档摄入
│   │   ├── schema.py             #   Schema 摄入
│   │   └── git.py                #   Git 摄入
│   │
│   ├── routing/                  # 旧路由模块 (Phase 4 后废弃)
│   ├── llm_service.py            # LLM 调用抽象层
│   ├── llm_models.py             # 多模型管理
│   └── schema_extractor.py       # 数据库 Schema 自动分析
│
├── routers/                      # API 路由 (17 个)
│   ├── copilot.py                #   Copilot 问答接口
│   ├── ontology.py               #   本体 CRUD + SPARQL + 导出
│   ├── knowledge_bases.py        #   知识库 CRUD
│   ├── datasources.py            #   数据源管理
│   ├── tables.py                 #   表/列详情
│   ├── analyze.py                #   Schema 分析
│   └── ...                       #   其他路由
│
└── prompts/                      # LLM Prompt 模板 (20+ 个)
```

### 8.2 抽取流水线详解 (Orchestrator)

抽取流水线是系统的核心——它是从"原始文档"到"结构化的本体知识"的转化引擎。

**并行执行阶段（针对文档分块）：**
```
Chunk → term_extractor ─┐
Chunk → metric_extractor ─┤
Chunk → dimension_extractor ─┼─→ 并行 LLM 调用
Chunk → rule_extractor ─┤
Chunk → relation_extractor ─┤
Chunk → hierarchy_builder ─┘
```

**串行执行阶段（跨文档聚合）：**
```
data_lineage → (Git 代码源才执行)
join_extraction → (数据库 Schema 才执行)
domain_term_extraction
```

**后处理阶段（非 LLM）：**
```
cross_entity_validation → (P0: 交叉引用完整性检查)
cross_kb_equivalence → (P2: 跨库等价术语检测)
entity_version_tracking → (P3: 版本变更记录)
```

**断点续跑机制：** 每个步骤独立缓存结果 (`step_cache.py`)，流水线中断后重新触发时自动跳过已完成步骤。

### 8.3 本体写入链路

```
RawTriple 列表
  │
  ├── 阶段 1: clean_triples()
  │     ├── 语法清洗 (TTL 转义、IRI 合法化)
  │     ├── 链接校验 (object_is_uri 一致性)
  │     ├── TBox 校验 (类型与属性 domain 匹配)
  │     ├── 去重 (同 S-P-O 合并)
  │     └── 状态门 (draft 状态不入生产图)
  │
  ├── 阶段 2: SHACL 校验
  │     ├── BusinessTerm → 必须有 skos:prefLabel (≥3 字符)
  │     ├── Metric → 必须有 dl:formula (≥3 字符)
  │     ├── PhysicalTable → 必须有 dl:platformId
  │     ├── 层级 → 无自环、深度 ≤ 6
  │     └── 引用 → dependsOn/computedFromTable 目标存在
  │
  ├── 通过 → production graph (graph/kb/{id})
  └── 失败 → quarantine graph (graph/quarantine/{id})
              └── 人工审核: 批准 / 拒绝 / 应用修复
```

### 8.4 Copilot 查询引擎

**OntologyRouter** 的核心查询逻辑：

1. **概念匹配** — 用 SPARQL REGEX 匹配用户问题中的术语：
   ```sparql
   SELECT ?concept ?label ?type WHERE {
       GRAPH ?g {
           ?concept a ?type ;
                    skos:prefLabel ?label .
           FILTER(REGEX(?label, "GMV", "i"))
       }
   }
   ```

2. **表路由** — 从概念沿属性路径找到物理表：
   - `dl:BusinessTerm → dl:mapsToColumn → dl:PhysicalColumn → schema:isPartOf → dl:PhysicalTable`
   - `dl:Metric → dl:computedFromTable → dl:PhysicalTable`

3. **图扩展** — Property path 多跳遍历：
   - `dl:joinableWith` (对称闭包) → 扩表
   - `dl:transformsFrom` (传递闭包) → 血缘上下游

4. **向量融合** — 当 SPARQL 匹配弱时，混入表摘要向量检索，RRF (Reciprocal Rank Fusion) 融合排序

---

## 9. API 路由设计

### 9.1 路由总览

| 路由前缀 | 模块 | 核心功能 |
|---------|------|---------|
| `/api/connect` | connect | 数据源连接测试 |
| `/api/datasources` | datasources | 数据源 CRUD、表列表 |
| `/api/tables` | tables | 表详情、列清单、Schema 分析 |
| `/api/analyze` | analyze | 批量 Schema 语义分析 |
| `/api/knowledge-bases` | knowledge_bases | 知识库 CRUD |
| `/api/knowledge-bases/{id}/git-sources` | knowledge_git_sources | Git 仓库同步管理 |
| `/api/knowledge-bases/{id}/api-sources` | knowledge_api_sources | API 文档源管理 |
| `/api/knowledge-bases/{id}/database-imports` | knowledge_database_imports | 数据库 Schema 导入 |
| `/api/knowledge-bases/{id}/ingestion` | knowledge_ingestion | 文档摄入触发 |
| `/api/knowledge-bases/{id}/semantic` | knowledge_semantic | 语义抽取触发与状态 |
| `/api/business-domains` | business_domains | 业务域 CRUD |
| `/api/domain-ontology` | domain_ontology | 域级本体聚合 |
| `/api/ontology` | ontology | SPARQL 查询、实体 CRUD、本体导出、治理 |
| `/api/copilot` | copilot | 自然语言问答（SSE 流式）、SQL 执行 |
| `/api/llm-settings` | llm_settings | 模型连接配置 |
| `/api/diagnostics` | diagnostics | 系统诊断接口 |

### 9.2 鉴权模型

- 全局 Bearer Token 鉴权（`/health` 除外）
- 前端通过 `NEXT_PUBLIC_API_TOKEN` 配置，每次请求携带 `Authorization: Bearer <token>`
- CORS 预检 (OPTIONS) 跳过鉴权
- 业务域隔离通过自定义 Header `X-Business-Domain-Id` 传递

---

## 10. 前端架构

### 10.1 页面路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 重定向 | → `/copilot` |
| `/copilot` | Copilot 对话 | 主界面，自然语言问答 |
| `/ontology` | 本体浏览 | 五层语义资产浏览 |
| `/knowledge-bases` | 知识库列表 | 知识库管理入口 |
| `/knowledge-bases/[id]` | 知识库详情 | 导入源卡片 + 建模与质量 |
| `/datasources` | 数据源列表 | 数据库连接管理 |
| `/datasources/[id]` | 数据源详情 | 数据库/表浏览 |
| `/datasources/[id]/tables/[tid]` | 表详情 | Schema + 语义分析结果 |
| `/settings` | 设置 | 模型配置、业务域、界面 |
| `/business-domains/[id]` | 业务域详情 | 编辑描述、关联资源 |

### 10.2 关键组件族

```
components/
├── copilot/         ChatView, MessageBubble, TraceTimeline, ContextInspector, SqlPreview
├── ontology/        ConceptHierarchyTree, ConceptDetailPanel, RelationGraph, MetricDerivationChain,
│                    TableLineageGraph, TripleViewer, ShaclViolationList, OntologyStatsCards
├── knowledge/       SourceCardGrid, SourcePipeline, OutputTabs, DocumentTable
├── datasource/      TableCardGrid, TableSemanticPanel, ColumnList, LineageDagView
├── governance/      QuarantineList, ShaclDashboard, ConfidenceDistribution, ApproveRejectPanel
└── shared/          EntityBadge, IriLink, ConfidenceBar, StatusChip
```

---

## 11. 关键设计决策

### 11.1 为什么 RDF 是"唯一真相源"而 PostgreSQL 是"缓存"？

**设计原则：语义数据归图，基础设施数据归库。**

- **本体知识**（术语定义、指标口径、关系、血缘）→ RDF 图。因为它们需要关系遍历、推理、SPARQL 查询
- **基础设施数据**（连接串、表元数据、向量、用户配置）→ PostgreSQL。因为它们需要事务、索引、全文搜索

PostgreSQL 中不再存储语义数据的权威副本——语义层旧表（`BusinessTerm`, `MetricDefinition`, `DataLineage`, `SemanticRelation`）已在 Phase 1 中移除。

### 11.2 为什么选择 Fuseki 而非 Neo4j 或其他图数据库？

- **标准 RDF 引擎** — 原生支持 SPARQL 1.1、OWL 2 RL 推理、SHACL 校验
- **轻量部署** — 单个 JAR 或 Docker 容器，无额外依赖
- **W3C 标准兼容** — 数据可导出为标准 Turtle/Trig，不被厂商锁定
- **推理原生嵌入** — 无需外挂推理机，查询管线直接走推理图

### 11.3 为什么 OWL 2 RL 而非 OWL DL？

RL Profile 的计算复杂度是可判定的 PTime，适合：
- 规则式推理（if-then 模式，与业务规则表达方式一致）
- 增量推理（每次写入后可快速刷新推理闭包，不会组合爆炸）
- 大规模 ABox（企业可能有数万术语和指标）

RL 的表达力缺口（基数约束、unionOf）由 SHACL 填补。

### 11.4 为什么 TBox/ABox 严格分离？

- **安全性** — TBox 变更（如新增属性）不应意外影响已有 ABox 数据
- **可管理性** — TBox 版本化管理 (`owl:versionInfo`)，ABox 独立演进
- **推理效率** — 推理机只操作 ABox + TBox 的固定子集

### 11.5 为什么 LLM 抽取 + SHACL 守门，而非直接信任 LLM 输出？

LLM 不可避免会产生：
- 术语含幻觉定义
- 指标引用不存在的表
- 公式与口径描述矛盾
- IRI 格式不合法

SHACL 守门确保写入图的数据满足**最低结构质量标准**，置信度阈值控制审批流程。

---

## 12. 质量保障体系

### 12.1 多层质量防线

```
Layer 1: 入库前 — 清洗规范化
  ├── 文本清洗 (去 HTML、规范化)
  ├── 分块质量 (最小块字符数、近重复检测)
  └── 语义结构化 (LLM 提取)

Layer 2: 写入前 — SHACL 校验
  ├── 结构约束 (必填字段、数据类型)
  ├── 引用完整性 (dependsOn/computedFromTable 目标存在)
  └── 层级安全 (无自环、深度 ≤ 6)

Layer 3: 写入后 — 交叉一致性
  ├── 跨抽取器交叉校验 (P0)
  ├── 跨知识库等价检测 (P2)
  └── 实体版本追踪 (P3)

Layer 4: 消费层 — SQL 安全
  ├── AST 白名单 (仅 SELECT/EXPLAIN/WITH)
  └── 执行风险提示 (review 标记)
```

### 12.2 DQV 数据质量五维度

依据 W3C DQV 标准 (`governance.ttl`)：

| 维度 | 定义 | 指标 |
|------|------|------|
| **完整度** | 有完整定义的实体占比 | 有定义实体 / 总实体 |
| **准确度** | 通过校验的三元组占比 | SHACL 通过三元组 / 总三元组 |
| **一致性** | 无冲突实体占比 | 1 - (冲突体 / 总实体) |
| **时效性** | 近期更新的实体占比 | 90 日内更新实体 / 总实体 |
| **唯一性** | 无重复定义实体占比 | 去重后实体 / 去重前实体 |

### 12.3 隔离区治理

未通过 SHACL 校验的三元组进入隔离区，提供：
- 拒绝原因说明
- 原始三元组展示
- 修复建议模板
- 人工操作：批准 / 拒绝 / 应用修复

---

## 13. 部署与运维

### 13.1 环境依赖

```
必备:
  - Python 3.11+       (后端)
  - Node.js 18+        (前端)
  - PostgreSQL 15+     (元数据+向量, 需 pgvector 扩展)
  - Apache Jena Fuseki (RDF 图存储, 通过 Docker 或本地 Java)

可选:
  - Docker / Docker Compose (一键启动全部服务)
```

### 13.2 启动方式

**本地开发：**
```bash
# 1. 配置环境变量
cp .env.example .env

# 2. 启动 Fuseki (Docker)
./scripts/fuseki.sh start

# 3. 启动后端
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端
cd frontend && npm run dev
```

**Docker 一键启动：**
```bash
./scripts/service.sh start docker
```

### 13.3 配置体系

环境变量 (`.env`) 管理 60+ 配置项，核心分类：

- **数据库** — `DATABASE_URL`, 连接池参数
- **LLM** — `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, 多连接配置
- **鉴权** — `API_AUTH_ENABLED`, `API_AUTH_TOKEN`
- **本体** — `FUSEKI_URL`, `ONTOLOGY_ENABLED`, `ONTOLOGY_NS`
- **Copilot** — 路由阈值、RRF 权重、候选表上限
- **语义** — 自动审批置信度、分块处理上限、流水线超时

### 13.4 运行目录约定

| 目录 | 用途 |
|------|------|
| `.run/` | 运行时状态 (日志、PID、Fuseki 数据)，不入库 |
| `run/` | 本地临时安装产物，不入库 |
| `scripts/` | 可复用脚本入口 |

---

## 14. 当前状态与演进路线

### 14.1 实现状态总结

| 能力 | 状态 | 说明 |
|------|------|------|
| 数据源连接与 Schema 分析 | ✅ 完成 | 多数据库支持，LLM 语义标注 |
| 文档摄入流水线 | ✅ 完成 | 文件/Git/API/手动/数据库多源 |
| LLM 语义抽取 (9 步) | ✅ 完成 | 术语/指标/维度/规则/关系/层级/血缘/Join/对齐 |
| TBox 本体模型 | ✅ 完成 | 三层架构、30+ 类、30+ 属性、11 SHACL Shape |
| OWL 2 RL 推理 | ✅ 完成 | 传递/对称闭包、逆属性、子类传递 |
| SHACL 守门 + 隔离区 | ✅ 完成 | 写入前校验、失败隔离、人工治理 |
| Copilot 本体路由 | ✅ 完成 | SPARQL 概念匹配 + 图扩展 + RRF 融合 |
| 五层语义资产浏览 | ✅ 完成 | 词汇/实体概念/关系/属性/规则 |
| DDL 约束 → OWL 公理 | ❌ 未实现 | NOT NULL/UNIQUE/FOREIGN KEY 未自动转换 |
| BI 元数据对齐 | ❌ 未实现 | Tableau/LookML 口径定义对接 |
| 本体版本迁移 | ⚠️ 部分 | 存在但未接入 orchestrator |
| 跨领域本体对齐 | ⚠️ 部分 | SBERT 基础设施已有，流程待完善 |

### 14.2 演进优先级

```
P0 (已完成)  → 交叉一致性校验：消除脏数据入图
P1 (2 周)   → TBox owl:Restriction 补充 + DatatypeProperty domain/range
P2 (3 周)   → SWRL 规则标准化 + 术语等价自动填充 + 层级循环检测
P3 (持续)   → 可视化增强 + 本体演化管理 + 跨领域对齐
```

---

## 附录

### A. 关键术语对照

| 缩写/术语 | 全称 | 说明 |
|----------|------|------|
| TBox | Terminological Box | 本体模式层（类、属性、公理） |
| ABox | Assertional Box | 本体实例层（具体术语、指标、表） |
| RBox | Role Box | 属性特征层（传递、对称、函数性） |
| RDF | Resource Description Framework | 三元组图数据模型 |
| OWL 2 RL | Web Ontology Language 2 RL Profile | 规则式本体推理语言 |
| SKOS | Simple Knowledge Organization System | 轻量概念体系 |
| SHACL | Shapes Constraint Language | RDF 图校验语言 |
| SPARQL | SPARQL Protocol and RDF Query Language | RDF 查询语言 |
| DQV | Data Quality Vocabulary | W3C 数据质量词汇表 |
| RRF | Reciprocal Rank Fusion | 多路检索结果融合算法 |
| Fuseki | Apache Jena Fuseki | RDF 三元组存储与 SPARQL 服务器 |
| SSE | Server-Sent Events | 服务端推送（流式响应） |
| SSOT | Single Source of Truth | 唯一真相源 |

### B. 参考文档索引

| 文档 | 说明 |
|------|------|
| [DataLens用户操作指南.md](DataLens用户操作指南.md) | 用户操作全流程 |
| [DataLens本体建模实现详情.md](DataLens本体建模实现详情.md) | 本体建模技术实现 |
| [本体建模理论标准.md](本体建模理论标准.md) | W3C 语义网理论基线 |
| [README.md](../README.md) | 快速入门与环境配置 |

### C. 关键文件索引

| 关注点 | 文件 |
|--------|------|
| 系统入口 | `backend/main.py:1-105` |
| 配置中心 | `backend/config.py:1-103` |
| ORM 模型 | `backend/models.py:1-480` |
| TBox 本体定义 | `backend/ontology/tbox/core.ttl` |
| SHACL 形状 | `backend/ontology/shacl/*.ttl` |
| 抽取编排 | `backend/services/extraction/orchestrator.py` |
| Copilot 路由 | `backend/services/copilot/router.py` |
| 本体写入 | `backend/services/ontology/writer.py` |
| SHACL 校验 | `backend/services/ontology/validator.py` |
| OWL 推理机 | `backend/services/ontology/reasoner.py` |
