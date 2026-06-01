# Copilot 语义路由优化方案

> 整理自 DataLens 语义层讨论 · 2026-05-25  
> 主题：Copilot 在「缩小语义搜索 / 上下文范围」上的现状评估与后续优化路线  
> 关联文档：[企业语义层与域内自治实践](../项目总览/企业语义层与域内自治实践.md)、[SEMANTIC_LAYER_OPTIMIZATION_BACKLOG](../项目总览/语义层能力清单.md)、[DATALENS_OVERVIEW](../项目总览/DataLens项目全貌.md)

---

## 摘要

DataLens Copilot 路由已完成 **P0 ~ P2 全量 backlog**（2026-05-25 落地）。当前策略为 **会话硬边界 + 多信号表路由（知识 / 表向量 / 指标术语 / 列向量 / 血缘）+ 打分截断与梯度 fallback + 意图前置 + 生成后 review**。

**已解决的原核心缺口**：表/列向量参与路由、DocumentChunk 统一检索、指标/术语/血缘扩表、Few-shot 域隔离、路由结构化 trace、无域语义 top_k、自动域推荐（高置信可绑定）、SQL 域外 review 闭环。

本文档 backlog 项均已标注 **✅**；§1~2 部分描述为实施前基线，§3 为实施记录与验收参照。

**代码入口**：`context_builder.py`、`rag_service.py`、`routing_bundle.py`、`services/routing/*`、`semantic_relation_sync.py`。

**2026-05-25 补充（轻量语义图 Phase 3）**：

- 知识库 chunk 写入 `semantic_meta`（role + grounding），路由信号 `semantic_grounding`
- `semantic_relations` 表：`term_column` / `metric_table` / `table_join` / `concept_alias`
- `graph_router.apply_graph_expansion` = lineage + semantic_relations 1-hop，信号 `semantic_graph`
- `concept_id` + `concept_alias` 支持指标/术语别名路由

---

## 1. 当前路由架构

### 1.1 三层漏斗（基线架构 · 现已扩展为多信号路由，见 §3）

> 下图描述优化前主路径；实施后已叠加表向量、指标术语、列/血缘扩表、梯度 fallback、`routing_bundle` 等，详见各 P0~P2 条目。

```
用户问题 + 可选 table_id + 可选 business_domain_id
  │
  ├─ [硬锁] table_id 存在 → 单表 schema + 表绑知识
  │
  ├─ [域路由] business_domain_id 存在
  │     ├─ tables_from_business_domain() → 域内挂载表全集
  │     ├─ candidate_table_ids_from_domain_knowledge()
  │     │     ├─ 域绑知识库 × search_entries_hybrid（向量 + BM25 + RRF）
  │     │     ├─ TableKnowledgeEntry 显式链接 → 表
  │     │     └─ 知识 title/summary/snippet 中表名字串匹配 → 表
  │     ├─ 命中候选表 → 加载候选子集
  │     └─ 未命中 → fallback 域内全部挂载表
  │
  └─ [无域] all_tables_for_copilot_fallback() → 按 created_at 取最近 N 张（默认 2000）
        │
        ▼
collect_knowledge_context_text()
  ├─ 域绑 / 表绑知识库
  ├─ TableKnowledgeEntry 固定全文注入
  └─ search_entries_hybrid 语义片段（每 KB top_k=6，合并最多 20 条）
        │
        ▼
SqlCopilotContext → generate_sql()
        │
        ▼
reasoning_3：解析 SQL 引用表 + trust 标签（仅观测，不干预路由）
```

### 1.2 关键代码入口

