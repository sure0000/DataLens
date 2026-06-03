# NL-to-SQL 非确定性分析：同一问题生成不同 SQL 的根因与修复方案

> 分析日期：2026-06-03
> 示例问题：「重要性等级为一级的客户，5 月缴费情况？」

---

## 一、流水线全貌

```
用户问题
  │
  ├─ 1. Guardrail（规则检查，确定性）
  ├─ 2. 意图分类（LLM，T=0，基本确定）
  ├─ 3. 本体知识匹配（SPARQL + 向量 + 关键词，有缓存 300s）
  ├─ 4. NLP 预处理（时间解析/维度提取/计算模式，规则确定性）
  ├─ 5. 路由 Bundle 组装（向量检索 + BM25，RRF 融合）
  ├─ 6. Few-shot 检索（向量相似度 top-5）
  ├─ 7. Context 组装（ontology_text + schema + knowledge + few-shot）
  ├─ 8. SQL 生成（LLM，T=0）
  ├─ 9. SQL 执行 + 修复（最多 3 轮自动修复）
  └─ 10. 结果持久化（写入 QueryExample + Embedding，影响下次检索）
```

## 二、非确定性来源（按影响程度排序）

### P0 — LLM 本身的非确定性

**文件:** `backend/services/llm_service.py:197-215`

即使 `temperature=0.0`，大模型输出也不是严格确定性的。浮点精度、GPU 内核调度、模型内部采样机制都会导致微小差异，在复杂的 SQL 生成场景中被放大。

**当前模型:** `deepseek:deepseek-v4-flash`（auto 策略默认，见 `llm_models.py:83`）

### P1 — Few-shot 历史样例每次不同

**文件:** `backend/services/rag_service.py:306-313`

```python
refs = await search_similar_async(db, question, top_k=5, ...)
```

- Embedding API（`text-embedding-3-small`）的向量在多次调用间可能有微小浮动
- 每次执行成功后写入新的 QueryExample，使检索池持续膨胀（`rag_service.py:417-428`）
- 不同 few-shot 示例强烈引导 LLM 模仿不同的 SQL 模式

### P1 — System Prompt 给了 4 种 SQL 模式，LLM 自由选择

**文件:** `backend/prompts/sql_generation_system.txt:36-77`

| 模式 | 触发场景 | 示例 SQL 结构 |
|------|---------|-------------|
| 模式 1：单表聚合 | 统计总量/平均值/计数 | `SELECT dim, SUM(metric) ... GROUP BY dim` |
| 模式 2：时间序列 | 按天/周/月趋势 | `SELECT date_col, SUM(metric) ... GROUP BY date_col` |
| 模式 3：对比/环比 | 变化/对比/vs/增长 | 自连接或 CASE WHEN 行列转置 |
| 模式 4：多表 JOIN | 跨表关联 | `LEFT JOIN` / `INNER JOIN` |

同一问题"5月缴费情况"可被理解为模式 1、2 或 4，LLM 每次选择可能不同。

### P2 — 本体概念匹配阈值边界漂移

**文件:** `backend/services/copilot/ontology_concept_match.py:20-23`

```python
MIN_EMBED_SIMILARITY = 0.50   # 向量相似度阈值
MIN_KEYWORD_SCORE = 0.42      # 关键词得分阈值
MIN_MERGED_SCORE = 0.42       # 合并后阈值
```

- 得分在阈值附近的概念可能"这次纳入、下次丢弃"
- SPARQL 子串匹配确定性高，但 Embedding 和 Keyword 策略的非确定性叠加

**缓解因素:** ontology 匹配结果有 300s 缓存（`ontology_match.py:14`），短时间内重复调用会命中缓存。

### P2 — 知识库混合检索 RRF 融合不稳定

**文件:** `backend/services/retrieval_service.py:58-64`

RRF（Reciprocal Rank Fusion）融合向量检索 + BM25 全文检索结果。向量差异通过 RRF 算法放大，导致最终返回给 LLM 的知识片段不同。

### P3 — NLP 时间提示给了多种 SQL 写法建议

**文件:** `backend/services/nlp_helpers.py:108-109`

```python
f"SQL 中请将月份过滤条件写为明确的日期范围"
f"（如 month_column = '2026-05' 或 BETWEEN '2026-05-01' AND '2026-05-31'）"
```

LLM 可能选 `=` 也可能选 `BETWEEN`，两种写法在有些数据库中等价，但生成的 SQL 文本不同，且在不同数据类型的列上可能产生不同结果。

