# DataLens 设计 Token — ChatGPT 深色主题

## 视觉基调
- **深色主题**，背景 `#212121`，侧栏 `#171717`，受 ChatGPT 设计语言启发。
- 品牌主色为 **ChatGPT 绿** `#10a37f`，用于主按钮、链接、激活态。
- 内容层级通过透明度微妙的白色边框 (`rgba(255,255,255,0.06~0.1)`) 和分层背景区分，而非大面积阴影。
- 整体风格扁平、干净、低阴影。

## 核心变量（`app/globals.css`）

### 背景层
| 变量 | 值 | 用途 |
|---|---|---|
| `--app-main-bg` | `#212121` | 主内容区背景 |
| `--app-sidebar-bg` | `#171717` | 侧栏背景（比主内容更暗） |
| `--app-elevated-bg` | `#2f2f2f` | 浮层、弹窗等上层表面 |
| `--app-surface-modal` | `#2f2f2f` | 模态框主体 |
| `--app-card-bg` | `#2f2f2f` | 卡片背景 |

### 品牌色
| 变量 | 值 | 用途 |
|---|---|---|
| `--app-primary` | `#10a37f` | ChatGPT 绿 — 主按钮、链接 |
| `--app-primary-hover` | `#0d8c6d` | 主色悬停态 |
| `--app-primary-text` | `#ffffff` | 主按钮文字 |
| `--app-accent-cyan` | `#22d3ee` | 青蓝高光 |
| `--app-accent-indigo` | `#818cf8` | 靛蓝高光 |

### 文字
| 变量 | 值 | 用途 |
|---|---|---|
| `--app-text-primary` | `#f0f0f0` | 主文字（近白） |
| `--app-text-secondary` | `#b4b4b4` | 次文字 |
| `--app-text-ink` | `#d0d0d0` | 强调级次文字 |
| `--app-text-placeholder` | `#6b6b6b` | 占位提示文字 |

### 边框 & 表面
| 变量 | 值 | 用途 |
|---|---|---|
| `--app-card-border` | `rgba(255,255,255,0.1)` | 卡片/组件边框 |
| `--app-border-subtle` | `rgba(255,255,255,0.08)` | 弱分割线 |
| `--app-surface-hover` | `rgba(255,255,255,0.07)` | 悬停高亮 |
| `--app-active-bg` | `rgba(16,163,127,0.12)` | 激活态背景（绿） |
| `--app-active-border` | `rgba(16,163,127,0.4)` | 激活态边框（绿） |

### 语义色
| 变量 | 值 |
|---|---|
| `--app-danger` | `#ef4444` |
| `--app-warning` | `#f59e0b` |
| `--app-success` | `#10a37f`（复用品牌绿） |
| `--app-info` | `#60a5fa` |

## 组件语义类

### 容器
- `app-card` — 标准内容卡片（`#2f2f2f` + 白色半透明边框）
- `app-surface-panel` — 浮层面板
- `app-modal-surface` — 对话框主体
- `app-dropdown-surface` — 下拉菜单主体

### 文字
- `app-text-primary` — 主文本（近白）
- `app-text-secondary` — 次文本（浅灰）
- `app-text-muted` — 弱提示文本
- `app-text-secondary-strong` — 强调次文本

### 交互
- `app-button` — ChatGPT 绿主按钮（圆角 pill 形状）
- `app-button-secondary` — 透明次按钮（白色描边）
- `app-button-danger` — 红色危险按钮
- `app-control-button` — 小型图标按钮（透明 hover 高亮）
- `app-card-interactive` — 可悬停卡片反馈

### 表单
- `app-input` — 深色输入框（半透明白底 + 深色文字）
- `app-form-label` — 表单标签
- `app-field-error` — 字段错误提示
- `app-textarea` — 文本域

## 间距
- `--app-space-page-x` / `--app-space-page-y` — 页面水平/垂直内边距
- `--app-space-section` — 章节间距

## 圆角
- 卡片：`18px`（`--app-card-radius`）
- 按钮：`999px`（pill 全圆角）
- 输入框：`0.8rem`
- 弹层按钮：`0.625rem`

## 新增样式时的规则
- 优先复用语义类，不直接写 `text-[#...]`、`bg-[#...]`。
- 先定义 token，再在组件层组合；避免页面局部"重新发明一套颜色"。
- 动效保持轻量，遵守 `prefers-reduced-motion`。
- 新组件默认适配深色主题，不使用 `bg-white` 等亮色硬编码。
