# 企业本体建模：数据来源与自动化抽取

> 本文档定义企业本体建模的完整要素构成、各要素对应的企业真实数据来源，以及 DataLens 如何通过大模型在用户无感知的情况下完成从原始数据到可路由本体知识的全自动清洗。  
> **产品/UI 演进：** 见 [本体三层架构与 UI 优化方案](./ONTOLOGY_LAYER_UI_OPTIMIZATION.md)。

---

## 1. 项目的本体论目标

DataLens 的 Copilot 不是通用 ChatBot——它需要**精确回答企业数据分析问题**。要实现这一点，必须先回答三个问题：

1. **用户在说什么？**（术语对齐：用户说的"GMV"和数据库里的 `orders.amount` 是什么关系）
2. **应该查哪里？**（表路由：用户的问题应该查哪些表、用哪些指标）
3. **回答是否可信？**（可观测：生成的 SQL 用了哪些口径、经过了哪些推理步骤）

这三个问题分别对应本体的三类核心能力：

```
术语对齐（概念层）  →  用户语言 ↔ 企业语义  →  路由上下文注入
表路由（关系层）    →  概念 → 表 → 血缘扩展  →  SPARQL 图遍历
可观测（溯源层）    →  口径定义、来源锚定    →  回答可解释
```

---

## 2. 本体要素全景

一个完整的 OWL 2 企业本体由以下要素组成：

### 2.1 概念类（Classes）—— TBox 骨架

定义"企业里存在哪些事物"。

| 要素 | OWL 构造 | 含义 | 企业数据来源 |
|------|---------|------|-------------|
| 原子类 | `owl:Class` | 基本概念，如 `Customer`、`Order`、`Product` | 业务域建模（DDD 限界上下文）、概念数据模型（CDM）、业务能力模型 |
| 子类层级 | `rdfs:subClassOf` | `CorporateCustomer ⊑ Customer` | 产品分类树（SKU 层级）、客户分群规则、会计科目表、组织架构树 |
| 等价类 | `owl:equivalentClass` | `ActiveUser ≡ User ⊓ (loginCount ≥ 1)` | 跨部门口径对齐："财务部的'活跃用户'和产品部的是否等价" |
| 不相交类 | `owl:disjointWith` | `Employee ⊓ Customer ≡ ⊥` | 业务规则引擎、合规约束、数据质量规则 |
| 枚举类 | `owl:oneOf` | `OrderStatus ≡ {pending, paid, shipped, refunded}` | 代码表/字典表、状态机定义、CHECK 约束的合法值域 |

### 2.2 关系（Properties）—— 概念间的连线

| 要素 | OWL 构造 | 含义 | 企业数据来源 |
|------|---------|------|-------------|
| 对象属性 | `owl:ObjectProperty` | `places(Customer, Order)` — 客户下订单 | ER 模型关系线（1:1, 1:N, M:N）、业务流程模型的流转关系 |
| 数据属性 | `owl:DatatypeProperty` | `hasName(Customer, xsd:string)` | 物理表字段定义（列名 + 类型）、数据字典的字段说明 |
| 传递属性 | `owl:TransitiveProperty` | `locatedIn(A,B) ∧ locatedIn(B,C) → locatedIn(A,C)` | 组织架构汇报链、地理层级、科目汇总、物料 BOM |
| 对称属性 | `owl:SymmetricProperty` | `joinableWith(A,B) → joinableWith(B,A)` | 表 JOIN 条件（天然对称）、同一客户识别 |
| 函数属性 | `owl:FunctionalProperty` | 每个实例最多一个值，如 `hasBirthDate` | 主键约束、UNIQUE 约束、函数依赖（A → B） |
| 逆属性 | `owl:inverseOf` | `hasParent ≡ hasChild⁻¹` | BOM 父子件、组织上下级、科目汇总 ↔ 明细 |
| 子属性 | `rdfs:subPropertyOf` | `manages ⊑ reportsTo`（管理是汇报的子关系） | 权限模型、流程审批中的关系细化 |

### 2.3 约束（Axioms）—— 规则层

约束决定知识图谱的质量边界——什么可以成立，什么不可以。