### P3 — Embedding API 向量微小浮动

**文件:** `backend/services/embedding_service.py:42-47`

OpenAI `text-embedding-3-small` 在理论上是确定性的，但实践中存在浮点精度差异。

**如果未配置 OpenAI Key**，会使用 SHA-256 本地确定性 hash（`embedding_service.py:33-39`），此时向量检索完全确定。

### P4 — 模型自动选择可能变化

**文件:** `backend/services/llm_models.py:76-86`

如果管理员增删了 LLM 连接配置，auto 策略可能解析到不同模型。

---

## 三、修复方案

### 方案 1：延长 Ontology 匹配缓存 TTL

**优先级:** P2 → P0（低风险，立即见效）
**文件:** `backend/services/copilot/ontology_match.py:14`

```python
# 当前
_CACHE_TTL_SEC = 300   # 5 分钟

# 建议
_CACHE_TTL_SEC = 1800  # 30 分钟
```

**影响:** 同一问题在 30 分钟内得到完全相同的 ontology 匹配结果，减少概念漂移。缓存 key 是 `hash(question) + hash(kb_ids)`，知识库更新后需主动清缓存。

---

### 方案 2：固定 Few-shot 样例策略

**优先级:** P1（影响大，实现中等）
**文件:** `backend/services/rag_service.py:306-313`

**方案 2a — 对 few-shot 检索结果做短期缓存（推荐）**

在 `search_similar_async` 外套一层缓存，同一 question + domain 组合复用同一批样例：

```python
# 伪代码
_few_shot_cache: dict[str, tuple[float, list[dict]]] = {}
_FEW_SHOT_TTL = 600  # 10 分钟

def cached_search_similar(db, question, ...):
    key = f"{hash(question)}:{domain_id}"
    entry = _few_shot_cache.get(key)
    if entry and time.monotonic() - entry[0] < _FEW_SHOT_TTL:
        return entry[1]
    result = await search_similar_async(db, question, ...)
    _few_shot_cache[key] = (time.monotonic(), result)
    return result
```

**方案 2b — 不依赖 few-shot，增强 System Prompt 中的规则**

减少或移除 few-shot 示例，改为在 System Prompt 中增加更详尽的规则，让 LLM 依靠规则而非样例来生成 SQL。

**权衡:** 2a 实现简单，但缓存过期后仍会变；2b 能彻底消除这一非确定性来源，但需要重新设计 prompt。

---

### 方案 3：在 Prompt 中增加问题分类约束，减少 LLM 自由选择

**优先级:** P1（影响大，实现中等）
**文件:** `backend/prompts/sql_generation_system.txt`

**方案 3a — 在 System Prompt 中增加路由规则**

在"SQL 生成模式"章节开头增加明确的路由决策规则：

```text
## 0. 模式选择规则（优先级从高到低）

1. 若问题包含"对比"/"环比"/"同比"/"vs"/"变化"/"增长"/"下降" → 模式 3（对比/环比/同比）
2. 若问题指定了具体时间点/时间段且无对比语义，且需要按时间维度分组 → 模式 2（时间序列）
3. 若问题仅做筛选+统计，无时间趋势要求 → 模式 1（单表聚合）
4. 若问题涉及跨表关联（如"客户的订单金额"）→ 模式 4（多表 JOIN）

**重要：选定模式后不要混合其他模式。禁止对简单筛选+统计问题使用复杂的自连接或多表 JOIN。**
```

**方案 3b — 在 NLP 预处理中增加问题模式分类**

在 `preprocess_question()` 中增加一个步骤，用简单规则判断问题属于哪种 SQL 模式（单表聚合 / 时间序列 / 对比 / 多表 JOIN），作为 hint 注入 prompt。

**文件:** `backend/services/nlp_helpers.py:482-494`

---

### 方案 4：统一 NLP 时间提示中的 SQL 写法

**优先级:** P3（影响小，实现简单）
**文件:** `backend/services/nlp_helpers.py:108-109`

```python
# 当前（给了两种写法）
f"SQL 中请将月份过滤条件写为明确的日期范围"
f"（如 month_column = '{year}-{m:02d}' 或 BETWEEN ...）"

# 建议（统一为一种）
f"SQL 中请将月份过滤条件写为字符串等值匹配：month_column = '{year}-{m:02d}'"
```