| 模块 | 文件 | 职责 |
|------|------|------|
| 表范围与 schema 组装 | `backend/services/context_builder.py` | `build_priority_context`、`candidate_table_ids_from_domain_knowledge`、`collect_knowledge_context_text` |
| 混合检索 | `backend/services/retrieval_service.py` | `search_kb_hybrid_unified`（KnowledgeEntry + DocumentChunk RRF 融合，P0-4） |
| 向量存储与检索 | `backend/services/embedding_service.py` | `search_similar`（仅 query few-shot）、表/列 embedding 写入在 analyze 侧 |
| 表/列 embedding 写入 | `backend/routers/analyze.py` | `ref_type='table'` / `'column'` |
| 流水线编排 | `backend/services/rag_service.py` | `answer()`：上下文 → 意图 → SQL |
| 配置 | `backend/config.py` | 见 §5（如 `copilot_max_tables_without_domain` 默认 **20**） |

### 1.3 语义资产与 Copilot 路由（实施后）

| 资产 | 存储 | Copilot 使用情况 |
|------|------|------------------|
| 表摘要向量 | `embeddings.ref_type='table'` | ✅ 域内 / 无域直搜 + RRF 融合 |
| 列语义向量 | `embeddings.ref_type='column'` | ✅ 维表/码表扩表（P1-2） |
| 文档分块 | `document_chunks` + hybrid | ✅ 统一 KB 检索（P0-4） |
| 业务术语 | `business_terms` | ✅ 指标/术语路由（P1-1） |
| 指标定义 | `metric_definitions` | ✅ 口径注入 + 表加权（P1-1） |
| 表间血缘 | `data_lineage` | ✅ 1-hop 扩表 + JOIN 指南（P2-2） |
| 历史问答 | `embeddings.ref_type='query'` | ✅ Few-shot，域内过滤（P0-5） |

---

## 2. 现状评估

### 2.1 做得好的

- **域优先硬边界**与「域内自治 + 企业薄层」联邦模型一致（`BusinessDomainSelection` + 域绑 KB）。
- **知识混合检索**（向量 + BM25 + RRF）优于纯向量，分块与条目去重已实现。
- **多信号表锚定**：显式 `TableKnowledgeEntry` + 知识正文表名提及，运营可解释。
- **固定全文 vs RAG 片段分层**：关键口径必达、长尾靠检索。
- **Trace 可解释**：`table_scope_note`、`reasoning_2/3` 便于排查路由结果。

### 2.2 主要短板（实施前基线 → 当前）

| 问题（基线） | 状态 |
|------|------|
| 表/列向量未参与「问题→表」路由 | ✅ P0-1 / P1-2 |
| 表路由二值化（命中 / 全量 fallback） | ✅ P0-2 打分 + 梯度 fallback |
| 表名字串匹配过粗 | ✅ P0-3 |
| 无域场景按 `created_at` 取表 | ✅ P0-2 语义 top_k（默认 20） |
| DocumentChunk 双轨未统一 | ✅ P0-4 |
| 指标/术语/血缘未接入 | ✅ P1-1 / P2-2 |
| Few-shot 无域隔离 | ✅ P0-5 |
| 意图分类在上下文组装之后 | ✅ P1-3 |
| 缺少路由单测与结构化 trace | ✅ 单测 + P2-3 `routing_trace` |

### 2.3 维度评分（实施后参考）

| 维度 | 评分 | 说明 |
|------|------|------|
| 硬边界（域/表锁定） | ★★★★☆ | 清晰 |
| 软路由（问题→表） | ★★★★☆ | 多信号融合 + 截断 |
| 知识检索 | ★★★★☆ | Entry + Chunk 统一 hybrid |
| 排序与置信度 | ★★★★☆ | 综合分 + 梯度 fallback |
| 结构化语义参与 | ★★★☆☆ | 指标/术语/血缘已接入，可继续标定权重 |
| 可解释性 | ★★★★★ | `routing_trace` + reasoning_2/3 |
| 联邦模型契合 | ★★★★☆ | 域优先 + 自动域推荐（P2-1） |

---

## 3. 优化 backlog（按优先级）

> **实施状态（2026-05-25）**：P0（5/5）· P1（4/4）· P2（4/4）**全部 ✅ 已完成**。无 🔲 / 🚧 待办项。

