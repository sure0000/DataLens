# DataLens 实现说明（研发视角，AI可读）

## 1) 文档用途

本文件用于让任意 AI/开发者快速定位：

- 系统分层与代码入口
- 核心数据流和模块职责
- 关键数据模型与 API
- 已知约束、风险和改造方向

## 2) 技术栈

- 后端：Python + FastAPI + SQLAlchemy
- 存储：PostgreSQL + pgvector
- 连接器：PyMySQL、clickhouse-driver
- LLM：DeepSeek（主）/ OpenAI（备）
- Embedding：`text-embedding-3-small`（1536维），可本地兜底
- 前端：Next.js App Router + TypeScript + Tailwind

## 3) 代码结构（高价值目录）

- `backend/main.py`：应用入口、CORS、路由注册
- `backend/database.py`：engine/session、建表与扩展初始化
- `backend/models.py`：ORM 模型
- `backend/routers/`：API 路由层
- `backend/services/`：核心业务逻辑层
- `frontend/app/`：页面路由
- `frontend/components/`：通用组件
- `frontend/lib/api.ts`：前端 API 调用封装

## 4) 后端分层职责

### 4.1 Router 层

职责：请求参数校验、入口编排、调用服务。

主要路由：

- `connect.py`：连接测试与表列表获取
- `analyze.py`：异步分析调度（表级）
- `datasources.py`：数据源 CRUD、目录浏览、范围分析触发
- `tables.py`：表列表与表详情聚合返回
- `copilot.py`：问答接口 + SSE 流式输出
- `business_domains.py`：业务域、描述、库表选择管理

### 4.2 Service 层

职责：封装可复用业务能力。

- `schema_extractor.py`
  - MySQL/ClickHouse 的库表字段抽取
  - 获取 DDL、样本、行数
  - 执行只读 SQL（白名单前缀校验）
- `profiler.py`
  - 字段统计与质量指标计算
  - 风险等级推断（low/medium/high）
- `llm_service.py`
  - 字段语义分析、表总结、SQL 生成
  - JSON 输出解析重试
  - 无 API Key 的规则兜底
- `embedding_service.py`
  - 向量化写入与相似检索
  - 无 Key 的 deterministic 本地向量兜底
- `rag_service.py`
  - 拼接优先上下文（数据源信息 + AI 分析信息 + 历史问答）
  - 调用 SQL 生成
  - 写入 query history 并执行 SQL 返回结果

## 5) 核心数据流（实现视角）

### 5.1 分析链路

1. 路由创建 `tables` 记录（`pending`）
2. 异步任务将状态改为 `analyzing`
3. 抽取字段、样本、行数、DDL
4. `profiler` 计算质量指标
5. `llm_service` 生成字段语义
6. 写入 `columns` 与向量 `embeddings`
7. 生成表总结并写入 `table_summary`
8. 状态置为 `done`（异常则 `error`）

### 5.2 Copilot 链路

1. 接收 `question` + 可选 `table_id`
2. 向量检索历史上下文
3. 拼接结构化 schema 与摘要信息
4. 调用 LLM 生成 SQL 与解释
5. 写入 `query_examples` 与 query embedding
6. 在目标数据源执行只读 SQL
7. 返回 SQL + explanation + query_result

## 6) 关键数据模型

- `DataSource`：数据源连接配置（含 name/source_type/host/port/database/username/password）
- `TableMeta`：表级状态与基础信息
- `ColumnMeta`：字段语义、可用性、质量画像
- `TableSummary`：表用途总结
- `QueryExample`：历史问答
- `Embedding`：RAG 检索向量
- `BusinessDomain*`：业务域及其描述/库表选择

## 7) API 族群（按能力）

- 连接与分析入口
  - `POST /api/connect`
  - `POST /api/analyze/{table_name}`
- 数据源管理
  - `GET/POST/PUT/DELETE /api/datasources`
  - `POST /api/datasources/test`
  - `GET /api/datasources/{id}/catalog`
  - `GET /api/datasources/{id}/databases/{db}/catalog`
  - `POST /api/datasources/{id}/analyze/table/{table_name}`
  - `POST /api/datasources/{id}/analyze/database/{database_name}`
  - `POST /api/datasources/{id}/analyze/datasource`
- 表详情
  - `GET /api/tables`
  - `GET /api/table/{table_id}`
- Copilot
  - `POST /api/ask`
  - `POST /api/ask/stream`
- 业务域
  - `GET/POST/DELETE /api/business-domains`
  - `GET /api/business-domains/{id}`
  - `GET /api/business-domains/options`
  - 描述与选择的增改接口

## 8) 前端信息架构

- `/`：业务域列表
- `/business-domains/[id]`：业务域详情（描述+库表选择）
- `/datasources`：数据源管理
- `/datasources/[id]`：数据源目录
- `/datasources/[id]/database/[db]`：数据库目录与分析
- `/table/[id]`：表详情画像
- `/copilot`：会话式 ChatBI

## 9) 环境变量与运行依赖

必需/关键变量：

- `DATABASE_URL`
- `DEEPSEEK_API_KEY`（可空，空则走兜底）
- `OPENAI_API_KEY`（用于 embedding 与备选 LLM）
- `NEXT_PUBLIC_API_URL`

运行端口默认：

- backend: `8000`
- frontend: `3000`

## 10) 现有限制与风险

- `data_sources.password` 明文存储（需加密）
- SQL 安全仅做语句前缀白名单（建议升级 AST 级校验）
- 分析任务为进程内异步/线程，不适合高并发队列化场景
- 前端存在 `dangerouslySetInnerHTML` 渲染点，需要输入清洗

## 11) 推荐演进路线（给 AI/开发的优先级）

P0：

- 数据源凭据加密存储
- 异步任务队列化（Celery/RQ）
- SQL AST 安全校验

P1：

- 增加可观测性（链路日志、模型耗时、错误分类）
- 将“业务域过滤”接入 Copilot 上下文

P2：

- 多用户与权限体系
- 协作与治理能力

## 12) 与初始设计的关键差异（实现层）

- 设计文档中 Copilot 为“只生成 SQL”，当前实现已支持“生成 + 执行 + 返回预览”。
- 新增业务域模型与页面，不再仅围绕“表列表 -> 表详情 -> Copilot”单线流程。
- 为提升联调可用性，增加了 LLM 与 embedding 的无 Key 兜底路径。

## 13) 参考资料

- 初始设计文档：[DataLens MVP 产品设计文档](https://www.notion.so/xuyouchang/DataLens-MVP-35045c17aec08175b54fc43d811c90f9?source=copy_link)
- 仓库说明：`README.md`
