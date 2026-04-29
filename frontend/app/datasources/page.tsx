"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import ConfirmDialog from "../../components/ConfirmDialog";
import EmptyState from "../../components/EmptyState";
import ListPagination from "../../components/ListPagination";
import LoadingSkeletonList from "../../components/LoadingSkeletonList";
import PageHeader from "../../components/PageHeader";
import Toast from "../../components/Toast";

type DataSource = {
  id: number;
  name: string;
  source_type: string;
  description?: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
};

const emptyForm = {
  name: "本地MySQL",
  source_type: "mysql",
  description: "本地测试库",
  host: "127.0.0.1",
  port: 3306,
  database: "ecommerce",
  username: "root",
  password: ""
};

function getDefaultFormByType(sourceType: string) {
  if (sourceType === "clickhouse") {
    return {
      ...emptyForm,
      name: "本地ClickHouse",
      source_type: "clickhouse",
      port: 9000
    };
  }
  return { ...emptyForm, source_type: "mysql", port: 3306 };
}

export default function DataSourcesPage() {
  const [form, setForm] = useState(emptyForm);
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<string>("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalStep, setModalStep] = useState<"type" | "form">("type");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await api<{ datasources: DataSource[] }>("/api/datasources");
      setDatasources(res.datasources);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [keyword, pageSize]);

  useEffect(() => {
    if (!isModalOpen) return;
    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") resetAndCloseModal();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isModalOpen]);

  async function create() {
    setSubmitting(true);
    try {
      await api("/api/datasources", { method: "POST", body: JSON.stringify(form) });
      resetAndCloseModal();
      load();
    } finally {
      setSubmitting(false);
    }
  }

  async function testCurrent() {
    const res = await api<{ success: boolean; tables_count?: number; sample_tables?: string[]; error?: string }>(
      "/api/datasources/test",
      { method: "POST", body: JSON.stringify(form) }
    );
    if (res.success) {
      setTestResult(`连接成功，发现 ${res.tables_count} 张表：${(res.sample_tables ?? []).join(", ")}`);
      return;
    }
    setTestResult(`连接失败：${res.error ?? "unknown error"}`);
  }

  async function testSaved(id: number) {
    const res = await api<{ success: boolean; tables_count?: number; sample_tables?: string[]; error?: string }>(
      `/api/datasources/${id}/test`,
      { method: "POST" }
    );
    if (res.success) {
      setTestResult(`连接成功，发现 ${res.tables_count} 张表：${(res.sample_tables ?? []).join(", ")}`);
      return;
    }
    setTestResult(`连接失败：${res.error ?? "unknown error"}`);
  }

  async function update() {
    if (!editingId) return;
    setConfirmState({
      title: "确认更新数据源？",
      description: "将使用当前表单内容覆盖原有数据源配置。",
      confirmText: "确认更新",
      action: async () => {
        setSubmitting(true);
        try {
          await api(`/api/datasources/${editingId}`, { method: "PUT", body: JSON.stringify(form) });
          resetAndCloseModal();
          load();
        } finally {
          setSubmitting(false);
        }
      }
    });
  }

  async function remove(id: number) {
    const target = datasources.find((d) => d.id === id);
    setConfirmState({
      title: "确认删除数据源？",
      description: `将删除「${target?.name || id}」，该操作不可撤销。`,
      confirmText: "确认删除",
      danger: true,
      action: async () => {
        await api(`/api/datasources/${id}`, { method: "DELETE" });
        if (editingId === id) {
          resetAndCloseModal();
        }
        load();
      }
    });
  }

  async function handleConfirm() {
    if (!confirmState) return;
    setConfirmLoading(true);
    try {
      await confirmState.action();
      setConfirmState(null);
    } finally {
      setConfirmLoading(false);
    }
  }

  function beginEdit(d: DataSource) {
    setEditingId(d.id);
    setForm({
      name: d.name,
      source_type: d.source_type,
      description: d.description ?? "",
      host: d.host,
      port: d.port,
      database: d.database,
      username: d.username,
      password: d.password
    });
    setTestResult("");
    setModalStep("form");
    setIsModalOpen(true);
  }

  function openCreateModal() {
    setEditingId(null);
    setForm({ ...emptyForm });
    setTestResult("");
    setModalStep("type");
    setIsModalOpen(true);
  }

  function chooseType(sourceType: "mysql" | "clickhouse") {
    setForm(getDefaultFormByType(sourceType));
    setModalStep("form");
  }

  function resetAndCloseModal() {
    setForm({ ...emptyForm });
    setEditingId(null);
    setTestResult("");
    setModalStep("type");
    setIsModalOpen(false);
  }

  const normalizedKeyword = keyword.trim().toLowerCase();
  const filteredDatasources = datasources
    .filter((d) => {
      if (!normalizedKeyword) return true;
      return [d.name, d.description, d.source_type, d.host, d.database, d.username]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalizedKeyword);
    })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  const start = (page - 1) * pageSize;
  const pagedDatasources = filteredDatasources.slice(start, start + pageSize);

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", href: "/" }, { label: "数据源" }]}
        title="数据源管理"
        subtitle="统一维护连接配置，支持 MySQL 与 ClickHouse。"
        actions={
          <div className="app-toolbar">
            <input
              className="app-input app-toolbar-input"
              placeholder="搜索名称/描述/地址"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button className="app-button app-toolbar-action" onClick={openCreateModal}>
              新增数据源
            </button>
          </div>
        }
      />

      <Toast message={testResult} tone={testResult.startsWith("连接失败") ? "error" : "info"} onClose={() => setTestResult("")} />

      <div className="mt-6 space-y-3">
        {loading && <LoadingSkeletonList count={3} />}
        {pagedDatasources.map((d) => (
          <div key={d.id} className="app-card app-card-interactive app-list-item p-4">
            <div className="app-list-item-main">
              <Link className="app-link break-all font-semibold" href={`/datasources/${d.id}`}>
                {d.name}
              </Link>
              <p className="app-text-muted break-words text-sm">{d.description || "无描述"}</p>
              <p className="app-text-secondary-strong break-all text-sm">
                {d.source_type} | {d.username}@{d.host}:{d.port}/{d.database}
              </p>
            </div>
            <div className="app-list-item-actions">
              <button className="app-button" onClick={() => testSaved(d.id)}>
                测试连接
              </button>
              <button className="app-button-secondary" onClick={() => beginEdit(d)}>
                编辑
              </button>
              <button className="app-button-danger" onClick={() => remove(d.id)}>
                删除
              </button>
            </div>
          </div>
        ))}
        {!filteredDatasources.length && (
          <EmptyState
            title="没有匹配的数据源"
            description="你可以调整搜索关键词，或新增一个 MySQL / ClickHouse 数据源开始分析。"
            actionLabel="新增数据源"
            onAction={openCreateModal}
          />
        )}
        {!!filteredDatasources.length && (
          <ListPagination
            page={page}
            pageSize={pageSize}
            total={filteredDatasources.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#111827]/35 p-4 backdrop-blur-[2px]" role="presentation" onClick={resetAndCloseModal}>
          <div
            className="app-card w-full max-w-2xl max-h-[88vh] overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="datasource-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 id="datasource-modal-title" className="app-section-title">
                {editingId ? "编辑数据源" : "新增数据源"}
              </h2>
              <button className="app-control-button" onClick={resetAndCloseModal}>
                关闭
              </button>
            </div>

            {!editingId && modalStep === "type" ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <button className="app-select-card p-4 text-left" onClick={() => chooseType("mysql")}>
                  <p className="font-semibold">MySQL</p>
                  <p className="app-text-muted mt-1 text-sm">适合 OLTP 业务库（交易、订单、用户）</p>
                </button>
                <button className="app-select-card p-4 text-left" onClick={() => chooseType("clickhouse")}>
                  <p className="font-semibold">ClickHouse</p>
                  <p className="app-text-muted mt-1 text-sm">适合分析型场景（报表、宽表、明细聚合）</p>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="app-form-label">
                  <span>名称（必填，页面显示名）</span>
                  <input
                    className="app-input"
                    placeholder="例如：生产MySQL、本地ClickHouse"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </label>
                <label className="app-form-label">
                  <span>类型</span>
                  <select
                    className="app-input"
                    value={form.source_type}
                    onChange={(e) => setForm({ ...form, source_type: e.target.value })}
                  >
                    <option value="mysql">mysql</option>
                    <option value="clickhouse">clickhouse</option>
                  </select>
                </label>
                <label className="app-form-label sm:col-span-2">
                  <span>备注（选填，用途说明）</span>
                  <input
                    className="app-input"
                    placeholder="例如：用于订单分析；仅测试环境可用"
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                  />
                </label>
                <p className="app-text-muted text-xs sm:col-span-2">名称用于列表展示；备注用于记录数据源用途与环境信息。</p>
                <label className="app-form-label">
                  <span>Host</span>
                  <input className="app-input" placeholder="127.0.0.1" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
                </label>
                <label className="app-form-label">
                  <span>Port</span>
                  <input
                    className="app-input"
                    placeholder="3306"
                    value={form.port}
                    onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
                  />
                </label>
                <label className="app-form-label">
                  <span>Database</span>
                  <input
                    className="app-input"
                    placeholder="ecommerce"
                    value={form.database}
                    onChange={(e) => setForm({ ...form, database: e.target.value })}
                  />
                </label>
                <label className="app-form-label">
                  <span>Username</span>
                  <input
                    className="app-input"
                    placeholder="root"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                  />
                </label>
                <label className="app-form-label sm:col-span-2">
                  <span>Password</span>
                  <input
                    className="app-input"
                    placeholder="输入连接密码"
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                  />
                </label>
                <button className="app-button sm:col-span-2" onClick={testCurrent}>
                  测试当前连接
                </button>
                {!!testResult && (
                  <p className="app-text-secondary-strong break-words text-sm sm:col-span-2" role="status" aria-live="polite">
                    {testResult}
                  </p>
                )}
                <div className="flex flex-col gap-2 sm:col-span-2 sm:flex-row">
                  <button
                    className={`app-button flex-1 ${submitting ? "is-loading" : ""}`}
                    onClick={editingId ? update : create}
                    disabled={submitting}
                  >
                    {submitting ? "提交中..." : editingId ? "更新数据源" : "保存数据源"}
                  </button>
                  <button className="app-button-secondary flex-1" onClick={resetAndCloseModal}>
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || ""}
        description={confirmState?.description}
        confirmText={confirmState?.confirmText}
        danger={!!confirmState?.danger}
        loading={confirmLoading}
        onCancel={() => setConfirmState(null)}
        onConfirm={handleConfirm}
      />
    </main>
  );
}