状态说明：**🔲 待做** / **🚧 进行中** / **✅ 已完成**

### P0 — 小改动、收益大（5/5 ✅）

#### P0-1 域内表向量直搜 + 与知识路由融合 ✅

**目标**：用已有 `ref_type='table'` embedding 做「问题 → 表」直接检索，与知识间接锚表 RRF 合并。

**建议实现**：
- 在 `candidate_table_ids_from_domain_knowledge` 同级新增 `candidate_table_ids_from_table_embeddings(db, question, allowed_table_ids, top_k)`。
- 检索域内表摘要向量，返回 `(table_id, cosine_distance)` 排名。
- 与知识路由命中表做 **RRF 融合**（复用 `retrieval_service._rrf_merge`）。
- 新增配置项如 `copilot_max_candidate_tables`（建议默认 8–12）。

**主要改动**：`context_builder.py`、`embedding_service.py`（或 `retrieval_service.py` 新增表级检索函数）、`config.py`。

**验收**：
- 域内 50+ 表、知识未提及某核心表时，问该表相关业务问题仍能进入 top 候选。
- trace 中展示各信号来源（knowledge / table_embedding / explicit_link）。

---

#### P0-2 候选表打分、截断与梯度 fallback ✅

**目标**：避免「0 命中 = 全域表」二值逻辑；控制 schema token 上限。

**建议实现**：
- 为每张候选表维护综合分：`w1·知识RRF + w2·表向量 + w3·显式链接加成`。
- 设 `min_score`：低于阈值不进入 schema；高于阈值按分排序取 top_k。
- 梯度 fallback：
  1. top_k 候选（高置信）
  2. 扩大 top_k 或降低阈值（中置信）
  3. 域内全表（低置信，trace 明确告警）
- 无域场景：语义 top_k + 硬上限（如 20），而非 2000 张全加载。

**主要改动**：`context_builder.py` → `build_priority_context`；`config.py` 新增阈值与 top_k。

**验收**：
- 典型域内问答 schema 行数可控（如 ≤12 表 × 列数）。
- fallback 到全域表时 trace 有明确 `fallback_reason`。

---

#### P0-3 表名匹配收紧 ✅

**目标**：减少 `order` 误命中 `order_items` / 正文普通词。

**建议实现**：
- 优先匹配 `` `{database}.{table}` `` 全名（词边界或标点分隔）。
- 短表名（如长度 < 6）仅作 tie-break，或要求同时命中多信号。
- 匹配前对 blob 做 token 化；避免裸 `tn in blob` 子串。

**主要改动**：`context_builder.py` → `candidate_table_ids_from_domain_knowledge` 内匹配逻辑。

**验收**：
- 单测覆盖：同名前缀表、短表名、中文问题 + 英文表名。

---

#### P0-4 Copilot 统一知识检索（KnowledgeEntry + DocumentChunk） ✅

**目标**：新文档流水线内容进入 Copilot 知识上下文与表锚定。

**建议实现**：
- 抽象 `search_kb_hybrid_unified(db, kb_id, query, top_k)`：合并 `search_entries_hybrid` 与 `search_chunks_hybrid` 结果（RRF 或分源标注）。
- `collect_knowledge_context_text` 与 `candidate_table_ids_from_domain_knowledge` 均改调统一入口。
- DocumentChunk 命中时，若 `source_meta` / 正文含表名，同样参与表锚定。

**主要改动**：`retrieval_service.py`、`context_builder.py`。

**验收**：
- 仅写入 `document_chunks`、无 legacy entry 的 KB，Copilot 仍能检索到相关内容。

---

#### P0-5 Few-shot 业务域隔离 ✅

**目标**：避免跨域历史 SQL 误导表选择与方言习惯。

**建议实现**：
- `search_similar_async` 增加 `business_domain_id` 或 `allowed_table_ids` 过滤。
- 实现方式：join `QueryExample` → `TableMeta`，过滤域内表；或对域外样本降权。
- 无域时保持现状或仅取最近 N 条。

