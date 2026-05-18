# DataLens 语义知识库 - AI-Readable UI Specification

> 本文档将 DataLens 语义知识库的 UI 设计整理为结构化规范，供 AI 模型理解、设计评审和代码实现使用。
> 设计版本：V2（基于资料源驱动的交互模型）
> 最后更新：2026-05-18

---

## 一、产品概述

### 1.1 产品定位
DataLens 语义知识库是一个企业级语义层构建工具，帮助数据团队将散落在代码、文档、数据库中的业务语义提取、清洗、组织为可被 AI 理解的语义资产，服务于 NL2SQL、Copilot 等下游 AI 应用。

### 1.2 核心价值
- 多源异构资料统一管理（Notion/飞书/GitHub/数据库/人工）
- 按资料源类型自动选择清洗策略
- 清洗结果统一呈现，支持溯源
- 数据血缘仅从代码库自动解析

### 1.3 用户角色
- **数据工程师**：管理资料源、配置清洗策略
- **业务分析师**：审核/补充术语和指标口径
- **AI 应用开发者**：消费语义资产（API/RAG）

---

## 二、页面结构

产品共 2 类页面：

| 页面 | 路由 | 说明 |
|------|------|------|
| 资料库总览页 | `/` | 所有资料源卡片 + 全局清洗结果 |
| 资料源详情页 | `/source/:id` | 单个资料源的清洗流水线 + 产出 |

---

## 三、资料库总览页

