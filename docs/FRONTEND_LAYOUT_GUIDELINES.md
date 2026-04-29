# Frontend Layout Guidelines

本文档沉淀 DataLens 前端常用布局类，目标是让搜索框、按钮、列表和输入区在不同页面保持一致。

## 1) 页面头部与操作区

- 页面头部统一使用 `PageHeader`（内部为 `app-page-header` + `app-page-header-actions`）。
- 头部按钮和筛选输入建议放进 `app-toolbar`。
- 搜索输入使用 `app-input app-toolbar-input`。
- 操作按钮使用 `app-button app-toolbar-action`（次按钮用 `app-button-secondary`）。

示例：

```tsx
<div className="app-toolbar">
  <input className="app-input app-toolbar-input" placeholder="搜索..." />
  <button className="app-button app-toolbar-action">新增</button>
</div>
```

## 2) 列表项与操作按钮

- 列表卡片统一基类：`app-card app-card-interactive`。
- 列表结构优先使用：
  - `app-list-item`（整体）
  - `app-list-item-main`（主信息）
  - `app-list-item-actions`（操作区）
- 移动端默认上下结构，桌面端自动左右分栏。

示例：

```tsx
<div className="app-card app-card-interactive app-list-item p-4">
  <div className="app-list-item-main">...</div>
  <div className="app-list-item-actions">
    <button className="app-button">操作</button>
  </div>
</div>
```

## 3) 分页区

- 统一使用 `ListPagination` 组件。
- 分页容器需与卡片风格一致（边框、背景、圆角）。
- 页码显示建议固定最小宽度，避免翻页时跳动。

## 4) 输入框与多行输入

- 单行输入：统一使用 `app-input`。
- 多行输入：统一使用 `app-textarea`。
- 组合输入区域（如 Copilot 输入框）使用：
  - `app-composer`（容器）
  - `app-textarea`（文本输入）
  - `app-composer-footer`（底部按钮/提示）

示例：

```tsx
<div className="app-composer">
  <textarea className="app-textarea" placeholder="输入问题..." />
  <div className="app-composer-footer">
    <button className="app-button">发送</button>
  </div>
</div>
```

## 5) 文本与语义颜色

- 辅助文案：`app-text-muted`
- 次级正文：`app-text-secondary-strong`
- 链接：`app-link`

避免在业务页面中重复硬编码颜色（如 `text-[#xxxxxx]`），优先复用语义类。

## 6) 响应式约定

- 搜索框优先可用：小屏让输入框占满，再放按钮。
- 操作区允许换行，避免按钮挤压文本。
- 长文本（表名/描述）需加 `break-all` 或 `break-words`。

## 7) 新页面落地检查清单

- 是否使用 `PageHeader` + `app-toolbar`？
- 搜索输入是否为 `app-input app-toolbar-input`？
- 列表是否采用 `app-list-item` 三段式结构？
- 分页是否使用 `ListPagination`？
- 多行输入是否使用 `app-composer` + `app-textarea`？
- 是否尽量使用语义类而非硬编码颜色？
