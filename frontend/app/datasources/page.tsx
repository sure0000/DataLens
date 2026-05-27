"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties } from "react";
import { Icon } from "../../components/AppIcons";
import { api, ApiError, formatApiError } from "../../lib/api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import ConfirmDialog from "../../components/ConfirmDialog";
import { alertError, alertInfo } from "../../lib/themeClasses";
import EmptyState from "../../components/EmptyState";
import ListPagination from "../../components/ListPagination";
import LoadingSkeletonList from "../../components/LoadingSkeletonList";
import PageHeader from "../../components/PageHeader";

type DataSource = {
  id: number;
  name: string;
  source_type: string;
  description?: string;
  host: string;
  port: number;
  database: string;
  username: string;
  connection_password: string;
};

const emptyForm = {
  name: "本地MySQL",
  source_type: "mysql",
  description: "本地测试库",
  host: "127.0.0.1",
  port: 3306,
  database: "ecommerce",
  username: "root",
  connection_password: ""
};

const TYPE_LABEL: Record<string, string> = {
  mysql: "MySQL",
  mariadb: "MariaDB",
  postgres: "PostgreSQL",
  postgresql: "PostgreSQL",
  greenplum: "Greenplum",
  sqlserver: "SQL Server",
  sqlite: "SQLite",
  clickhouse: "ClickHouse",
  doris: "Apache Doris",
  starrocks: "StarRocks",
  trino: "Trino",
  hive: "Apache Hive"
};

function typeLabel(sourceType: string) {
  return TYPE_LABEL[sourceType] ?? sourceType;
}

const TYPE_PICKER_GROUPS: { title: string; items: { id: string; hint: string }[] }[] = [
  {
    title: "关系型",
    items: [
      { id: "mysql", hint: "OLTP、业务库" },
      { id: "mariadb", hint: "与 MySQL 协议兼容" },
      { id: "postgres", hint: "PostgreSQL / 云 RDS" },
      { id: "greenplum", hint: "MPP，PostgreSQL 协议" },
      { id: "sqlserver", hint: "Microsoft SQL Server" },
      { id: "sqlite", hint: "本地单文件库" }
    ]
  },
  {
    title: "分析 / 大数据",
    items: [
      { id: "clickhouse", hint: "列存 OLAP" },
      { id: "doris", hint: "MySQL 协议，默认 FE 9030" },
      { id: "starrocks", hint: "MySQL 协议，默认 9030" },
      { id: "trino", hint: "联邦查询，库名填 catalog.schema" },
      { id: "hive", hint: "HiveServer2，默认端口 10000" }
    ]
  }
];

function getDefaultFormByType(sourceType: string) {
  const base = { ...emptyForm, source_type: sourceType };
  switch (sourceType) {
    case "clickhouse":
      return { ...base, name: "本地 ClickHouse", port: 9000, database: "default" };
    case "postgres":
    case "postgresql":
      return {
        ...base,
        name: "PostgreSQL",
        source_type: "postgres",
        port: 5432,
        database: "postgres",
        username: "postgres"
      };
    case "greenplum":
      return { ...base, name: "Greenplum", port: 5432, database: "postgres", username: "gpadmin" };
    case "sqlserver":
      return { ...base, name: "SQL Server", port: 1433, database: "master", username: "sa" };
    case "sqlite":
      return {
        ...base,
        name: "SQLite 文件",
        host: ".",
        port: 0,
        database: "/path/to/database.sqlite",
        username: "-",
        connection_password: ""
      };
    case "mariadb":
      return { ...base, name: "MariaDB", port: 3306 };
    case "doris":
      return { ...base, name: "Doris", port: 9030, database: "information_schema", username: "root" };
    case "starrocks":
      return { ...base, name: "StarRocks", port: 9030, database: "information_schema", username: "root" };
    case "trino":
      return {
        ...base,
        name: "Trino",
        port: 8080,
        database: "tpch.tiny",
        username: "trino",
        connection_password: ""
      };
    case "hive":
      return {
        ...base,
        name: "Hive",
        port: 10000,
        database: "default",
        username: "hive",
        connection_password: ""
      };
    default:
      return { ...base, source_type: "mysql", port: 3306 };
  }
}

