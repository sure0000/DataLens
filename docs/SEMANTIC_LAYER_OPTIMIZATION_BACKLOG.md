# 语义层增强与接入方案（备忘 · 暂不执行）

> 本文档汇总「语义层可增信息」与「在当前 DataLens 工程中如何通过功能接入」的讨论结论，**仅作保留与规划参考，不要求按本文立即改代码**。

---

## 1. 语义层可增加的信息（按收益方向）

以下信息若维护得当，可提升**表推断**与**逻辑 / SQL 生成**的依据强度（与实现成本大致相关，非严格排序）。

### 1.1 表级业务语义（超越物理 DDL）

- 表/主题解决的业务问题、核心实体、与上下游表关系（1:n、事实/维度等）。
- **行粒度**：一行代表什么（订单行、日汇总、快照等），减少错误的聚合与去重策略。
- **主键 / 自然键 / 软删**：如 `is_deleted`、`valid_from/to`，降低误关联与漏过滤。
- **时间语义**：业务时区、统计日切分（自然日 vs 账单日）、迟到数据策略。

### 1.2 列级语义与可计算约束

- **度量 vs 维度**、**可加性**（可加 / 半可加 / 不可加）、默认聚合方式。
- **枚举 / 码表**：状态含义、与维表映射，减少模型猜测常量。
- **单位与精度**（金额分/元、重量单位等）。
- **PII / 脱敏**：不可 SELECT 或需脱敏的列（合规 + 减少胡编）。

### 1.3 跨表 JOIN 与路径先验

- 推荐 JOIN 路径、禁止或慎用的 JOIN（笛卡尔、历史脏键）。
- 与推理链路中「主分析表 / JOIN 涉及」等角色标签对齐的**固化分析路径**说明。

### 1.4 指标与口径层

- 指标目录：名称、定义、表达式或 SQL 片段、维度切片约定、与表/列绑定。
- **同义词**：口语指标名到统一口径的映射。
- **口径版本**：变更历史，避免新旧混用。

### 1.5 业务规则与策略（可检索、可引用）

- 默认时间窗、排除测试账号、仅看已支付等过滤规则。
- 按组织/区域/租户的数据范围（与权限或查询模板对齐）。
- 典型问题模式与推荐表组合（便于 RAG 命中）。

### 1.6 数据质量与新鲜度

- 分区、更新频率、延迟（T+1、小时级），帮助选对分区与预期。
- 已知缺口：某段日期缺数、迁移中等，减少无效推理。

### 1.7 负例与边界

- 易错问法与错误 SQL 对照（不要怎样 JOIN、不要用某列做金额等）。
- 易混淆表的区分说明。

### 1.8 结构化 + 自然语言双轨

- 除长文本外，提供 **JSON/YAML 等机器可读块**（主键、外键置信度、推荐度量、常用 WHERE），供护栏与 prompt 共用，比纯叙述更稳。

---

## 2. 当前工程中已有的承载能力

| 能力 | 数据模型（示例） | 进入 Copilot 的路径（概念） |
|------|------------------|-----------------------------|
| 列语义 | `ColumnMeta`：`semantic_desc`、`semantic_type`、`comment` 等 | `rag_service._build_priority_context` → `schema_text` → `SqlCopilotContext.schema` |
| 表级摘要 / 场景 / 关键列 / 风险 | `TableSummary`：`summary`、`use_cases`、`key_columns`、`warnings` | 同上 → `analysis_text` / `summary_text` → `TABLE SUMMARY` 等 |
| 业务域与知识 | `BusinessDomainDescription`、域绑知识库 | `_collect_knowledge_context_text` → `SqlCopilotContext.knowledge` |
| 表绑知识库与固定条目 | `TableKnowledgeBase`、`TableKnowledgeEntry` | 同上 |
| 相似问法 | `QueryExample` + 向量检索 | `few_shot_json` |

Prompt 分层拼装入口：`backend/services/llm_service.py` 中 `SqlCopilotContext`、`_sql_generation_user_message`。

---

## 3. 通过「功能」接入的推荐方式（与代码位置对应）

### 3.1 表 / 列语义（结构化）

- **功能**：表详情中维护列说明、语义类型、可用性等；必要时扩展 `TableMeta` / `ColumnMeta` 字段或增加 `JSON`（如 `semantic_extra`）。
- **接入**：扩展 `rag_service._build_priority_context` 中 `schema_lines` / `analysis_lines` 的拼接规则。
- **相关代码**：`backend/models.py`，`backend/routers/tables.py`、`analyze.py`、`datasources.py`；前端 `app/table/[id]/`、`ColumnCard.tsx` 等。

### 3.2 表级叙述与风险（自然语言）

- **功能**：维护 `TableSummary` 各字段；可通过「语义分析任务」写回或提供表详情页编辑能力。
- **接入**：依赖现有 `_build_priority_context` 读取逻辑即可；若新增可编辑 API，需与 `TableSummary` 读写对齐。

### 3.3 口径、指标、JOIN 约定、负例（长文本 + RAG）

- **功能**：用知识库条目（Markdown 分节）维护；通过业务域 / 表关联已有知识库能力。
- **接入**：`_collect_knowledge_context_text` 已聚合进 `knowledge`；主要工作是**内容运营 + 关联配置**，必要时微调检索条数或拼接模板。

### 3.4 业务域全局语义

- **功能**：完善业务域描述与域下知识库绑定。
- **接入**：会话 `business_domain_id` 已参与知识拉取；若需域描述更靠前，可在 `rag_service.answer` 组装 `SqlCopilotContext` 时追加一节（规划项）。

### 3.5 指标目录 / 强结构化规则（进阶）

- **功能**：新表（如 `metric_definitions`）或 `TableMeta` 上 `JSON` 字段承载指标与表达式。
- **接入**：新增一段固定格式文本（如 `## METRICS`）拼入 `SqlCopilotContext`；可能需扩展 `SqlCopilotContext` 或 `business_sections`（规划项）。

### 3.6 Few-shot 质量

- **功能**：维护高质量 `QueryExample`（或批量导入）。
- **接入**：现有相似检索与 `few_shot_json` 链路。

---

## 4. 建议实施顺序（落地时参考）

1. **零/schema 变更**：填满 `TableSummary`、列语义、知识库（域/表绑定）与 `QueryExample`。
2. **小改动**：在 `_build_priority_context` 中增加已有字段的展示（如 `warnings`、更多 `ColumnMeta` JSON 子字段的摘要）。
3. **-schema 迁移**：新增表或 JSON 列承载指标目录、JOIN 图等，再扩展 `SqlCopilotContext` 与表详情/管理端功能。

---

## 5. 文档状态

- **性质**：产品 / 技术规划备忘。
- **执行**：**暂不执行**；后续若立项，可拆为独立需求（数据迁移、API、前端、Prompt 变更）分别跟踪。

---

*最后更新：基于仓库内 Copilot 管线（`rag_service`、`llm_service`、`models`、表/知识库路由与前端表页）的讨论整理。*
