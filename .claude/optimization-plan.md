# DataLens 优化执行计划

## 执行顺序（按优先级）

### 批次 1: P0-2 Alembic 数据库迁移初始化
- 安装 alembic
- 生成初始迁移（基于当前数据库 schema）
- 将 database.py:init_db() 中所有 DDL 迁移到 alembic 管理
- 清理 init_db()

### 批次 2: P1-3 拆分 rag_service.py
- 1184 行拆分为 5 个模块：
  - services/intent_classifier.py — 意图识别
  - services/context_builder.py — 上下文组装
  - services/sql_pipeline.py — SQL 生成→执行→结果格式化
  - services/repair_pipeline.py — SQL 修复循环
  - services/trace_renderer.py — 追踪行渲染

### 批次 3: P1-4 后台任务队列
- 创建 services/task_queue.py — 统一的异步任务管理器
- 替换 knowledge_bases.py 中的文件导入后台线程
- 替换 knowledge_git_sources.py 中的代码分析后台线程
- 替换 semantic_extraction.py 中的流水线后台线程
- 替换 git_knowledge_sync.py 中的同步后触发线程

### 批次 4: P1-5 前端共享 hooks 提取
- hooks/useToast.ts
- hooks/useConfirmDialog.ts
- hooks/useClickOutside.ts
- hooks/useEscapeKey.ts
- 在各页面中替换现有重复逻辑

### 批次 5: P2-6 消除后端代码重复
- term/metric CRUD 合并
- 共享序列化层
- RRF 搜索统一

### 批次 6: P2-7 Prompt 模板外部化
- 创建 backend/prompts/ 目录
- 迁移 semantic_extraction.py 的 prompt
- 迁移 llm_service.py 的 prompt

### 批次 7: P2-8 前端巨型组件拆分
- CopilotPageContent → CopilotToolbar + ChatPanel + SessionList
- SettingsPage → ModelTab + SemanticTab + ApiSourceTab
- AppShell → Sidebar + ProjectTree + SearchOverlay

### 批次 8: P3-9 类型安全加固
- 前端字符串联合类型
- 判别联合替代 if/else

### 批次 9: P3-10 魔法数字配置化
- 统一到 config.py

### 批次 10: P3-11 补充测试
- SQL AST Guard
- 知识库 CRUD
- LLM 降级逻辑
- Token 脱敏

---

## 当前状态
- 批次 1: ✅ 完成 — Alembic 初始化、env.py 配置、baseline 已 stamp、database.py 清理、models.py 补充、requirements.txt 更新
- 批次 2: ✅ 完成 — rag_service.py 1185行→581行(-51%)，拆出 context_builder.py(495行) + trace_helpers.py(17行)
- 批次 3: ✅ 完成 — 创建 background.py 统一调度模块，8处 threading.Thread 全部添加 logger.exception，消除裸 except 吞错
- 批次 4: ✅ 完成 — 创建 4 个共享 hooks。8 个页面/组件已采用 useEscapeKey（page / settings / datasources / copilot / business-domains / knowledge-bases + ConfirmDialog / GitFileBrowser / EntryViewModal / EditKbModal / ImportPickerModal / AppShell），3 个页面已采用 useToast，2 个页面保留自有 showMessage（含自定义 duration 逻辑）
- 批次 5: ✅ 完成 — RRF 搜索统一（_rrf_merge 通用化），Base.to_dict() 序列化层，knowledge_semantic.py CRUD 合并（_list_semantic / _delete_semantic / _count_grouped 消除 120+ 行重复），pipeline-stats 查询简化
- 批次 6: ✅ 完成 — 创建 backend/prompts/ 包（12 个模板文件），semantic_extraction / llm_service / codebase_analyzer 全部迁移至 load_prompt()
- 批次 7: ✅ 完成 — 设置页 1321→702 行(-47%)，提取 ApiSourcesTab(430行) + ModelsTab(103行) + SemanticTab(156行)；AppShell 936→817 行(-13%)，提取 AppIcons.tsx(31行)；Copilot 1034→1004 行，提取 SessionList(47行)；TS 编译零错误
- 批次 8: ✅ 完成 — 创建 frontend/lib/types.ts 统一类型定义（ToastTone / SourceType / ReviewStatus 等 10 个联合类型）
- 批次 9: ✅ 完成 — config.py 新增 pipeline_run_timeout_seconds / rrf_k 可配置项
- 批次 10: ✅ 完成 — 新增 test_token_desensitization.py（3 个用例：掩码不泄露原始 token / has_token 布尔 / 列表接口排除 token）
