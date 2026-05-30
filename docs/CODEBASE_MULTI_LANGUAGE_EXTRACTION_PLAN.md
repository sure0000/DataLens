# 代码库多语言语义抽取改造方案

> 状态：已保存，待新会话全量实施  
> 背景：代码库语义清洗出现 `no_triples`（「抽取已完成但未产生可入图三元组」），且当前实现偏 SQL/ETL，对 Python / dbt / Spark / ORM 等非纯 SQL 数据代码支持不足。  
> 关联代码：`git_knowledge_sync.py`、`codebase_analyzer.py`、`orchestrator.py`、`lineage_extractor.py`、`join_extractor.py`、`pipeline_status.py`

---

## 1. 目标

1. 代码库语义清洗**不绑定 SQL 文件**，支持 Python / dbt / Spark / ORM 等「非纯 SQL」数据代码稳定产出 RDF 三元组。
2. 失败原因从笼统的「请确认含 SQL/ETL」变为**可操作的 `_git_diagnostics` 诊断**。
3. 规则抽取（确定性、可测）优先，LLM 兜底，降低空跑与成本。

---

## 2. 现状与缺口

| 能力 | 现状 | 缺口 |
|------|------|------|
| 语言识别 | 仅扩展名 glob | 无按语言路由 |
| 结构化解析 | 少量 regex（`codebase_analyzer` 路径） | 语义清洗路径几乎纯 LLM |
| JOIN | 要求 SQL 式 `join_key` | pandas/PySpark/ORM join 难入图 |
| 血缘 | 要求 `source_table` + `target_table` | 单表读写、链式 ETL 常为空 |
| 文件选取 | `_get_git_entries` limit=80、无 ORDER BY | 易漏 SQL/ETL 文件 |
| 失败提示 | `no_triples` 文案偏 SQL/ETL | 与 Python 等能力不符 |
| 双链路 | 同步后 `codebase_analyzer` vs 手动「语义清洗」 | 前者写 PG 元数据，后者写 RDF，用户易混淆 |

### 2.1 两条并行链路

```
Git 同步 → KnowledgeEntry (kind=git_file)
    ├─ [A] codebase_analyzer（同步后自动）→ TableKnowledgeEntry / PG 元数据
    └─ [B] orchestrator 语义清洗（手动/同步后 source:git）→ lineage + join → RDF
```

`no_triples` 仅来自路径 B。

### 2.2 语义清洗对 git 的实际步骤

- 默认 `enable_document_indexing=false` → 术语/指标等 chunk 步骤跳过（`no_document_chunks`）。
- 仅跑 `data_lineage` + `join_extraction`，读 `KnowledgeEntry.body`。
- 单文件门槛：`body.strip()` 长度 ≥ 50，否则静默跳过。
- 最多 80 条 entry，无扩展名优先排序。

### 2.3 已修复项（本方案实施前已完成）

- Git 同步后自动清洗使用 `source_type=source:git` + `source_id`（证据包状态可关联）。
- `no_triples` 时 pipeline 标记为 `failed`（不再假成功）。

---

## 3. 总体架构：三层抽取 + 语言路由

```
git_file KnowledgeEntry
    → 按扩展名/内容嗅探路由
    → 规则抽取 (code_patterns/*)
    → 统一 IR (LineageEdge / JoinEdge)
    → 转 RawTriple
    → LLM 补全（规则未命中或部分命中）
    → OntologyWriter 入图
```

**原则**：规则优先 → LLM 补全 → 仍无结果则输出分语言 `_git_diagnostics`。

---

## 4. 分阶段实施

### 阶段 P0：低成本、立刻见效（预估 1–2 天）

#### P0.1 修正文案与诊断

**文件**：`backend/services/extraction/pipeline_status.py`、`frontend/components/knowledge-bases/EvidencePackageList.tsx`

**`no_triples` 新文案（建议）**：

> 抽取已完成但未产生可入图三元组。请确认仓库含**表间依赖或 JOIN 类逻辑**（SQL/dbt/Python/Spark 等），且单文件正文 ≥50 字符；可在流水线步骤中查看 `_git_diagnostics`。

**orchestrator 失败时写入 `steps._git_diagnostics`**（示例结构）：