### 3.1 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  ◈ DataLens     [语义知识库] [Copilot] [数据源] [设置]  │  ← 顶部导航 (56px)
│                                        4个资料源 术语:45 │
├─────────────────────────────────────────────────────────┤
│  📥 资料库  — 点击卡片进入清洗详情              [+ 添加] │  ← Section Header
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 📄 产品PRD│ │ 📋 数据Wiki│ │ 💻 data- │ │ 🗄️ PG订单│   │
│  │ Notion   │ │ 飞书     │ │ warehouse│ │ 直连     │   │  ← 资料卡片区
│  │ ✓已同步  │ │ ✓已同步  │ │ ⟳同步中  │ │ ✓已连接  │   │
│  │ 术语12  │ │ 术语18  │ │ 术语8指标3│ │ 表理解23 │   │
│  │ 指标5   │ │ 指标8   │ │ 表12血缘10│ │ 字段312  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌─────────────────────────────┐            │
│  │ ✍️ 人工补充│ │ ➕ 添加新资料源               │            │
│  │ 术语28  │ │                              │            │
│  └──────────┘ └─────────────────────────────┘            │
├─────────────────────────────────────────────────────────┤
│  ─────────────── 分隔线 ──────────────────────────────   │
├─────────────────────────────────────────────────────────┤
│  📊 清洗结果  数据血缘仅在代码库详情页展示    [🔍搜索]   │  ← Section Header
├─────────────────────────────────────────────────────────┤
│  [📑 术语45] [📏 指标18] [📋 表理解23] [🏷️ 字段312]   │  ← Tab Bar
├─────────────────────────────────────────────────────────┤
│  术语    类型      定义         关联字段     来源    置信度 │  ← Table
│  GMV    💰度量    所有订单金额... orders.amount  📄PRD  92%  │
│  实收金额 💰度量   已支付订单... payments.amount 📋Wiki 95%  │
│  订单状态 📋枚举   订单当前...    orders.status  💻代码 98%  │
│  ...                                                       │
├─────────────────────────────────────────────────────────┤
│  文档:2源  代码:1源  数据库:1源  人工:28条 术语:45 指标:18│  ← Footer Stats
└─────────────────────────────────────────────────────────┘
```

### 3.2 组件规范

#### 3.2.1 资料卡片 (SourceCard)

**数据结构**
```
SourceCard {
  id: string
  type: "notion" | "feishu" | "github" | "database" | "manual" | "external"
  title: string
  subtitle: string
  syncStatus: "synced" | "syncing" | "pending"
  lastSyncTime: string
  meta: {
    docCount?: number
    sqlCount?: number
    tableCount?: number
    fieldCount?: number
  }
  tags: string[]           // ["📄 业务文档"] | ["💻 代码库", "dbt"]
  cleaningPills: Pill[]    // 显示该源已完成的清洗环节
  onClick: navigate(`/source/${id}`)
}
```

**Pill 数据结构**
```
Pill {
  label: string            // "术语提取" | "指标口径" | "表理解" | "数据血缘"
  status: "done" | "progress" | "waiting"
  count: number | string   // "12" | "3/5" | "—"
}
```

**卡片类型与清洗环节映射**
| 资料源类型 | 支持的清洗环节 |
|-----------|-------------|
| 业务文档 (Notion/飞书) | 术语提取, 指标口径 |
| 代码库 (GitHub) | 术语提取, 指标口径, 表理解, **数据血缘** |
| 数据库 (直连) | 表理解, 字段语义, 数据血缘 |
| 人工补充 | 术语提取, 指标口径 |
| 外部导入 | 术语提取, 指标口径 |

#### 3.2.2 清洗结果表格 (ResultTable)

**支持的 Tab 类型**（总览页不显示"数据血缘"Tab）
```
Tab: "business_terms" | "metrics" | "table_understanding" | "field_semantics"
注：数据血缘不显示在总览页，仅在代码库详情页
```

**业务术语表字段**
| 字段 | 类型 | 说明 |
|------|------|------|
| 术语 | string | 业务术语名称 |
| 类型 | enum | 💰度量 / 📋枚举 / 📅时间 / 👤维度 |
| 定义 | string | 术语的业务含义 |
| 关联字段 | string | 对应的数据库字段，逗号分隔 |
| 来源 | string | 资料源名称 + 图标 |
| 置信度 | number | AI 提取置信度 0-100% |

**指标口径表字段**
| 字段 | 类型 | 说明 |
|------|------|------|
| 指标名 | string | 指标名称 |
| 计算公式 | string | SQL/MDX 公式 |
| 统计口径 | string | 口径说明文字 |
| 来源 | string | 资料源名称 |
| 关联术语 | string[] | 依赖的业务术语 |

---

## 四、资料源详情页

### 4.1 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  ← 返回  [📄 产品PRD]               同步:2小时前  [重新同步]│
├─────────────────────────────────────────────────────────┤
│  🔄 清洗流水线  — 本资料源支持 N 个清洗环节              │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  →  ┌─────────────┐  →  ┌─────────────┐ │
│  │ ✓ 术语提取  │     │ ✓ 指标口径  │     │ — 表理解    │ │
│  │ 完成 12条  │     │ 完成 5条   │     │ 不支持     │ │
│  │ ✓GMV✓实收  │     │ ✓日GMV✓付费 │     │ 本资料源不适用│ │
│  │ [✓完成][详情]│     │ [✓完成][详情]│     │ [不支持]   │ │
│  └─────────────┘     └─────────────┘     └─────────────┘ │
│  (代码库还有第四步：数据血缘)                             │
├─────────────────────────────────────────────────────────┤
│  📄 本资料源产出                                        │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │ 📑 术语 (12)    │  │ 📏 指标 (5)    │              │
│  │ GMV     度量 92%│  │ 日GMV  92%     │              │
│  │ 实收金额 度量 95%│  │ 付费率  95%     │              │
│  │ [查看全部→]     │  │ [查看全部→]     │              │
│  └─────────────────┘  └─────────────────┘              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  ← 返回  [💻 data-warehouse]           同步:进行中...  │
├─────────────────────────────────────────────────────────┤
│  🔄 清洗流水线  — 代码库支持 4 个清洗环节（含数据血缘）  │
├─────────────────────────────────────────────────────────┤
│  ✓术语  →  ◐指标  →  ◐表理解  →  ◐数据血缘(专属)     │
├─────────────────────────────────────────────────────────┤
│  🔗 数据血缘  — 来自代码库的 dbt lineage (10/23已完成)  │
│                                                         │
│  ODS  [ods_order] [ods_user] [ods_product]            │
│         │          │          │                        │
│  DWD  [dwd_order_detail]   [dim_user]                  │
│         │                                        │       │
│  DWS  [dws_trade_daily] ←── [dws_user_profile]         │
│         │                                               │
│  ADS  [ads_gmv_report]  [⏳ ads_user_analysis]          │
│                                                         │
│  ✓已完成10条边  ⏳处理中5条  待处理8条  [展开字段级][导出]│
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────┐  ┌──────────────────┐ │
│  │ 📑术语8  │📏指标3/5 │📋表12/23│ │  📊 同步统计    │ │
│  │ 🔗血缘10/23(专属)            │  │  总文件: 156    │ │
│  │                          │  │  已处理: 122(78%)│ │
│  │                          │  │  术语: ✓8条     │ │
│  │                          │  │  指标: ◐3/5     │ │
│  │                          │  │  表理解: ◐12/23 │ │
│  │                          │  │  数据血缘: ◐10/23│ │
│  └─────────────────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 4.2 清洗流水线组件 (CleanPipeline)

**数据结构**
```
CleanPipeline {
  sourceId: string
  sourceType: SourceType
  steps: PipelineStep[]
}

