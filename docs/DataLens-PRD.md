# DataLens 产品需求文档 (PRD)

## 1. 产品概述

### 1.1 产品定位

DataLens 是一个 **LLM 驱动的企业级语义知识图谱平台**，核心定位为轻量级 ChatBI（对话式商业智能）系统。它连接企业异构数据源，自动理解表结构与字段的业务含义，构建以 RDF 知识图谱为核心的业务语义知识库，让用户用自然语言提问并获得精确的 SQL 查询结果。

### 1.2 一句话描述

**智能数据理解与自然语言分析系统**——填补"数据库里有什么"和"用户想问什么"之间的语义鸿沟。

### 1.3 解决的三个核心问题

| 问题 | 描述 | 解决方案 |
|------|------|----------|
| **术语对齐** | 用户说的"GMV"对应数据库中哪个字段？ | 从文档中自动提取术语，通过本体映射建立术语与物理字段的关联 |
| **表路由** | 用户的问题应该查询哪些表？ | SPARQL 图遍历 + 向量检索 + RRF 融合排序，多信号路由 |
| **回答可信** | 生成的 SQL 用了什么口径？经过什么推理？ | 全链路可观测追踪：概念匹配 → 表路由 → 血缘扩展 → SQL 推导 |

---

## 2. 目标用户与场景

### 2.1 目标用户

| 角色 | 描述 | 核心需求 |
|------|------|----------|
| **业务分析师** | 需要从数据库取数但不会写 SQL | 用自然语言提问，获得准确的数据查询结果 |
| **数据工程师** | 维护数据仓库和 ETL 管线 | 快速理解表结构、字段含义和表间血缘关系 |
| **知识管理员** | 负责企业数据字典和业务口径维护 | 将散落在文档中的业务知识结构化、可检索、可追溯 |
| **管理层** | 需要即席查询和数据洞察 | 对关键业务指标进行即席提问，获得可信答案 |

### 2.2 典型使用场景

1. **即席查询**：分析师问"上个月华东区的GMV是多少？"，系统自动定位表、生成并执行 SQL，返回结果
2. **口径查询**：用户问"我们怎么定义活跃用户的？"，系统从知识库中检索对应的指标定义和计算逻辑
3. **知识沉淀**：将企业文档（飞书/Notion/Confluence）、Git 仓库中的业务规范自动抽取为结构化术语和指标定义
4. **数据库探索**：连接新的数据库后，自动分析表结构，生成业务含义描述

---

## 3. 功能需求

### 3.1 数据源连接管理

**FR-1.1** 支持多种数据库类型连接：MySQL、MariaDB、Doris、StarRocks、PostgreSQL、Greenplum、SQL Server、SQLite、ClickHouse、Trino、Hive

**FR-1.2** 提供连接测试功能，验证连接可用性

**FR-1.3** 自动抽取数据库元数据（Schema、表结构、列信息、DDL、数据采样）

**FR-1.4** 支持手动触发元数据刷新

### 3.2 知识库管理

**FR-2.1** 支持创建和管理多个独立知识库（对应不同业务领域或项目）

**FR-2.2** 知识摄入来源支持：
- 文件上传（PDF、Word、Excel、Markdown、TXT）
- Git 仓库（GitHub / GitLab），支持 cron 定时同步
- API 集成（Notion、Confluence、飞书）
- 数据库 Schema 导入

**FR-2.3** 语义清洗流水线：文本抽取 → 清洗 → 语义分块 → 语义结构化 → 向量嵌入

**FR-2.4** 文档处理状态追踪（待处理 → 抽取中 → 清洗中 → 分块中 → 嵌入中 → 已索引 → 失败）

### 3.3 本体建模（核心能力）

**FR-3.1** LLM 驱动的知识抽取，自动从文档中提取：
- 业务术语/概念（Term Extraction）
- 指标定义（Metric Extraction）
- 维度定义（Dimension Extraction）
- 业务关系（Relation Extraction）
- 业务规则/约束（Rule Extraction）
- 类层次结构（Hierarchy Building）
- 数据血缘（Lineage Extraction）
- 表连接关系（Join Extraction）
- 跨知识库等价对齐（Cross-KB Equivalence）
- 领域特定术语（Domain Term Extraction）