```json
{
  "total_entries": 120,
  "processed_entries": 80,
  "eligible_body_ge_50": 65,
  "by_ext": { ".py": 40, ".sql": 5, ".ts": 35 },
  "regex_hits": { "sql": 3, "pandas_merge": 0, "pyspark_join": 0 },
  "llm_lineage_triples": 0,
  "llm_join_triples": 0,
  "sample_paths": ["models/orders.sql", "etl/load_users.py"]
}
```

**前端**：证据包/流水线面板展示 `_git_diagnostics`（可折叠）。

#### P0.2 改进 `_get_git_entries` 选取策略

**文件**：`backend/services/extraction/orchestrator.py`

- `limit`：80 → **200**（或与 Git 源 `max_files` 对齐，取较小合理值）。
- **ORDER BY 扩展名优先级**：`.sql` > `.hql` > `.py` > `.yml`/`.yaml` > 其他（可用 SQL `CASE` 或 Python 侧排序）。
- 可选：Git 源 `extraction_profile=data_warehouse` 时过滤 `.ts/.tsx/.jsx` 不参与抽取（配置见 P3）。

#### P0.3 放宽 LLM Prompt（不改 RDF schema）

**文件**：`backend/prompts/lineage_extraction_system.txt`、`backend/prompts/join_extraction_system.txt`

**血缘 prompt 补充示例**：

- Python：`read_sql` / `to_sql` / `INSERT INTO ... SELECT`
- PySpark：`df.join()`、`createOrReplaceTempView` 链
- Airflow：`PostgresOperator(sql=...)`

**JOIN prompt 补充**：

- `pd.merge(..., on=...)`
- `DataFrame.join(..., on=...)`
- SQLAlchemy `.join(Model, ...)`

规则从「只提取显式 JOIN 语句」改为「**等价 JOIN 语义**（含 merge/join/on/condition）」。

#### P0 验收

- [x] 失败提示不再仅提 SQL/ETL
- [x] `steps._git_diagnostics` 可在 API/UI 看到
- [x] 大仓库中 `.sql` 文件优先进入抽取队列
- [x] 纯 `.sql` 含 JOIN 的 fixture 仍 `completed`

---

### 阶段 P1：规则抽取层 + Python 优先（预估 3–5 天）

#### P1.1 新建模块结构

```
backend/services/extraction/code_patterns/
  __init__.py
  ir.py              # LineageEdge, JoinEdge  dataclass
  sql.py             # 纯 .sql 文件
  python_sql.py      # 三引号 / f-string 内 SQL
  python_pandas.py   # merge/join/read_sql/to_sql
  python_spark.py    # PySpark join, sql()
  python_orm.py      # SQLAlchemy join, __tablename__
  dbt_yaml.py        # ref/source, models 依赖
  embedded_sql.py    # Java @Select, Go 反引号 SQL（P2 可扩）
  router.py          # 按 path 后缀 + 内容嗅探路由
  diagnostics.py     # 汇总 _git_diagnostics 统计
```

#### P1.2 统一中间表示（IR）

```python
@dataclass
class LineageEdge:
    source_table: str
    target_table: str
    source_field: str = ""
    target_field: str = ""
    layer: str = "DWD"
    transform_logic: str = ""
    confidence: float = 90.0
    provenance: str = "regex:pandas_merge"  # 可追溯

@dataclass
class JoinEdge:
    left_table: str
    right_table: str
    join_key: str
    join_type: str = "inner"
    confidence: float = 85.0
    provenance: str = "regex:pyspark_join"
```

#### P1.3 与 extractor 集成

**修改**：`lineage_extractor.py`、`join_extractor.py`

流程：

1. `router.extract(entry)` → `list[LineageEdge]` / `list[JoinEdge]`
2. IR 非空 → 转 `RawTriple`（现有逻辑）
3. IR 为空 → 现有 LLM 路径
4. 合并去重（`seen_pairs` / `seen_joins`）

#### P1.4 Python 规则（首期必做）

| 模式 | 血缘 | JOIN | 实现要点 |
|------|------|------|----------|
| `"""... SELECT ... FROM a JOIN b ..."""` | ✅ | ✅ | 抽出 SQL 子串，复用 `sql.py` |
| `pd.read_sql` + `df.to_sql('t2')` | ✅ read→write | — | 表名来自 SQL / 字面量 |
| `pd.merge(left, right, on=[...])` | — | ✅ | 变量名/上一行 read_sql 启发式推断表名 |
| `spark.sql(...)` / `df.join(...)` | ✅ | ✅ | SQL 子串或 join on 列 |
| SQLAlchemy `session.query(A).join(B)` | ⚠️ | ✅ | `__tablename__` 映射 |