**注意:** 这个修改需要在了解实际数据列的类型后做决策。如果月份列是 DATE 类型，BETWEEN 更合适；如果是 VARCHAR，`=` 更合适。

---

### 方案 5：切换到本地确定性 Embedding

**优先级:** P3（影响小，实现简单，但有精度损失）
**文件:** `backend/services/embedding_service.py:33-39`

当前默认使用 OpenAI `text-embedding-3-small`（需要 API Key）。如果未配置 Key，已经使用 SHA-256 确定性 hash 作为 fallback。要彻底消除向量检索的非确定性，可以：

- 强制使用 `_local_embed()` 替代远程 API
- **权衡:** 本地确定性 hash 的语义理解能力远弱于 OpenAI Embedding，可能降低检索质量

**建议:** 不作为首选方案，保留远程 Embedding 但做好缓存。

---

### 方案 6：Ontology 匹配失败时的降级策略

**优先级:** P2（防御性措施）
**文件:** `backend/services/copilot/ontology_concept_match.py:404-439`

当三种匹配策略都没有高置信度结果时，当前行为是返回低于阈值的结果或空集。建议：

- 对低置信度结果（0.42-0.55 区间）标记 `low_confidence` 标志
- 在 prompt 中告知 LLM"以下概念匹配置信度较低，仅供参考"
- 避免 LLM 过度信任低质量匹配

---

## 四、推荐实施顺序

| 优先级 | 方案 | 预期效果 | 实施难度 | 风险 |
|--------|------|---------|---------|------|
| 1 | 方案 1：延长缓存 TTL | 减少概念漂移 | 1 行改动 | 极低 |
| 2 | 方案 4：统一时间提示 SQL 写法 | 减少 SQL 格式变体 | 2-3 行改动 | 低（需确认列类型） |
| 3 | 方案 2a：Few-shot 检索缓存 | 同一问题样例稳定 | ~30 行新代码 | 低 |
| 4 | 方案 3a：Prompt 增加模式选择规则 | LLM 选模式更一致 | Prompt 改动 | 中（需充分测试） |
| 5 | 方案 3b：NLP 问题模式分类 | 更精确的模式路由 | ~80 行新代码 | 中 |
| 6 | 方案 6：低置信度标记 | 减少误导 | ~50 行 | 低 |
| 7 | 方案 5：本地 Embedding | 完全确定性 | 配置项 | 高（语义精度损失） |

---

## 五、验证方法

修复后，建议用以下方式验证效果：

1. **重复查询测试**：对同一问题连续发起 10 次请求，对比 SQL 文本的一致性
2. **缓存命中率监控**：在 ontology 匹配和 few-shot 检索中增加缓存命中率日志
3. **SQL 模式分布**：统计同一问题在不同模式下的分布比例，理想情况应集中在单一模式
4. **结果一致性**：不仅对比 SQL 文本，也对比查询结果的数值是否一致

---

## 六、相关文件索引

| 组件 | 文件 | 关键行号 |
|------|------|---------|
| 主入口 | `backend/services/rag_service.py` | 127-506 |
| SQL 生成 | `backend/services/llm_service.py` | 623-652 |
| SQL 生成 Prompt | `backend/prompts/sql_generation_system.txt` | 1-91 |
| LLM 调用（T=0） | `backend/services/llm_service.py` | 197-215 |
| 模型自动选择 | `backend/services/llm_models.py` | 76-86 |
| Ontology 匹配缓存 | `backend/services/copilot/ontology_match.py` | 12-47 |
| 概念匹配阈值 | `backend/services/copilot/ontology_concept_match.py` | 18-23 |
| 混合路由合并 | `backend/services/copilot/ontology_concept_match.py` | 404-439 |
| Context 组装 | `backend/services/copilot/context.py` | 28-83 |
| Context Builder | `backend/services/context_builder.py` | 687-972 |
| Few-shot 检索 | `backend/services/embedding_service.py` | 105-116 |
| Embedding 服务 | `backend/services/embedding_service.py` | 33-47 |
| NLP 时间解析 | `backend/services/nlp_helpers.py` | 66-194 |
| NLP 预处理 | `backend/services/nlp_helpers.py` | 482-494 |
| 知识库混合检索 | `backend/services/retrieval_service.py` | 58-80 |
| SQL 修复 | `backend/services/llm_service.py` | 697-743 |
| QueryExample 持久化 | `backend/services/rag_service.py` | 416-428 |