**FR-3.2** 双层本体架构：
- **领域本体层**：面向特定业务域（如营销、财务、供应链），管理域内共享的术语、指标、维度
- **知识库本体层**：单知识库内的语义资产，包含表映射、口径定义等具体实现

**FR-3.3** 本体存储：Apache Jena Fuseki 作为主 RDF 存储，rdflib 内存图作为回退

**FR-3.4** 本体质量保障：
- SHACL 形状验证
- OWL 推理闭包
- 质量隔离区（低置信度三元组）
- 来源追踪（Provenance）

**FR-3.5** 本体资产浏览：按五层分类组织（实体概念、关系、规则、属性、词汇表）

**FR-3.6** 建模与质量与语义资产的局部-整体关系：

DataLens 本体层包含两组功能界面，分别对应本体资产的**局部视角**和**整体视角**：

| 维度 | 建模与质量（局部） | 语义资产（整体） |
|------|-------------------|-------------------|
| **作用域** | 单个知识库 | 业务域（跨知识库聚合） |
| **路由** | `/knowledge-bases/{id}/modeling-quality` | `/ontology`（或 `/business-domains/{id}/ontology`） |
| **核心功能** | 语义清洗流水线、五层清洗结果、SHACL 验证、隔离区治理 | 五层语义资产浏览、来源追溯、图谱可视化 |
| **子视图** | "五层结果" + "质量与隔离"两个子标签 | "概览" + "语义资产" + "物理资产" + "图谱"四个标签 |
| **操作权限** | 可写（触发清洗、审核隔离项、修改状态） | 只读（浏览已入图的通过审核资产） |
| **数据来源** | 当前 KB 的 RDF 命名图（含生产图 + 隔离图） | 领域内所有 KB 的 RDF 生产图（跨图聚合） |
| **后端入口** | `routers/ontology.py`（`/api/ontology/knowledge-bases/{kb_id}/*`） | `routers/domain_ontology.py`（`/api/business-domains/{domain_id}/ontology/*`） |

**数据流转关系**：

```
导入源（文档/Git/DB Schema）
  → 语义清洗流水线（P0 建模流水线）
    → 五层实体抽取（术语/指标/维度/规则/关系/属性 + 层次/血缘/JOIN）
      → 本体写入器（OntologyWriter）
        → SHACL 校验
          ├─ 通过 → 写入生产图 → 语义资产浏览可见
          └─ 未通过 → 写入隔离图 → 建模与质量"隔离区"待审核
```

**五层分类体系**（建模与质量、语义资产两模块共享同一分类标准）：

| 层 Key | 中文名 | 包含的 OWL 类型 | 说明 |
|--------|--------|----------------|------|
| `entity-concept` | 实体概念层 | BusinessTerm, Metric, Dimension, BusinessConcept | 含层级关系的语义实体，维度作为子视图嵌入展示 |
| `relation` | 关系层 | ObjectProperty 边 | 实体间的语义关系 |
| `rule` | 规则层 | Metric, BusinessRule | 指标口径与业务规则 |
| `attribute` | 属性层 | DatatypeProperty 值 | 表/字段的数据属性（如 businessSummary） |
| `vocabulary` | 词汇层 | BusinessTerm | 业务术语定义（不含层级） |

> **注**：内部实现维护 6 层（含 `dimension` 维度层），对外展示为 5 层。`dimension` 层在"实体概念"层中以「维度」子视图呈现。`entity-concept` 层使用连字符 `-` 作为标准键名；后端 `modeling_status.py`、`modeling_layers.py`、`domain_aggregation.py` 共用统一的 `LAYER_KEYS`。

**一致性规范**：

1. 建模与质量使用 6 层 SPARQL 查询（`modeling_layers.py` LAYER_KEYS），`modeling_status.py` 的 `layers_summary` 字段需补齐全部 6 层计数
2. 领域聚合时 `_LAYERS_WITH_GROUNDING` 覆盖全部 6 层，确保 `relation` 和 `attribute` 层条目也携带来源追溯（`origin`）
3. 前端两处五层列定义（`DomainFiveLayerBrowse.tsx` 与 `OntologyLayerDetailPanel.tsx`）保持对齐：词汇层应含同义词列，属性层应含名称列
4. 层键名统一使用连字符 `entity-concept`（非下划线 `entity_concept`），前端通过 `normalizeModelingLayerKey()` 兼容别名输入

### 3.4 Copilot 自然语言查询（核心功能）