**复用**：将 `codebase_analyzer.py` 中 `_RE_SQL_TABLE`、`_RE_ORM_TABLE`、`_RE_DBT_MODEL` 等抽到 `code_patterns/` 或 `codebase_regex.py`，分析器与清洗器共用。

#### P1.5 LLM 分工

- 规则 confidence ≥ 80：直接入图，可不调用 LLM（或仅对未覆盖 entry 调 LLM）。
- 规则部分命中：LLM 仅处理未命中文件。
- 规则全空：LLM 全量（现有行为）。

#### P1 验收

- [x] `fixtures/codebases/python_etl/`：pandas merge + 内嵌 SQL → join/lineage > 0
- [x] `fixtures/codebases/pure_sql/`：仅 .sql → completed
- [x] 单元测试覆盖各 `code_patterns/*.py`
- [x] `codebase_analyzer` 与 `code_patterns` 共用 regex，无重复维护

---

### 阶段 P2：dbt / Java / Go 内嵌 SQL（预估 2–3 天）

| 语言/格式 | 规则 |
|-----------|------|
| dbt YAML | `ref('x')` / `source('s','t')` → lineage |
| Java | `@Select("...JOIN...")`、MyBatis XML（若已同步） |
| Go | 反引号 SQL 字符串 |
| Scala | Spark `spark.table` / `.join` |

不做完整 AST，仅「内嵌 SQL 提取 + 框架关键字」。

#### P2 验收

- [x] `fixtures/codebases/dbt_mini/` → lineage > 0
- [x] `fixtures/codebases/java_mybatis/` → 至少 JOIN 或 lineage > 0

---

### 阶段 P3：Git 源配置与 UI（预估 1–2 天）

#### P3.1 抽取配置

扩展 `KnowledgeGitSource`（新 JSON 字段 `extraction_config` 或独立列）：

```json
{
  "extraction_profile": "data_warehouse",
  "prefer_extensions": [".sql", ".py", ".yml"],
  "enable_regex_extractors": true,
  "enable_llm_fallback": true,
  "min_body_chars": 30,
  "skip_extensions": [".ts", ".tsx", ".jsx"]
}
```

- `data_warehouse`：默认窄 glob，跳过前端代码
- `mixed`：宽 glob，诊断强调「未检测到表关系」

**API/UI**：`knowledge_git_sources` 创建/更新、Git 源编辑表单。

#### P3.2 默认 glob 调整（需产品确认）

当前默认：

```
*.md,*.sql,*.py,*.ts,*.tsx,*.java,*.go,*.rs,*.yml,*.yaml,*.json
```

建议新 Git 源默认：

```
*.sql,*.py,*.yml,*.yaml,*.hql
```

已有源不强制迁移，可在 UI 提示优化 glob。

#### P3 验收

- [x] Git 源可配置 `extraction_profile`
- [x] 证据包失败时 UI 展示 `_git_diagnostics`

---

### 阶段 P4（可选）：扩展入图类型 `CodeTableReference`

**问题**：仅 `read_sql('orders')` 无下游时，Lineage/Join 均为空 → `no_triples`。

**方案 A（推荐，P1 内尽量做）**：规则将 `read_sql(A)` + `to_sql(B)` 凑成 lineage A→B；仅 read 无 write → 不入 RDF，但在 `_git_diagnostics.single_table_refs` 计数并提示。

**方案 B（P4 可选）**：新增 `dl:CodeTableReference` + SHACL + 五层 UI 展示。

实施 P4 前需确认产品是否接受新本体类型。

---

## 5. 测试策略

### 5.1 Fixture 仓库（建议路径）

```
backend/tests/fixtures/codebases/
  pure_sql/          # 仅 .sql → 必须 completed
  python_etl/        # pandas + 内嵌 SQL → join/lineage > 0
  python_app/        # FastAPI 无表关系 → failed + 明确 diagnostics
  dbt_mini/          # ref/source → lineage > 0
  java_mybatis/      # @Select JOIN → P2
```

### 5.2 测试文件（建议）

- `test_code_patterns_*.py`：各规则模块
- `test_git_extraction_integration.py`：orchestrator 端到端（mock LLM）
- 扩展 `test_git_evidence_packages.py`、`test_extraction_pipeline_status.py`