**主要改动**：`embedding_service.py`、`rag_service.py`（传入 domain 上下文）。

**验收**：
- 两域各有相似问法时，选域 A 不会召回域 B 的 few-shot。

---

### P1 — 中等投入（4/4 ✅）

#### P1-1 指标 / 术语路由 ✅

**目标**：「近 30 天 GMV」类口语问法先命中标准口径，再锁定绑定表。

**建议实现**：
- 问句对 `metric_definitions`、`business_terms` 做关键词 + 向量检索（域绑 KB 范围内）。
- 命中后向 `SqlCopilotContext.knowledge` 注入口径块，并向表路由传递 `bound_table_ids` 加权。
- 与 [SEMANTIC_LAYER_OPTIMIZATION_BACKLOG](../项目总览/语义层能力清单.md) 中指标目录规划对齐。

**主要改动**：新建 `routing/metric_router.py` 或扩展 `context_builder.py`；可能需补 `metric_definitions` 与表的关联字段。

**验收**：
- 指标条目已维护的域，口语指标名问法 SQL 口径与条目一致率提升。

---

#### P1-2 列向量辅助扩表（维表 / 码表） ✅

**目标**：主事实表确定后，按问题中的维度词扩展相关维表。

**建议实现**：
- 主表 top-1 确定后，在域内对 `ref_type='column'` 检索，找 semantic_type=dimension/enum 且与问题相关的列所在表。
- 仅作 JOIN 候选扩展，权重低于主表。

**主要改动**：`embedding_service.py`、`context_builder.py`。

**验收**：
- 「按渠道 / 状态 breakdown」类问题，维表进入候选且不超过 top_k 上限。

---

#### P1-3 意图分类前置 ✅

**目标**：general_qa 不加载全量 schema，节省 token 与延迟。

**建议实现**：
- `rag_service.answer()` 调整顺序：guardrail → intent → 分支组装上下文。
- `general_qa`：仅域描述 + 知识检索，跳过 `build_priority_context` 列 schema。
- `sql_query`：完整表路由链路。

**主要改动**：`rag_service.py`。

**验收**：
- general_qa 路径 context 体积显著小于 sql_query；行为回归测试通过。

---

#### P1-4 检索去重（一次 embed、一次 KB 查询） ✅

**目标**：同一问题不对各 KB 重复 embed；表候选与知识片段共用检索结果。

**建议实现**：
- 单次 hybrid search 返回结构化结果：`entries[]`、`chunks[]`、`linked_table_ids[]`。
- `build_priority_context` 与 `collect_knowledge_context_text` 消费同一份 `RoutingSearchResult`。

**主要改动**：`context_builder.py`、`rag_service.py`（可先算 `routing_bundle` 再分发）。

**验收**：
- 单次 Copilot 请求对同一 KB 的 SQL/向量查询次数下降（可日志计数）。

---

### P2 — 架构级增强（4/4 ✅）

#### P2-1 自动业务域路由（可选） ✅

**目标**：用户未选域时，根据问题推荐或自动绑定业务域。

**建议实现**：
- 对 `BusinessDomainDescription` + 域内表摘要聚合向量做分类 / top-k 域检索。
- 低置信度时 UI 提示用户确认域，不 silent 切换。

**验收**：
- 多域环境下未选域提问，top-1 域准确率可度量。

---

#### P2-2 血缘 / JOIN 图扩展候选表 ✅

**目标**：主表确定后沿 `data_lineage` 或 JOIN 指南条目 1-hop 扩展，并支持禁止 JOIN 黑名单。

**建议实现**：
- 读 `data_lineage` 或知识条目中 `semantic_role=join_guide` 的结构化块。
- 扩展表权重低于主表；黑名单表 hard exclude。

**关联**：企业薄层「跨域关系注册」；见 [企业语义层与域内自治实践](../项目总览/企业语义层与域内自治实践.md) §4.4。

---