| 要素 | OWL 构造 | 含义 | 企业数据来源 |
|------|---------|------|-------------|
| 域约束 | `rdfs:domain` | `places` 的 domain 是 `Customer` | 业务规则引擎（Drools/ILOG）、外键方向 |
| 值域约束 | `rdfs:range` | `hasStatus` 的 range 是 `OrderStatus` | 代码表取值范围、字段 CHECK 约束 |
| 基数约束 | `owl:cardinality` | `hasLegalRepresentative max 1` | 主键/NOT NULL、法律合规要求（法人唯一） |
| 存在约束 | `owl:someValuesFrom` | `Order ⊑ ∃hasCustomer` | NOT NULL、外键强制引用 |
| 全称约束 | `owl:allValuesFrom` | `VIPOrder ⊑ ∀hasItem.PremiumProduct` | 业务规则（大额交易必走审批）、风控规则 |
| 键约束 | `owl:hasKey` | `{countryCode, cityName}` 唯一标识城市 | 复合主键、联合唯一索引 |

### 2.4 实例（Individuals）—— ABox 事实层

| 要素 | OWL 构造 | 含义 | 企业数据来源 |
|------|---------|------|-------------|
| 实例断言 | `rdf:type` 即 `ClassAssertion` | `华为 : Customer` | MDM 主数据系统、CRM 客户主表、供应商主表 |
| 属性断言 | `PropertyAssertion` | `华为 位于 深圳` | 主数据属性列、数仓维度表的行数据 |
| 同一性 | `owl:sameAs` | `cust_12345 ≡ cust_HW`（两个系统的"华为"是同一个） | MDM 的 ID 映射表、实体解析/身份匹配结果 |
| 差异性 | `owl:differentFrom` | `华为 ≠ 中兴` | 去重逻辑、主数据"黄金记录"判定 |

### 2.5 对齐层（Alignment）—— 跨本体映射

| 要素 | OWL/SKOS 构造 | 含义 | 企业数据来源 |
|------|-------------|------|-------------|
| 概念等价 | `owl:equivalentClass` | 本企业 `Customer` ↔ FIBO 标准 `PartyInRole` | 行业标准本体（FIBO 金融、ISO 20022、schema.org） |
| 近似映射 | `skos:closeMatch` / `skos:exactMatch` | 本企业"营业收入" ≈ 税务口径"应税收入" | 监管报送映射表（1104、EAST）、企业间 EDI 数据交换协议 |
| 版本/弃用 | `owl:deprecated` | `SAP_ORDER_TYPE_A` 已停用 | 系统退役记录、数据迁移文档、变更管理日志 |

---

## 3. 企业原始数据 → 本体要素的映射矩阵

```
                 TBox(概念)  属性/关系  约束     ABox(实例)  对齐
                 ────────  ────────  ────    ────────  ────
数据字典/Wiki      ████      ████      ██               ██
BI 工具元数据      ████      ████      ████
KPI / 制度文件     ████                ████
需求文档 (BRD)    ████      ████
ETL / dbt 代码              ████████  ████
数据仓库元数据              ████      ████████
CDC / 同步配置              ████████
建模工具 (PDM)    ████████  ████████  ████
主数据 (MDM)                                    ████████  ████
行业标准          ████████                                ████████
组织架构                            ████
代码表/字典表      ██                            ██
数据库 DDL                  ████      ████████
```

### 核心观察

**企业中大量本体要素是隐性的**——它们不存储为 RDF/OWL，而是隐藏在以下载体中：

- **外键约束** → 对象属性在物理层的投影
- **CHECK 约束** → 基数约束和值域约束的投影
- **JOIN 条件** → 传递属性、对称属性的投影
- **聚合 SQL** → 指标口径公式的投影
- **枚举注释** → 枚举类的投影

本体建模的核心工作**不是从零创造**，而是从这些隐性、分散、异构的表达中，将本体要素逆向抽取出来。

---

## 4. DataLens 的自动化抽取方案

### 4.1 设计原则

DataLens 的目标是让用户在**无感知**的情况下完成本体构建：

```
用户操作:  上传文档 → 关联数据源 → 提问
            ↓           ↓           ↓
系统自动:  语义抽取     Schema 采集   本体路由
            ↓           ↓           ↓
用户感知:  术语自动出现  表自动关联   准确的 SQL 回答
```

### 4.2 输入层：三类原始数据

| 输入类型 | 具体来源 | 采集方式 |
|---------|---------|---------|
| **文档** | PDF、Word、Markdown、Confluence、飞书文档 | 文件上传 / API 同步 / Git 仓库同步 |
| **代码** | SQL 存储过程、dbt 模型、Spark/PySpark、Python ORM | Git 仓库同步 → KnowledgeEntry |
| **数据库元数据** | information_schema、Hive Metastore | JDBC 连接器自动采集 → TableMeta / ColumnMeta |