### 5.3 总体验收标准

| 场景 | 期望 |
|------|------|
| 含 JOIN 的 `.sql` | lineage + join > 0，`completed` |
| pandas merge + read_sql | join > 0 |
| 纯 CRUD Python 无表间关系 | `failed`，diagnostics 说明「无表间依赖」或 `single_table_refs` |
| 80+ 文件仓库 | `.sql` 优先被处理 |
| 失败信息 | 不单提 SQL/ETL，含 `_git_diagnostics` |

---

## 6. 实施顺序（新会话执行清单）

```
[x] P0.1  no_triples 文案 + FAILURE_REASON_LABELS
[x] P0.2  orchestrator _git_diagnostics + diagnostics.py 骨架
[x] P0.3  _get_git_entries limit/排序
[x] P0.4  放宽 lineage/join prompts
[x] P1.1  code_patterns/ 模块 + ir.py + router.py
[x] P1.2  从 codebase_analyzer 抽取共用 regex
[x] P1.3  python_sql / python_pandas / python_spark / python_orm / sql.py
[x] P1.4  接入 lineage_extractor + join_extractor
[x] P1.5  fixture python_etl + pure_sql + 单测
[x] P2.1  dbt_yaml.py + embedded_sql.py
[x] P2.2  fixture dbt_mini + java_mybatis
[x] P3.1  KnowledgeGitSource extraction_config + API
[x] P3.2  前端 Git 源表单 + EvidencePackage 诊断展示
[x] P3.3  （可选）默认 include_globs 调整
[x] 文档  更新 ONTOLOGY_LAYER_UI_OPTIMIZATION.md 中代码库清洗说明
```

> 实施状态（2026-05-30）：以上项均已落地。

---

## 7. 风险与取舍

| 风险 | 缓解 |
|------|------|
| pandas 变量名 ≠ 表名 | 启发式 + LLM 兜底；diagnostics 标明低置信 |
| 单表脚本无 RDF | 方案 A diagnostics；必要时 P4 CodeTableReference |
| LLM 成本 | 规则前置，预计 60–80% ETL 文件免 LLM |
| regex 双份维护 | 统一到 `code_patterns/`，analyzer 引用 |
| SHACL 变更 | P4 前不做新类型；P1 只用 LineageAssertion + JoinRelation |

---

## 8. 待产品拍板（实施前可默认）

1. **首期语言**：P1 仅 Python + SQL + dbt；Java/Go 放 P2。（**默认采纳**）
2. **单表引用**：暂不入 RDF，仅 diagnostics。（**默认采纳方案 A**）
3. **默认 glob**：新源改为 `*.sql,*.py,*.yml,*.yaml,*.hql`；老源不动。（**默认采纳，UI 提示**）

---

## 9. 新会话启动提示词（复制即用）

```
请按 docs/CODEBASE_MULTI_LANGUAGE_EXTRACTION_PLAN.md 全量实施代码库多语言语义抽取改造（P0→P1→P2→P3，P4 可选不做除非方案 A 不足）。

要求：
1. 按文档第 6 节清单逐项完成并勾选
2. 添加 fixture 与单测，跑 pytest 相关用例
3. 保持最小 diff，复用现有 OntologyWriter / RawTriple 路径
4. 完成后简要说明变更文件与如何验证
```

---

## 10. 关键文件索引

| 文件 | 改动类型 |
|------|----------|
| `backend/services/extraction/orchestrator.py` | P0 diagnostics、entry 排序 |
| `backend/services/extraction/lineage_extractor.py` | P1 接入 code_patterns |
| `backend/services/extraction/join_extractor.py` | P1 接入 code_patterns |
| `backend/services/extraction/pipeline_status.py` | P0 文案 |
| `backend/services/codebase_analyzer.py` | P1 regex 抽取到共用模块 |
| `backend/services/extraction/code_patterns/*` | P1/P2 新建 |
| `backend/prompts/lineage_extraction_system.txt` | P0 放宽 |
| `backend/prompts/join_extraction_system.txt` | P0 放宽 |
| `backend/models.py` + `knowledge_git_sources.py` | P3 extraction_config |
| `frontend/components/knowledge-bases/EvidencePackageList.tsx` | P0/P3 diagnostics UI |
| `frontend/app/knowledge-bases/[id]/page.tsx` | P3 Git 源配置（若需要） |