**FR-4.1** 对话式问答界面，支持多轮对话上下文

**FR-4.2** 端到端查询流水线：

| 步骤 | 功能 | 说明 |
|------|------|------|
| 1 | 意图识别 | LLM 分类：sql_query / general_qa |
| 2 | 本体知识匹配 | 问题 → RDF 术语/指标/物理表 |
| 3 | NLP 预处理 | 时间解析、维度值提取、计算模式检测 |
| 4 | 上下文组装 | 知识库检索 + 表嵌入相似度 + 列扩展 + 血缘扩展 + RRF 融合 |
| 5 | SQL 生成 | 分层提示词：本体映射 > Schema > 知识库 > 少样本示例 |
| 6 | SQL 安全校验 | 基于 sqlglot AST 的只读验证，禁止写操作 |
| 7 | 执行与修复 | 执行 SQL，失败时最多 3 次自动修复 |
| 8 | 结果展示 | 表格 + CSV 导出，附 SQL 语句 |

**FR-4.3** 通用问答：对非 SQL 类问题（口径定义、业务概念解释），从知识库检索回答

**FR-4.4** 表分析：自动对表和列生成业务含义描述

### 3.5 可观测性与追踪

**FR-5.1** Copilot 执行追踪：记录流水线每一步的输入、输出和决策理由

**FR-5.2** 路由追溯：展示概念匹配、表路由评分、血缘扩展路径

**FR-5.3** SQL 归因：展示生成的 SQL 使用了哪些口径和知识条目

### 3.6 业务域管理

**FR-6.1** 支持创建和管理多个业务域（如营销、财务、供应链）

**FR-6.2** 业务域自动路由：基于问题语义相似度自动选择目标域

**FR-6.3** 业务域与知识库的多对多关联

**FR-6.4** 域内本体资产独立浏览

### 3.7 LLM 连接管理

**FR-7.1** 支持配置多个 LLM 连接（厂商、模型、API Key、代理）

**FR-7.2** 默认支持 DeepSeek 和 OpenAI

**FR-7.3** 可针对不同任务选择不同模型

---

## 4. 非功能需求

### 4.1 性能

- Copilot 查询响应采用 SSE 流式传输，首字节时间 < 3 秒
- 向量检索响应时间 < 500ms
- 知识抽取支持异步后台处理

### 4.2 安全性

- Bearer Token 认证中间件
- SQL 生成后基于 AST 的只读安全校验（禁止 INSERT / UPDATE / DELETE / DROP / TRUNCATE / ALTER）
- 连接凭证加密存储

### 4.3 可扩展性

- 本体层支持跨域扩展，企业本体 → 领域本体 → 知识库本体自上而下继承
- 数据源连接器可插拔扩展
- LLM 厂商可配置替换

### 4.4 可靠性

- 本体写入支持事务（Fuseki 命名图粒度）
- SHACL 验证 + 隔离区机制确保本体质量
- SQL 执行失败时自动修复重试（最多 3 次）

### 4.5 可维护性

- Docker Compose 一键部署
- Alembic 数据库迁移管理
- 结构化日志输出

---

## 5. 系统架构

### 5.1 总体架构

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (Next.js 14)              │
│              http://localhost:3000                   │
└────────────────────────┬────────────────────────────┘
                         │ HTTP / SSE Streaming