PipelineStep {
  id: "term_extraction" | "metric_caliber" | "table_understanding" | "data_lineage"
  label: string
  description: string
  status: "done" | "progress" | "waiting"
  isExclusive: boolean         // 仅代码库有此字段 = true (data_lineage)
  totalCount?: number           // 总数
  doneCount?: number            // 已完成数
  previews: PreviewItem[]       // 预览数据
  actions: Action[]
}

PreviewItem {
  status: "ok" | "warn" | "wait"
  text: string
}
```

**各资料源类型的清洗环节配置**
| 资料源 | 术语提取 | 指标口径 | 表理解 | 数据血缘 |
|--------|---------|---------|--------|---------|
| Notion/飞书 | ✓ | ✓ | — | — |
| GitHub | ✓ | ✓ | ✓ | ✓ (专属) |
| PostgreSQL | — | — | ✓ | ✓ |
| 人工补充 | ✓ | ✓ | — | — |

### 4.3 数据血缘图组件 (LineageGraph)

**数据结构**
```
LineageGraph {
  layers: Layer[]          // ODS → DWD → DWS → ADS
  edges: Edge[]
  stats: { done, processing, pending }
}

Layer {
  name: "ODS" | "DWD" | "DWS" | "ADS"
  nodes: Node[]
}

Node {
  id: string
  name: string
  status: "done" | "processing" | "pending"
  layer: LayerName
}