### 4.3 抽取层：五阶段 LLM 流水线

所有抽取通过 LLM 完成，用户无需任何标注或配置：

```
阶段 1: 术语提取（term_extractor）
  输入: DocumentChunk（已索引的文档分块）
  提示: term_extraction_system.txt
  产出: BusinessTerm 三元组
  ┌─────────────────────────────────────┐
  │ rdf:type         dl:BusinessTerm    │
  │ skos:prefLabel   "GMV"              │
  │ skos:definition  "成交总额..."       │
  │ dl:termType      "metric"           │
  │ dl:confidence    "85.0"             │
  │ dl:mapsToColumn  (关联物理列)        │
  │ skos:altLabel    "Gross Merchandise"│
  └─────────────────────────────────────┘

阶段 2: 指标口径提取（metric_extractor）
  输入: DocumentChunk + table_refs
  提示: metric_extraction_system.txt
  产出: Metric 三元组
  ┌─────────────────────────────────────┐
  │ rdf:type             dl:Metric      │
  │ skos:prefLabel       "日GMV"        │
  │ dl:formula           "SUM(amount)..."│
  │ dl:caliber           "仅含已支付..."  │
  │ dl:computedFromTable data:table/42  │
  │ dl:derivedFrom       (父指标IRI)     │
  │ dl:aggregatesOver    (维度IRI)       │
  └─────────────────────────────────────┘

阶段 3: 关系提取（relation_extractor）
  输入: 文档 + 已提取的概念列表
  提示: relation_extraction_system.txt
  产出: 语义关系边
  ┌─────────────────────────────────────┐
  │ dl:dependsOn  (概念A 依赖 概念B)      │
  │ skos:related  (概念A 关联 概念B)      │
  │ dl:derivedFrom (指标A 派生自 指标B)   │
  └─────────────────────────────────────┘

阶段 4: 层级构建（hierarchy_builder）
  输入: 已知概念名称列表
  提示: hierarchy_extraction_system.txt
  产出: SKOS 层级边
  ┌─────────────────────────────────────┐
  │ skos:broader   (子概念 → 父概念)     │
  │ skos:narrower  (父概念 → 子概念)     │
  │ skos:related   (跨层级关联)          │
  │ 安全: 无自环, 最大深度6, 概念必须存在 │
  └─────────────────────────────────────┘

阶段 5: 血缘提取（lineage_extractor）
  输入: KnowledgeEntry（Git 代码文件）
  提示: lineage_extraction_system.txt
  产出: LineageAssertion 三元组
  ┌─────────────────────────────────────┐
  │ rdf:type          dl:LineageAssertion│
  │ dl:transformsFrom (源表 → 目标表)     │
  │ dl:layer          "ODS/DWD/DWS/ADS" │
  │ dl:sourceField    (源字段)           │
  │ dl:targetField    (目标字段)          │
  │ dl:transformLogic (转换逻辑描述)      │
  └─────────────────────────────────────┘
```

### 4.4 写入层：clean → SHACL → production / quarantine

```
RawTriple 列表
  │
  ├── 阶段 1: clean_triples()
  │     ├── 语法清洗 (TTL 转义)
  │     ├── 链接校验 (object_is_uri 一致性)
  │     ├── TBox 校验 (类型与属性 domain 匹配)
  │     ├── 去重 (同 subject-predicate-object 合并)
  │     └── 状态门 (draft 不入 production)
  │
  ├── 阶段 2: SHACL 校验
  │     ├── BusinessTerm 必须含 skos:prefLabel
  │     ├── Metric 必须含 dl:formula
  │     ├── PhysicalTable 必须含 dl:platformId
  │     └── ...
  │
  ├── 通过 → production graph  (graph/kb/{id})
  └── 失败 → quarantine graph (graph/quarantine/{id})
```

### 4.5 推理层：OWL 2 RL 增量推理

写入 production 后触发增量推理：

| 推理类型 | 作用属性 | 推理效果 |
|---------|---------|---------|
| 传递闭包 | `dl:derivedFrom`、`dl:transformsFrom`、`dl:exactMatch` | A→B, B→C ⇒ A→C |
| 对称闭包 | `dl:joinableWith`、`dl:exactMatch` | A↔B ⇒ B↔A |
| 逆属性 | `skos:broader` ↔ `skos:narrower` | A broader B ⇒ B narrower A |