┌────────────────────────▼────────────────────────────┐
│               Backend (FastAPI)                      │
│              http://localhost:8000                   │
│                                                      │
│  ┌──────────┬──────────┬──────────┬──────────────┐  │
│  │ 路由层   │ Copilot  │ 抽取编排 │ 本体层       │  │
│  │ (17模块) │ 流水线   │ (10种)   │ R/W/推理     │  │
│  └──────────┴──────────┴──────────┴──────────────┘  │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
┌──────────▼──────────┐  ┌─────────▼──────────────┐
│  PostgreSQL 16       │  │  Apache Jena Fuseki     │
│  + pgvector (1536d)  │  │  (RDF 三元组存储)       │
│                      │  │  + SPARQL 查询          │
│  • 元数据            │  │  + SHACL 验证           │
│  • 文档/知识条目     │  │  + OWL 推理             │
│  • 向量嵌入          │  │                         │
│  • 业务域            │  │                         │
│  • 配置              │  │                         │
└─────────────────────┘  └─────────────────────────┘
```

### 5.2 逻辑分层

```
┌───────────────────────────────────────────────────┐
│       语义资产浏览层（Semantic Assets - 整体）      │
│  实体概念 | 关系 | 规则 | 属性 | 词汇表             │
│  作用域：业务域（跨知识库聚合）                     │
│  入口：/ontology → DomainFiveLayerBrowse           │
├───────────────────────────────────────────────────┤
│     建模与质量层（Modeling & Quality - 局部）       │
│  ┌─────────────────┬─────────────────────────────┐ │
│  │ 五层结果         │ 质量与隔离                   │ │
│  │ · 清洗结果卡片   │ · SHACL 通过率               │ │
│  │ · 分层明细列表   │ · 隔离区待办                 │ │
│  │ · 层级树形视图   │ · 置信度分布                 │ │
│  │ 入口：KbModeling │ 入口：KbModelingQualityPanel │ │
│  │       QualitySection                          │ │
│  └─────────────────┴─────────────────────────────┘ │
│  作用域：单个知识库                                 │
├───────────────────────────────────────────────────┤
│        建模流水线层（Modeling Pipeline）            │
│  术语抽取 → 指标抽取 → 维度抽取 → 规则抽取 →       │
│  关系抽取 → 层次构建 → 血缘抽取 → JOIN 抽取 → 入图  │
├───────────────────────────────────────────────────┤
│         导入层（Evidence Package）                  │
│  文件上传 | Git仓库 | API源 | DB Schema 导入        │
└───────────────────────────────────────────────────┘
```

### 5.3 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| **前端框架** | Next.js (App Router) + React + TypeScript | 14.2 / 18.3 / 5.5 |
| **UI 框架** | Tailwind CSS | 3.4 |
| **后端框架** | FastAPI + Uvicorn | 0.111 / 0.30 |
| **ORM** | SQLAlchemy | 2.0 |
| **数据库** | PostgreSQL + pgvector | 16 |
| **RDF 存储** | Apache Jena Fuseki + rdflib | 最新 |
| **本体验证** | pyshacl + owlrl | 最新 |
| **SQL 解析** | sqlglot | 30.7 |
| **LLM** | DeepSeek (主) / OpenAI (备) | - |
| **容器化** | Docker Compose | - |

---

## 6. 核心工作流

### 6.1 知识库初始化和知识摄入

```
1. 创建知识库
   └─ 2. 添加知识来源（文件/Git/API/Schema）
        └─ 3. 触发语义清洗流水线
             ├─ 文本抽取（PDF/Word/Excel/Markdown）
             ├─ 文本清洗
             ├─ 语义分块
             ├─ 语义结构化（LLM）
             └─ 向量嵌入 → pgvector
                  └─ 4. 本体抽取流水线
                       ├─ 术语/概念抽取
                       ├─ 指标/维度抽取
                       ├─ 关系/规则抽取
                       ├─ 层次结构构建
                       └─ 写入 RDF 图 → Fuseki
                            └─ 5. SHACL 验证 → 隔离区审核
```

### 6.2 Copilot 查询流程

```
用户输入自然语言问题
  → 意图识别 (SQL / 问答)
    → 本体匹配 (问题 → 术语/指标/表)
      → 表路由 (图遍历 + 向量 + RRF)
        → 上下文组装 (Schema + 知识条目 + 血缘)
          → SQL 生成 (分层提示词)
            → SQL 安全校验 (sqlglot AST)
              → 执行 (数据库)
                → 结果返回 + 可观测追踪
```

### 6.3 本体双层架构

```
领域本体 (Domain Ontology)
  ├─ 营销领域：GMV、CTR、转化率
  ├─ 财务领域：应收账款、毛利率
  └─ 供应链：库存周转、履约率
       │
       ▼
知识库本体 (Knowledge Base Ontology)
  ├─ 具体表映射 (orders.amount ↔ GMV)
  └─ 口径定义 (GMV = SUM(orders.amount) WHERE status = 'paid')
