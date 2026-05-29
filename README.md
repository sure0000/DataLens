# DataLens — 数据表智能理解与自然语言分析系统

DataLens 是一个轻量级 ChatBI 系统：连接数据源 → 自动理解表结构和字段含义 → 维护业务语义知识库 → 自然语言生成 SQL → 只读执行预览。

**详细架构、数据流、数据模型、API 文档：** 见 [`docs/DATALENS_OVERVIEW.md`](docs/DATALENS_OVERVIEW.md)。

## 文档索引

| 文档 | 说明 |
|------|------|
| [DATALENS_OVERVIEW.md](docs/DATALENS_OVERVIEW.md) | 项目全貌（推荐首读） |
| [ONTOLOGY_LAYER_UI_OPTIMIZATION.md](docs/ONTOLOGY_LAYER_UI_OPTIMIZATION.md) | 本体三层 UI（导入层证据包、KB 建模与质量、业务域五层语义资产浏览） |
| [企业语义层与域内自治实践.md](docs/企业语义层与域内自治实践.md) | 语义层理念、存储结构、联邦治理 |
| [COPILOT_ROUTING_OPTIMIZATION.md](docs/COPILOT_ROUTING_OPTIMIZATION.md) | Copilot 多信号路由与 trace |
| [SEMANTIC_LAYER_OPTIMIZATION_BACKLOG.md](docs/SEMANTIC_LAYER_OPTIMIZATION_BACKLOG.md) | 语义层能力清单与实现状态 |

---

## 环境准备与启动

## 1. 环境准备

- Python `3.11+`（本地后端）
- Node.js `18+`（本地前端）
- PostgreSQL（建议 15+，需安装 `pgvector` 扩展）
- 可选：Docker / Docker Compose（用于容器化启动）

## 2. 配置环境变量

项目根目录已有 `.env.example`，复制为 `.env` 并填写真实值：

```bash
cp .env.example .env
```

关键变量说明：

- `DATABASE_URL`：后端连接的 PostgreSQL 地址
- `DB_SCHEMA_MANAGEMENT_MODE`：`legacy`（默认，启动时自动补丁）或 `alembic`（仅依赖 Alembic 迁移）
- `DEEPSEEK_API_KEY`：DeepSeek Key（主）
- `OPENAI_API_KEY`：OpenAI Key（备）
- `BACKEND_PORT`：后端端口，默认 `8000`
- `FRONTEND_PORT`：前端端口，默认 `3000`
- `NEXT_PUBLIC_API_URL`：前端调用后端地址（本地建议 `http://localhost:8000`）
- `API_AUTH_ENABLED`：后端 API 鉴权开关（默认 `true`）
- `API_AUTH_TOKEN`：后端 Bearer Token（默认 `datalens-dev-token`）
- `NEXT_PUBLIC_API_TOKEN`：前端调用 API 时携带的 Bearer Token（需与后端一致）
- `FUSEKI_IMAGE`：Fuseki Docker 镜像地址（默认 `stain/jena-fuseki:4.10.0`，网络受限时可替换为镜像代理地址）
- `COPILOT_MAX_TABLES_WITHOUT_DOMAIN`：未选业务域时语义 top_k 表上限（默认 `20`）
- `SEMANTIC_AUTO_APPROVE_CONFIDENCE`：术语/指标提取置信度 ≥ 此值自动 `approved`（默认 `80`）
- `SEMANTIC_CHUNK_STRUCTURE_MAX`：单文档语义结构化最多处理的 chunk 数（默认 `40`）
- **本体层 / 存储**（Formal OWL，见 [`docs/ONTOLOGY_CUTOVER.md`](docs/ONTOLOGY_CUTOVER.md)）：
  - **默认**：Fuseki（`FUSEKI_URL=http://localhost:3030`），可用 Docker 或本地 Java Fuseki
  - `./scripts/fuseki.sh start`：单独启动 Docker Fuseki（`./scripts/service.sh start local` 不会自动拉起 Docker）
  - 调试回退：显式设置 `ONTOLOGY_LOCAL_STORE_ENABLED=true` 才写入本地 Trig 文件

更多 Copilot 路由相关变量见 [`docs/COPILOT_ROUTING_OPTIMIZATION.md`](docs/COPILOT_ROUTING_OPTIMIZATION.md) §5。

## 3. 本地启动后端（FastAPI）

在项目根目录执行：

```bash
python3 -m pip install -r backend/requirements.txt
```

然后启动后端：

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

预期返回：

```json
{"ok": true}
```

鉴权验证（除 `/health` 外接口默认要求 Bearer Token）：

```bash
curl -H "Authorization: Bearer ${API_AUTH_TOKEN}" http://localhost:8000/api/knowledge-bases
```

## 4. 本地启动前端（Next.js）

新开一个终端，在项目根目录执行：

```bash
cd frontend
npm install
npm run dev
```

访问：

- 前端首页：`http://localhost:3000`
- Copilot 页面：`http://localhost:3000/copilot`

## 5. 容器方式启动（可选）

如果本机已安装 Docker，可在项目根目录执行：

```bash
./scripts/service.sh start docker
```

停止容器：

```bash
./scripts/service.sh stop docker
```

默认端口：

- 前端：`3000`
- 后端：`8000`
- PostgreSQL：`5432`

## 6. 常见问题

- `command not found: docker`：本机未安装 Docker，使用“本地启动方式”即可。
- 前端请求失败：确认 `.env` 中 `NEXT_PUBLIC_API_URL` 指向正确后端地址；访问前端时勿混用 `localhost` 与 `127.0.0.1`（可配置 `CORS_ORIGINS`，见 `.env.example`）。
- 知识库建模：在详情页**导入源卡片**点击「语义清洗」；**建模与质量**（`#modeling`）含 **流水线**、**五层结果**（实体概念层支持列表/树形）、**质量与隔离**（KPI + 待办隔离区 / 指标 SHACL·置信度）。详见 [`docs/ONTOLOGY_LAYER_UI_OPTIMIZATION.md`](docs/ONTOLOGY_LAYER_UI_OPTIMIZATION.md) §5.3.1。
- 语义资产浏览：侧栏选择业务域后进入 **语义资产**（`/ontology`），按五层（实体概念 / 关系 / 规则 / 属性 / 词汇）聚合域内已入图资产，支持 `?kb=` 筛选与来源追溯。详见同上文档 §5.5。
- 后端启动时报数据库错误：确认 PostgreSQL 已启动、`DATABASE_URL` 正确、并已启用 `pgvector`。
- SQL Copilot 空结果：检查 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` 是否有效。

## 运行目录约定

- `.run/`：运行时状态目录（日志、PID、Fuseki 数据），默认不入库。
- `run/`：本地临时安装产物目录（例如 Fuseki 解压模板），默认不入库。
- `scripts/`：可复用脚本入口（建议把可执行流程固定在这里）。

## 7. 开发约定（重启服务）

- 每次修改代码后，必须重启前后端服务：
```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN | awk 'NR>1 {print $2}' | xargs -I{} kill {}
lsof -nP -iTCP:8000 -sTCP:LISTEN | awk 'NR>1 {print $2}' | xargs -I{} kill {}
```
- 然后分别启动：
```bash
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
cd frontend && npm run dev
```
- 启动后必须做健康检查：
```bash
curl http://localhost:8000/health
curl -I http://localhost:3000
```