#### P2-3 路由可观测性 ✅

**目标**：可量化迭代效果，指导域团队补知识。

**建议 trace 字段**（写入 `pipeline_trace` 或结构化日志）：

| 字段 | 含义 |
|------|------|
| `routing_mode` | locked_table / domain_narrowed / domain_full / global_fallback |
| `candidate_table_count` | 进入 schema 的表数 |
| `candidate_sources` | knowledge / table_emb / explicit_link / lineage |
| `fallback_reason` | 未缩窄原因 |
| `top_table_scores` | 前 N 表及综合分 |

**验收**：
- 可按域统计 fallback 率、平均候选表数。

---

#### P2-4 生成后校验闭环 ✅

**目标**：`reasoning_3` 的 trust 标签驱动二次确认或重路由，而非仅展示。

**建议实现**：
- SQL 解析表 ∉ 域内挂载表 → 标记 `review`，可选触发窄化重试或前端确认。
- SQL 解析表与候选集差异大 → 降低自动执行优先级（产品策略待定）。

---

## 4. 建议实施顺序

```
Phase 1 ✅ 已完成
  ✅ P0-1 表向量直搜 + RRF 融合
  ✅ P0-2 打分 / 截断 / 梯度 fallback
  ✅ P0-3 表名匹配收紧
  ✅ P0-5 Few-shot 域隔离
  ✅ context_builder / embedding 单测

Phase 2 ✅ 已完成
  ✅ P0-4 DocumentChunk 统一检索
  ✅ P1-3 意图前置
  ✅ P1-4 检索去重（routing_bundle）
  ✅ P2-3 路由 trace 字段

Phase 3 ✅ 已完成
  ✅ P1-1 指标/术语路由
  ✅ P1-2 列向量扩表
  ✅ P2-2 血缘/JOIN 扩展
  ✅ P2-1 自动域路由（可选）
  ✅ P2-4 生成后校验闭环
```

**后续（文档外 · 部分已落地）**：线上 fallback 率观测、per-domain 权重标定；前端域推荐确认 UI、`sql_review` 交互（2026-05-25 已接入 Copilot 会话展示）。

---

## 5. 配置项（已落地）

| 环境变量 | 默认 | 说明 | 状态 |
|----------|------|------|------|
| `COPILOT_MAX_CANDIDATE_TABLES` | 10 | 域内语义路由后进入 schema 的表上限 | ✅ |
| `COPILOT_TABLE_EMBED_TOP_K` | 15 | 表向量检索 probe 数 | ✅ |
| `COPILOT_ROUTING_MIN_SCORE` | 0.012 | 低于则触发 fallback 链 | ✅ 可继续标定 |
| `COPILOT_MAX_TABLES_WITHOUT_DOMAIN` | 20 | 无域时语义 top_k 硬上限 | ✅ |
| `COPILOT_ROUTING_WEIGHT_KNOWLEDGE` | 1.0 | 知识 RRF 权重 | ✅ |
| `COPILOT_ROUTING_WEIGHT_TABLE_EMB` | 1.0 | 表向量 RRF 权重 | ✅ |
| `COPILOT_MAX_CANDIDATE_TABLES_EXPANDED` | 20 | 梯度 fallback 第二档上限 | ✅ |
| `COPILOT_ROUTING_MIN_SCORE_RELAXED` | 0.006 | 第二档阈值 | ✅ |
| `COPILOT_COLUMN_EXPAND_TOP_K` | 4 | 列向量维表扩表 | ✅ |
| `COPILOT_AUTO_DOMAIN_*` | 见 config | 自动域推荐/绑定 | ✅ |
| `COPILOT_LINEAGE_*` / `COPILOT_JOIN_BLACKLIST` | 见 config | 血缘扩表与 JOIN 黑名单 | ✅ |
| `SEMANTIC_CHUNK_STRUCTURE_MAX` | 40 | 单文档语义结构化 chunk 上限 | ✅ |
| `SEMANTIC_AUTO_APPROVE_CONFIDENCE` | 80 | 术语/指标自动 approved 阈值 | ✅ |