Edge {
  from: string   // Node.id
  to: string     // Node.id
  status: "done" | "processing" | "pending"
}
```

**可视规范**
- 每层节点横向排列，同层节点等高
- 层间连接线为垂直→水平→垂直折线（工字形）
- ODS: 蓝色 (#60a5fa)
- DWD: 绿色 (#4ade80)
- DWS: 橙色 (#facc15)
- ADS: 红色 (#f87171)

### 4.4 右侧统计面板

**数据结构**
```
DetailStatsPanel {
  sourceId: string
  syncProgress: {
    total: number
    processed: number
    pending: number
    elapsedTime: string
  }
  cleaningStatus: {
    term_extraction: { status, count }
    metric_caliber: { status, done, total }
    table_understanding: { status, done, total }
    data_lineage: { status, done, total }  // 仅代码库
  }
}
```

---

## 五、组件清单

| 组件名 | 说明 | 状态 |
|--------|------|------|
| TopNav | 顶部导航栏 | 设计中 |
| SourceCard | 资料源卡片 | 设计中 |
| CleaningPill | 清洗状态药丸 | 设计中 |
| ResultTabs | 结果 Tab 切换 | 设计中 |
| ResultTable | 清洗结果表格 | 设计中 |
| BackButton | 返回按钮 | 设计中 |
| CleanPipeline | 清洗流水线 | 设计中 |
| PipelineStep | 流水线步骤卡 | 设计中 |
| LineageGraph | 数据血缘图 | 设计中 |
| LineageNode | 血缘节点 | 设计中 |
| DetailStatsPanel | 详情统计面板 | 设计中 |
| SourceResultCards | 本资料源产出卡片组 | 设计中 |

---

## 六、技术规范

### 6.1 技术栈
- **前端框架**: Next.js 14+ (App Router)
- **UI 组件库**: shadcn/ui (基于 Radix)
- **图表库**: @xyflow/react (用于血缘图)
- **状态管理**: Zustand
- **样式**: Tailwind CSS
- **图标**: Lucide React

### 6.2 页面路由
```
/                           → 资料库总览页
/source/[id]               → 资料源详情页
```

### 6.3 核心数据模型

```typescript
// 资料源
interface DataSource {
  id: string
  type: "notion" | "feishu" | "github" | "database" | "manual"
  title: string
  subtitle: string
  syncStatus: "synced" | "syncing" | "pending" | "error"
  lastSyncTime: Date | null
  cleaningProgress: CleaningProgress
}

// 清洗进度
interface CleaningProgress {
  termExtraction: { status: StepStatus; count: number }
  metricCaliber: { status: StepStatus; done: number; total: number }
  tableUnderstanding: { status: StepStatus; done: number; total: number }
  dataLineage?: { status: StepStatus; done: number; total: number } // 仅代码库
}

type StepStatus = "done" | "progress" | "waiting"

// 业务术语
interface BusinessTerm {
  id: string
  name: string
  type: "metric" | "enum" | "time" | "dimension" | "other"
  definition: string
  sourceId: string
  sourceType: DataSource["type"]
  relatedFields: string[]
  confidence: number
  status: "pending_review" | "approved" | "rejected"
}

// 指标口径
interface MetricDefinition {
  id: string
  name: string
  formula: string
  caliber: string
  sourceId: string
  relatedTerms: string[]
  confidence: number
  status: "pending_review" | "approved" | "rejected"
}

// 数据血缘
interface DataLineage {
  id: string
  sourceTable: string
  targetTable: string
  sourceField?: string
  targetField?: string
  layer: "ODS" | "DWD" | "DWS" | "ADS"
  status: "done" | "processing" | "pending"
}
```

### 6.4 API 接口（待实现）

```
GET  /api/sources                    → 获取所有资料源列表
GET  /api/sources/:id                → 获取资料源详情
POST /api/sources                    → 添加资料源
DELETE /api/sources/:id              → 删除资料源
POST /api/sources/:id/sync           → 触发同步
GET  /api/sources/:id/cleaning      → 获取清洗进度
POST /api/sources/:id/cleaning/run   → 运行清洗
GET  /api/results/terms              → 获取所有术语
GET  /api/results/metrics            → 获取所有指标
GET  /api/results/lineage            → 获取血缘图数据（仅代码库）
```

---

## 七、设计决策记录

| 决策 | 理由 | 日期 |
|------|------|------|
| 数据血缘不在总览页显示 | 血缘是代码库专属产出，在总览页显示会造成其他源用户的困惑 | 2026-05-18 |
| Notion等文档源不支持表理解/血缘 | 表理解依赖代码/数据库schema，文档本身无法提供此信息 | 2026-05-18 |
| 资料源卡片按来源类型设计图标 | 快速区分不同类型的资料源（文档/代码/数据库/人工） | 2026-05-18 |
| 详情页用流水线展示清洗状态 | 让用户清晰知道当前进度，以及下一步该做什么 | 2026-05-18 |
| 血缘图只展示代码库结果 | 血缘数据来自dbt lineage/ORM，文档库无法生成 | 2026-05-18 |