推理结果写入 `inferred graph`（不污染 production graph）。

---

## 5. 消费层：如何服务于 Copilot 路由与可观测回答

### 5.1 路由流程

```
用户问题: "上个月华东区的GMV是多少？"
  │
  ├── 1. 概念匹配 (OntologyRouter.route_concepts)
  │      SPARQL: REGEX(?label, "GMV", "i") + REGEX(?label, "华东", "i")
  │      → dl:BusinessTerm "GMV" (confidence=85)
  │      → dl:Metric "GMV" (formula="SUM(orders.amount)...")
  │
  ├── 2. 表路由 (OntologyRouter.route_tables)
  │      概念 → dl:computedFromTable → data:table/42
  │      → PhysicalTable "orders" (platformId=42)
  │
  ├── 3. 血缘扩展 (OntologyRouter.expand_lineage)
  │      data:table/42 → dl:joinableWith → data:table/56("order_items")
  │      候选表: [42, 56]
  │
  ├── 4. 上下文组装 (ContextAssembler.build_context)
  │      注入 LLM prompt:
  │      ├── 术语定义: "GMV = 成交总额..."
  │      ├── 指标口径: "SUM(orders.amount) WHERE status='paid'"
  │      ├── 相关表: orders (platformId=42), order_items (56)
  │      └── 表结构: orders(id, amount, status, created_at...)
  │
  └── 5. SQL 生成 + 执行
        生成的 SQL 引用了正确的表、使用了正确的口径
        可追溯: 每个概念选择、表扩展都有 trace 记录
```

### 5.2 可观测层

每个 Copilot 回答附带完整的路由 trace：

```
routing_trace:
  ├── matched_concepts:     [{term: "GMV", iri: "...", confidence: 85}]
  ├── routed_tables:        [{table: "orders", via: "computedFromTable"}]
  ├── expanded_tables:      [{table: "order_items", via: "joinableWith"}]
  ├── context_sections:     [terms, metrics, tables, schema]
  └── strategy:             "ontology_sparql"
```

用户可以看到**每个回答使用了哪些概念、哪些表、哪些口径**，从而实现完整的可观测性。

---

## 6. 企业落地的核心难题

| 难题 | 本质 | 当前应对 |
|------|------|---------|
| **文档与代码不一致** | KPI 手册写"有效订单 = paid"，SQL 里还加了 `AND refund_flag=0` | 置信度标记 + 来源锚定（`dl:groundedBy` 指向 source chunk），暴露不一致 |
| **同义词泛滥** | 市场部说"GMV"，财务部说"成交额"，运营部说"总流水" | `skos:altLabel` + `skos:exactMatch` 对齐，路由时多词匹配 |
| **存量资产沉默** | BI 工具的 LookML、Tableau 工作簿中藏着大量口径定义 | 目前仅支持文档 + 代码，BI 元数据对接是明确缺口 |
| **推理 vs 现实的鸿沟** | 本体推理可以推出 A→C 的传递血缘，但现实中可能存在例外 | 推理结果保留在 inferred graph，production graph 只存事实 |
| **冷启动问题** | 没有文档就没有本体，新企业接入门槛高 | 数据库元数据自动采集提供基础的 PhysicalTable 骨架 |

---

## 7. 与企业现有系统的关系

DataLens 不取代任何现有系统，而是作为一个 **语义聚合层**：

```
┌─────────────────────────────────────────────┐
│                  DataLens 本体层             │
│  (RDF 知识图谱 — 术语/指标/血缘/层级)          │
├─────────────────────────────────────────────┤
│  聚合自:                                     │
│  ┌──────────┬──────────┬──────────┬───────┐  │
│  │ 数据字典  │ BI 工具   │ ETL 代码 │ 数据库 │  │
│  │ (Confluence)│(Tableau)│ (dbt)    │(PG/Hive)│ │
│  └──────────┴──────────┴──────────┴───────┘  │
│                                              │
│  服务于:                                      │
│  ┌──────────┬──────────┬──────────────────┐  │
│  │ Copilot  │ 数据治理  │ 口径对齐/冲突发现 │  │
│  │ 问答路由  │ 影响分析  │                  │  │
│  └──────────┴──────────┴──────────────────┘  │
└─────────────────────────────────────────────┘
```

---

*最后更新：2026-05-26*