---

## 6. 测试与验收清单

### 6.1 单测（已新增）

| 用例 | 文件 | 状态 |
|------|------|------|
| 知识命中 + 表向量融合排序 | `backend/tests/test_context_builder_routing.py` | ✅ |
| 表名子串不误命中 | 同上 | ✅ |
| 无命中梯度 fallback | 同上 | ✅ |
| Few-shot 域过滤 | `backend/tests/test_embedding_service.py` | ✅ |
| DocumentChunk 统一检索 | `backend/tests/test_retrieval_service.py` | ✅ |
| 指标/术语、routing bundle、列扩表 | `backend/tests/test_routing_p1.py` | ✅ |
| 域推荐、血缘、SQL review、routing trace | `backend/tests/test_routing_p2.py` | ✅ |

### 6.2 场景回归（可用手工 + manufacturing demo）

1. **域内窄化成功**：问题明确、知识有条目链接 → 候选表 ≤5，SQL 表正确。
2. **域内窄化失败**：问题模糊、知识无链接 → 可控 fallback，trace 有原因。
3. **未选域**：语义 top_k，不全库 2000 表。
4. **单表锁定**：忽略域内其他表，schema 仅一表。
5. **跨域 few-shot 污染**：选域 A 时不出现域 B 历史 SQL。

### 6.3 成功指标（上线后观察）

| 指标 | 方向 |
|------|------|
| `domain_full` fallback 占比 | ↓ |
| 平均候选表数 / 平均 schema 字符数 | ↓ |
| SQL 首次执行成功率 | ↑ |
| reasoning_3 中 `trust=low/review` 占比 | ↓ |
| 域团队补知识后 fallback 率 | 可感知下降 |

---

## 7. 与语义层建设的关系

路由优化 **不替代** 域内语义内容建设，而是让已有资产可被检索到：

| 域团队维护 | 路由如何利用 |
|------------|--------------|
| 业务域描述 | ✅ 域硬边界 + 自动域推荐（P2-1） |
| 域挂载表 | ✅ 候选 allowed set |
| 知识库条目 + TableKnowledgeEntry | ✅ 间接锚表 + 口径注入 |
| TableSummary / 列语义 | ✅ 表/列向量直搜与扩表 |
| 指标条目 / 术语 | ✅ 口语→口径→表加权 + concept_alias |
| Document 流水线文档 | ✅ 统一 hybrid 检索 + semantic_meta grounding |
| semantic_relations | ✅ graph_router 1-hop 扩表 |
| QueryExample | ✅ few-shot + 域隔离 |

详见 [企业语义层与域内自治实践](../项目总览/企业语义层与域内自治实践.md) §2.4、§5.4 域团队最小维护清单。

---

## 8. 关键决策记录（已按此落地）

| 决策点 | 结论 | 对应实现 |
|--------|------|----------|
| 0 命中是否仍允许全域表 fallback | 保留，trace 强告警 | P0-2 `fallback_reason` |
| 无域默认行为 | 语义 top_k；高置信可自动绑域 | P0-2 + P2-1 |
| 表向量与知识 RRF 权重 | 先等权，trace 标定 | `COPILOT_ROUTING_WEIGHT_*` |
| SQL 表 ∉ 域挂载 | review 标签，默认不 block 执行链路由 review 跳过 | P2-4 `sql_review` |

---

## 9. 文档状态

- **性质**：Copilot 路由专项优化备忘；**backlog 已全部完成**。
- **实施完成**：2026-05-25（P0 ~ P2 + 轻量语义图 Phase 1~3）。
- **维护**：权重标定、线上指标、semantic_relations UI、前端 `domain_suggestion` / `sql_review` 交互。

---

*主要代码：`backend/services/context_builder.py`、`backend/services/rag_service.py`、`backend/services/routing_bundle.py`、`backend/services/routing/`。*
