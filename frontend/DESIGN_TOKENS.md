# DataLens Frontend Design Tokens

## 视觉基调
- 深色夜景背景 + 青蓝品牌高光。
- 内容层级通过 `surface`、边框透明度和阴影区分，而不是依赖大面积纯黑灰。

## 核心变量（`app/globals.css`）
- `--app-main-bg` / `--app-sidebar-bg` / `--app-surface-modal`
- `--app-card-bg` / `--app-card-border`
- `--app-text-primary` / `--app-text-secondary`
- `--app-primary` / `--app-primary-hover`
- `--app-accent-cyan` / `--app-accent-indigo`

## 组件语义类
- **容器**
  - `app-card`: 标准内容卡片
  - `app-surface-panel`: 浮层面板（Toast/空状态等）
  - `app-modal-surface`: 对话框主体
  - `app-dropdown-surface`: 下拉菜单主体
- **文字**
  - `app-text-primary`: 主文本
  - `app-text-secondary`: 次文本
  - `app-text-muted`: 弱提示文本
  - `app-text-secondary-strong`: 强次级文本
- **交互**
  - `app-button` / `app-button-secondary` / `app-button-danger`
  - `app-control-button`
  - `app-card-interactive`: 可悬停卡片反馈

## 页面结构约定
- 页面头优先使用 `PageHeader`（标题/副标题/操作区）。
- 表单标签优先使用 `app-form-label`。
- 空状态统一使用 `EmptyState`，提示统一使用 `Toast`，确认统一 `ConfirmDialog`。

## 新增样式时的规则
- 优先复用语义类，不直接写 `text-[#...]`、`bg-[#...]`。
- 先定义 token，再在组件层组合；避免页面局部“重新发明一套颜色”。
- 动效保持轻量，遵守 `prefers-reduced-motion`。