```

跨域等价对齐通过 SKOS 映射词汇表（`skos:exactMatch`、`skos:closeMatch` 等）实现，不再需要独立的企业本体层。

---

## 7. 数据模型概要

### 7.1 关系型数据（PostgreSQL）

核心实体关系：

- **DataSource** ──1:N── **TableMeta** ──1:N── **ColumnMeta**
- **KnowledgeBase** ──1:N── **KnowledgeEntry** / **Document**
- **Document** ──1:N── **DocumentChunk**（带 1536 维向量）
- **BusinessDomain** ──N:M── **KnowledgeBase** / **DataSource**
- **KnowledgeBase** ──1:N── **KnowledgeGitSource** / **KnowledgeApiSource** / **KnowledgeDatabaseImport**

### 7.2 图数据（Fuseki RDF）

以 W3C 标准 RDF 三元组存储：
- 命名空间：skos、owl、rdfs、dcterms、prov、shacl
- 自定义命名空间：datlens（实体概念）、datlens-relation（关系）、datlens-rule（规则）
- 命名图（Named Graph）粒度的 CRUD 和版本管理

---

## 8. 部署说明

### 8.1 环境要求

- Docker 和 Docker Compose
- Python 3.11+（本地开发）
- Node.js 20+（前端开发）
- PostgreSQL 16（含 pgvector 扩展）

### 8.2 Docker Compose 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| db | 5432 | PostgreSQL 16 |
| fuseki | 3030 | Apache Jena Fuseki |
| backend | 8000 | FastAPI 后端 |
| frontend | 3000 | Next.js 前端 |

### 8.3 核心配置项（环境变量）

- `LLM_PROVIDER`：LLM 厂商（deepseek / openai）
- `LLM_API_KEY`：LLM API 密钥
- `LLM_BASE_URL`：LLM API 地址
- `DATABASE_URL`：PostgreSQL 连接字符串
- `FUSEKI_URL`：Fuseki SPARQL 端点
- `API_AUTH_TOKEN`：API 认证令牌

---

## 9. 路线图

### P0 - 已完成
- [x] 多数据源连接与元数据抽取
- [x] 知识库管理与文档摄入
- [x] LLM 驱动的本体抽取（术语/指标/维度/关系/规则/层次/血缘）
- [x] Copilot 自然语言查询（意图识别 → 表路由 → SQL 生成 → 安全校验 → 执行）
- [x] 本体三层架构与 RDF 图存储
- [x] SSE 流式查询响应
- [x] SQL 只读安全校验
- [x] 执行追踪与可观测性
- [x] 业务域管理与自动路由

### P1 - 规划中
- [ ] 本体跨知识库等价对齐增强
- [ ] 查询结果可视化（图表/仪表盘）
- [ ] 用户反馈闭环（结果点赞/踩，持续优化路由）
- [ ] 多租户权限体系
- [ ] 查询缓存与预计算

### P2 - 远期
- [ ] 自然语言 → 本体查询（NL2SPARQL）
- [ ] 实时数据源 CDC 集成
- [ ] 移动端适配
- [ ] 开放 API 与 Webhook

---

## 10. 术语表

| 术语 | 定义 |
|------|------|
| **本体 (Ontology)** | 对业务领域中概念、关系、规则的形式化描述，使用 RDF/OWL 表示 |
| **建模与质量 (Modeling & Quality)** | 知识库级别的本体治理界面（局部视角），包含语义清洗流水线、五层清洗结果、SHACL 验证和隔离区审核 |
| **语义资产 (Semantic Assets)** | 业务域级别的本体资产浏览界面（整体视角），聚合域内所有知识库的已入图资产，按五层分类组织和追溯来源 |
| **RDF** | Resource Description Framework，W3C 知识图谱标准 |
| **SPARQL** | RDF 图查询语言，类似 SQL for graphs |
| **SHACL** | Shapes Constraint Language，RDF 图数据验证标准 |
| **OWL** | Web Ontology Language，支持逻辑推理的本体语言 |
| **Fuseki** | Apache Jena 的 SPARQL 服务器，RDF 存储与查询引擎 |
| **RRF** | Reciprocal Rank Fusion，多路排序结果融合算法 |
| **SSE** | Server-Sent Events，服务端到客户端的单向实时数据推送 |
| **pgvector** | PostgreSQL 向量扩展，支持向量相似度检索 |
| **证据包 (Evidence Package)** | 导入层的原始数据单元，包含文档、代码等未结构化的信息来源 |
| **命名图 (Named Graph)** | RDF 中通过 URI 标识的子图，在 DataLens 中用于版本管理和隔离 |
| **隔离区 (Quarantine)** | 未通过 SHACL 验证的三元组存储区域，需人工审核后决定通过或拒绝 |