export default function DataSourcesPage() {
  const [form, setForm] = useState(emptyForm);
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
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
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [showDatasourcePassword, setShowDatasourcePassword] = useState(false);

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await api<{ datasources: DataSource[] }>("/api/datasources");
      setDatasources(res.datasources);
    } catch (e: unknown) {
      setLoadError(
        e instanceof ApiError
          ? formatApiError(e)
          : e instanceof Error
            ? e.message
            : "无法连接后端，请确认服务已启动且 NEXT_PUBLIC_API_URL 指向正确地址。"
      );
      setDatasources([]);
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

  useEscapeKey(resetAndCloseModal, isModalOpen);

  function validateForm(): boolean {
    const errors: Record<string, string> = {};
    if (!form.name.trim()) errors.name = "名称不能为空";
    if (!form.database.trim()) errors.database = "Database 不能为空";
    if (form.source_type === "sqlite") {
      /* Host/Port/用户名对 SQLite 无意义，占位即可 */
    } else {
      if (!form.host.trim()) errors.host = "Host 不能为空";
      if (!form.username.trim()) errors.username = "Username 不能为空";
      if (!form.port || form.port <= 0) errors.port = "Port 必须为正整数";
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function create() {
    if (!validateForm()) return;
    setSubmitting(true);
    try {
      await api("/api/datasources", { method: "POST", body: JSON.stringify(form) });
      resetAndCloseModal();
      load();
    } catch (e: unknown) {
      setTestResult(
        `保存失败：${e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "未知错误"}`
      );
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

  async function beginEdit(d: DataSource) {
    setEditingId(d.id);
    setTestResult("");
    setModalStep("form");
    setIsModalOpen(true);
    // 编辑时默认明文展示密码，避免部分浏览器对受控 password 输入框不渲染已回填值；仍可用眼睛图标隐藏。
    setShowDatasourcePassword(true);
    setForm({
      name: d.name,
      source_type: d.source_type,
      description: d.description ?? "",
      host: d.host,
      port: d.port,
      database: d.database,
      username: d.username,
      connection_password: d.connection_password ?? ""
    });
    // 单独拉取详情，确保密码等字段与库内一致（列表接口若被缓存或字段滞后时仍可回填）
    try {
      const res = await api<{ datasource: DataSource }>(`/api/datasources/${d.id}`);
      const s = res.datasource;
      setForm({
        name: s.name,
        source_type: s.source_type,
        description: s.description ?? "",
        host: s.host,
        port: s.port,
        database: s.database,
        username: s.username,
        connection_password: s.connection_password ?? ""
      });
    } catch {
      /* 保留列表行数据 */
    }
  }

  function openCreateModal() {
    setEditingId(null);
    setForm({ ...emptyForm });
    setShowDatasourcePassword(false);
    setTestResult("");
    setModalStep("type");
    setIsModalOpen(true);
  }

  function chooseType(sourceType: string) {
    setForm(getDefaultFormByType(sourceType));
    setShowDatasourcePassword(false);
    setModalStep("form");
  }

  function resetAndCloseModal() {
    setForm({ ...emptyForm });
    setEditingId(null);
    setShowDatasourcePassword(false);
    setTestResult("");
    setModalStep("type");
    setIsModalOpen(false);
    setFormErrors({});
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
        title="数据源管理"
        subtitle="统一维护连接配置：关系型（MySQL / MariaDB / PostgreSQL / Greenplum / SQL Server / SQLite）与分析型（ClickHouse / Doris / StarRocks / Trino / Hive）。"
        actionsBelowSubtitle
        actions={
          <div className="app-toolbar !flex-nowrap w-full min-w-0 md:w-auto">
            <input
              className="app-input app-toolbar-input min-w-0 w-full max-w-[13.5rem] sm:max-w-[15rem]"
              placeholder="搜索名称/描述/地址"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button type="button" className="app-button app-toolbar-action shrink-0" onClick={openCreateModal}>
              新增数据源
            </button>
          </div>
        }
      />

      {loadError && (
        <div
          className={`app-surface-panel mt-4 flex flex-wrap items-start gap-3 rounded-xl px-4 py-3 text-sm ${alertError}`}
          role="alert"
        >
          <p className="min-w-0 flex-1 break-words">{loadError}</p>
          <button type="button" className="app-button-secondary app-button-xs shrink-0" onClick={() => void load()}>
            重试
          </button>
        </div>
      )}

      {!!testResult && !isModalOpen && (
        <div
          className={`app-surface-panel mt-6 flex max-w-full items-start gap-3 rounded-xl px-4 py-3 text-sm backdrop-blur ${
            testResult.startsWith("连接失败") ? alertError : alertInfo
          }`}
          role="status"
          aria-live="polite"
        >
          <p className="min-w-0 flex-1 break-words">{testResult}</p>
          <button type="button" className="app-control-button shrink-0" onClick={() => setTestResult("")} aria-label="关闭连接测试结果">
            关闭
          </button>
        </div>
      )}

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
            description="你可以调整搜索关键词，或新增一个支持列表中的数据源开始分析。"
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
        <div className="app-modal-backdrop" role="presentation" onClick={resetAndCloseModal}>
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
              <div className="space-y-6">
                {TYPE_PICKER_GROUPS.map((group) => (
                  <div key={group.title}>
                    <p className="app-text-secondary-strong mb-2 text-sm font-semibold">{group.title}</p>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {group.items.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="app-select-card p-3 text-left"
                          onClick={() => chooseType(item.id)}
                        >
                          <p className="font-semibold">{typeLabel(item.id)}</p>
                          <p className="app-text-muted mt-0.5 text-xs">{item.hint}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="app-form-label">
                  <span>名称（必填，页面显示名）</span>
                  <input
                    className={`app-input ${formErrors.name ? "is-error" : ""}`}
                    placeholder="例如：生产MySQL、本地ClickHouse"
                    value={form.name}
                    aria-describedby={formErrors.name ? "err-name" : undefined}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                  {formErrors.name && <span id="err-name" className="app-field-error">{formErrors.name}</span>}
                </label>
                {!editingId && (
                  <div className="app-form-label">
                    <span>类型</span>
                    <div className="flex items-center gap-2 rounded-lg border border-app-border bg-app-hover px-3 py-2 text-sm text-app-ink">
                      {typeLabel(form.source_type)}
                      <span className="app-text-muted text-xs">（已在上一步选择）</span>
                    </div>
                  </div>
                )}
                {!!editingId && (
                  <label className="app-form-label">
                    <span>类型</span>
                    <select
                      className="app-input"
                      value={form.source_type}
                      onChange={(e) => setForm({ ...form, source_type: e.target.value })}
                    >
                      <optgroup label="关系型">
                        <option value="mysql">MySQL</option>
                        <option value="mariadb">MariaDB</option>
                        <option value="postgres">PostgreSQL</option>
                        <option value="greenplum">Greenplum</option>
                        <option value="sqlserver">SQL Server</option>
                        <option value="sqlite">SQLite</option>
                      </optgroup>
                      <optgroup label="分析 / 大数据">
                        <option value="clickhouse">ClickHouse</option>
                        <option value="doris">Apache Doris</option>
                        <option value="starrocks">StarRocks</option>
                        <option value="trino">Trino</option>
                        <option value="hive">Apache Hive</option>
                      </optgroup>
                    </select>
                  </label>
                )}
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
                  <input
                    className={`app-input ${formErrors.host ? "is-error" : ""}`}
                    placeholder="127.0.0.1"
                    value={form.host}
                    aria-describedby={formErrors.host ? "err-host" : undefined}
                    onChange={(e) => setForm({ ...form, host: e.target.value })}
                  />
                  {formErrors.host && <span id="err-host" className="app-field-error">{formErrors.host}</span>}
                </label>
                <label className="app-form-label">
                  <span>Port</span>
                  <input
                    className={`app-input ${formErrors.port ? "is-error" : ""}`}
                    placeholder="3306"
                    value={form.port}
                    aria-describedby={formErrors.port ? "err-port" : undefined}
                    onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
                  />
                  {formErrors.port && <span id="err-port" className="app-field-error">{formErrors.port}</span>}
                </label>
                <label className="app-form-label">
                  <span>Database</span>
                  <input
                    className={`app-input ${formErrors.database ? "is-error" : ""}`}
                    placeholder="ecommerce"
                    value={form.database}
                    aria-describedby={formErrors.database ? "err-database" : undefined}
                    onChange={(e) => setForm({ ...form, database: e.target.value })}
                  />
                  {formErrors.database && <span id="err-database" className="app-field-error">{formErrors.database}</span>}
                  {form.source_type === "sqlite" && (
                    <span className="app-text-muted text-xs">SQLite：填写 .db 文件路径；Host/Port 可忽略。</span>
                  )}
                  {form.source_type === "trino" && (
                    <span className="app-text-muted text-xs">Trino：填写 catalog.schema（如 tpch.tiny）；仅填 catalog 时将在目录中列出其下 schema。</span>
                  )}
                  {(form.source_type === "postgres" || form.source_type === "postgresql" || form.source_type === "greenplum") && (
                    <span className="app-text-muted text-xs">PostgreSQL / Greenplum：此处为库名（dbname）；数据源目录中的「数据库」对应 schema。</span>
                  )}
                  {form.source_type === "hive" && (
                    <span className="app-text-muted text-xs">Hive：Database 为 Hive 库名（与 SHOW DATABASES 一致）；目录中「数据库」即各 Hive database。</span>
                  )}
                </label>
                <label className="app-form-label">
                  <span>Username</span>
                  <input
                    className={`app-input ${formErrors.username ? "is-error" : ""}`}
                    placeholder="root"
                    value={form.username}
                    aria-describedby={formErrors.username ? "err-username" : undefined}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                  />
                  {formErrors.username && <span id="err-username" className="app-field-error">{formErrors.username}</span>}
                </label>
                <label className="app-form-label sm:col-span-2">
                  <span>Password</span>
                  <div className="relative">
                    {/* 不用 type=password：Chrome 等对脚本回填的受控密码框常表现为完全空白（无圆点无明文）。改用 text + WebKit 圆点遮罩。 */}
                    <input
                      key={editingId ? `ds-pw-edit-${editingId}` : "ds-pw-create"}
                      className="app-input w-full pr-11 text-sm text-app-primary"
                      placeholder="输入连接密码"
                      type="text"
                      spellCheck={false}
                      name="datalens-datasource-password"
                      autoComplete="off"
                      value={String(form.connection_password ?? "")}
                      onChange={(e) => setForm({ ...form, connection_password: e.target.value })}
                      style={
                        {
                          WebkitTextSecurity:
                            !showDatasourcePassword && String(form.connection_password ?? "").length > 0 ? "disc" : "none"
                        } as CSSProperties
                      }
                    />
                    <button
                      type="button"
                      className="app-control-button absolute right-1.5 top-1/2 h-9 w-9 min-h-0 shrink-0 -translate-y-1/2 rounded-lg border border-transparent p-0 text-app-muted hover:text-app-secondary"
                      aria-label={showDatasourcePassword ? "以圆点隐藏" : "显示为明文"}
                      aria-pressed={showDatasourcePassword}
                      onClick={() => setShowDatasourcePassword((v) => !v)}
                    >
                      {showDatasourcePassword ? <Icon name="eyeOff" className="size-4" aria-hidden /> : <Icon name="eye" className="size-4" aria-hidden />}
                    </button>
                  </div>
                  {editingId ? (
                    <span className="app-text-muted text-xs">
                      编辑时默认明文；点击眼睛可切换为圆点隐藏（Chrome/Safari）。若仍为空，表示库中未保存密码或曾被空保存覆盖；填写新密码并更新即可（留空更新不会清空已存密码）。
                    </span>
                  ) : (
                    <span className="app-text-muted text-xs">
                      新增时可留空；点击眼睛可在「圆点 / 明文」间切换（非 type=password，避免浏览器不显示已填值）。
                    </span>
                  )}
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
