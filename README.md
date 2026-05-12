# DataLens — 数据表智能理解与自然语言分析系统

DataLens 是一个轻量级 ChatBI 系统：连接数据源 → 自动理解表结构和字段含义 → 自然语言生成 SQL → 只读执行预览。

**详细架构、数据流、数据模型、API 文档：** 见 [`docs/DATALENS_OVERVIEW.md`](docs/DATALENS_OVERVIEW.md)。

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
- `DEEPSEEK_API_KEY`：DeepSeek Key（主）
- `OPENAI_API_KEY`：OpenAI Key（备）
- `BACKEND_PORT`：后端端口，默认 `8000`
- `FRONTEND_PORT`：前端端口，默认 `3000`
- `NEXT_PUBLIC_API_URL`：前端调用后端地址（本地建议 `http://localhost:8000`）

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
docker compose up --build
```

默认端口：

- 前端：`3000`
- 后端：`8000`
- PostgreSQL：`5432`

## 6. 常见问题

- `command not found: docker`：本机未安装 Docker，使用“本地启动方式”即可。
- 前端请求失败：确认 `.env` 中 `NEXT_PUBLIC_API_URL` 指向正确后端地址。
- 后端启动时报数据库错误：确认 PostgreSQL 已启动、`DATABASE_URL` 正确、并已启用 `pgvector`。
- SQL Copilot 空结果：检查 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` 是否有效。

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
