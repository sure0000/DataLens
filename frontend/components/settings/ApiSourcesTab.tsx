"use client";

import { useEffect, useState } from "react";
import ConfirmDialog from "../ConfirmDialog";
import Toast from "../Toast";
import { api } from "../../lib/api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { useToast } from "../../hooks/useToast";

type ApiSource = {
  id: number;
  knowledge_base_id: number | null;
  name: string;
  integration: string;
  object_id: string;
  extra: Record<string, string>;
  has_key: boolean;
  enabled: boolean;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

function integrationLabel(s: ApiSource): string {
  const map: Record<string, string> = { notion: "Notion", confluence: "Confluence", feishu: "飞书" };
  return map[s.integration] ?? s.integration;
}

export default function ApiSourcesTab() {
  const { toast, notify, dismiss } = useToast();
  const [apiSources, setApiSources] = useState<ApiSource[]>([]);
  const [apiSourcesLoading, setApiSourcesLoading] = useState(false);
  const [apiModalOpen, setApiModalOpen] = useState(false);
  const [apiEditingId, setApiEditingId] = useState<number | null>(null);
  const [apiSaving, setApiSaving] = useState(false);
  const [apiName, setApiName] = useState("");
  const [apiIntegration, setApiIntegration] = useState<"notion" | "confluence" | "feishu">("notion");
  const [apiKey, setApiKey] = useState("");
  const [apiExtraEmail, setApiExtraEmail] = useState("");
  const [apiExtraDomain, setApiExtraDomain] = useState("");
  const [apiExtraAppId, setApiExtraAppId] = useState("");
  const [apiShowKey, setApiShowKey] = useState(false);
  const [apiEnabled, setApiEnabled] = useState(true);
  const [apiDeleteId, setApiDeleteId] = useState<number | null>(null);
  const [apiDeleting, setApiDeleting] = useState(false);
  const [apiKeyLoading, setApiKeyLoading] = useState(false);

  useEscapeKey(() => setApiModalOpen(false), apiModalOpen);

  async function loadApiSources() {
    setApiSourcesLoading(true);
    try {
      const res = await api<{ api_sources: ApiSource[] }>("/api/api-sources");
      setApiSources(res.api_sources ?? []);
    } catch {
      // 静默失败，切换 tab 时会自动重试
    } finally {
      setApiSourcesLoading(false);
    }
  }

  useEffect(() => { loadApiSources(); }, []);

  function openApiCreateModal() {
    setApiEditingId(null);
    setApiName("");
    setApiIntegration("notion");
    setApiKey("");
    setApiExtraEmail("");
    setApiExtraDomain("");
    setApiExtraAppId("");
    setApiShowKey(false);
    setApiEnabled(true);
    setApiModalOpen(true);
  }

  async function openApiEditModal(s: ApiSource) {
    setApiEditingId(s.id);
    setApiName(s.name);
    setApiIntegration(s.integration as "notion" | "confluence" | "feishu");
    setApiKey("");
    setApiShowKey(false);
    setApiKeyLoading(true);
    const extra = s.extra || {};
    setApiExtraEmail((extra as Record<string, string>).email ?? "");
    setApiExtraDomain((extra as Record<string, string>).domain ?? "");
    setApiExtraAppId((extra as Record<string, string>).app_id ?? "");
    setApiEnabled(s.enabled);
    setApiModalOpen(true);
    try {
      const res = await api<{ api_source: ApiSource & { api_key?: string } }>(`/api/api-sources/${s.id}?reveal_secret=true`);
      setApiKey(res.api_source.api_key || "");
    } catch {
      // key fetch failed
    } finally {
      setApiKeyLoading(false);
    }
  }

  async function saveApiSource() {
    if (!apiName.trim()) { notify("请填写名称", "error"); return; }
    if (!apiEditingId && !apiKey.trim()) { notify("新建 API 源时必须填写 API Key / Token", "error"); return; }
    if (apiIntegration === "confluence" && (!apiExtraEmail.trim() || !apiExtraDomain.trim())) {
      notify("Confluence 需要填写邮箱与域名", "error"); return;
    }
    if (apiIntegration === "feishu" && !apiExtraAppId.trim()) {
      notify("飞书需要填写 App ID", "error"); return;
    }
    setApiSaving(true);
    try {
      const extra: Record<string, string> = {};
      if (apiIntegration === "confluence") { extra.email = apiExtraEmail.trim(); extra.domain = apiExtraDomain.trim(); }
      if (apiIntegration === "feishu") { extra.app_id = apiExtraAppId.trim(); }
      const body: Record<string, unknown> = { name: apiName.trim(), integration: apiIntegration, extra, enabled: apiEnabled };
      if (apiEditingId) {
        if (apiKey.trim()) body.api_key = apiKey.trim();
        await api(`/api/api-sources/${apiEditingId}`, { method: "PUT", body: JSON.stringify(body) });
        notify("API 源已更新", "success");
      } else {
        body.api_key = apiKey.trim();
        await api("/api/api-sources", { method: "POST", body: JSON.stringify(body) });
        notify("API 源已添加", "success");
      }
      setApiModalOpen(false);
      await loadApiSources();
    } catch {
      notify("保存失败", "error");
    } finally {
      setApiSaving(false);
    }
  }

  async function toggleApiKeyVisibility() {
    if (apiShowKey) { setApiShowKey(false); return; }
    if (apiKey.trim()) { setApiShowKey(true); return; }
    if (!apiEditingId) { setApiShowKey(true); return; }
    setApiKeyLoading(true);
    try {
      const res = await api<{ api_source: ApiSource & { api_key?: string } }>(`/api/api-sources/${apiEditingId}?reveal_secret=true`);
      setApiKey(res.api_source.api_key || "");
      setApiShowKey(true);
    } catch {
      notify("无法获取密钥", "error");
    } finally {
      setApiKeyLoading(false);
    }
  }

  async function confirmDeleteApiSource() {
    const id = apiDeleteId;
    if (!id) return;
    setApiDeleting(true);
    try {
      await api(`/api/api-sources/${id}`, { method: "DELETE" });
      setApiDeleteId(null);
      notify("API 源已删除", "success");
      await loadApiSources();
    } catch {
      notify("删除失败", "error");
    } finally {
      setApiDeleting(false);
    }
  }

  return (
    <>
      <Toast message={toast.message} tone={toast.tone} duration={toast.tone === "error" ? 8000 : toast.durationMs} onClose={dismiss} />

      <section className="app-card rounded-2xl p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
            </span>
            <div>
              <h2 className="app-card-title text-base">API 源</h2>
              <p className="mt-1 text-[11px] text-app-muted">全局 API 源，可在各个知识库中复用导入。配置与导入分离，支持重复使用。</p>
            </div>
          </div>
          <button type="button" className="app-button shrink-0" onClick={openApiCreateModal}>
            新增 API 源
          </button>
        </div>

        {apiSourcesLoading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
            加载中
          </div>
        ) : apiSources.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-app-border bg-app-hover/30 px-4 py-8 text-center text-sm text-app-muted">
            暂无 API 源，请点击右上角「新增 API 源」。
          </div>
        ) : (
          <ul className="mt-5 divide-y divide-[var(--app-card-border)] overflow-hidden rounded-xl border border-[var(--app-card-border)] bg-[var(--app-card-bg)]">
            {apiSources.map((s) => (
              <li key={s.id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-4">
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="truncate text-sm font-semibold text-app-ink">{s.name}</p>
                  <p className="text-[11px] text-app-secondary">
                    <span className="text-app-muted">集成</span> {integrationLabel(s)}
                    <span className="mx-1.5 text-app-border">·</span>
                    <span className="text-app-muted">密钥</span>{" "}
                    {s.has_key ? <span className="app-text-success font-medium">已配置</span> : <span className="app-text-danger">未配置</span>}
                  </p>
                  <p className="text-[10px] text-app-muted">
                    上次导入：{s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : "—"}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button type="button" className="app-button-secondary app-button-xs" onClick={() => openApiEditModal(s)}>
                    编辑
                  </button>
                  <button
                    type="button"
                    className="app-button-danger app-button-xs"
                    onClick={() => setApiDeleteId(s.id)}
                  >
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {apiModalOpen && typeof document !== "undefined" && (
        <div className="app-modal-backdrop app-modal-backdrop--front" role="presentation" onClick={() => !apiSaving && setApiModalOpen(false)}>
          <div
            className="app-modal-surface app-chatgpt-dialog mx-4 max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl p-5 sm:p-6"
            role="dialog"
            aria-modal="true"
            aria-labelledby="api-source-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="api-source-modal-title" className="text-base font-semibold text-app-ink">
              {apiEditingId ? "编辑 API 源" : "新增 API 源"}
            </h3>
            <div className="mt-4 space-y-3">
              <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                显示名称
                <input className="app-input rounded-xl px-3 py-2 text-sm" value={apiName} onChange={(e) => setApiName(e.target.value)} disabled={apiSaving} />
              </label>
              <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                平台
                <select
                  className="app-input rounded-xl px-3 py-2 text-sm"
                  value={apiIntegration}
                  onChange={(e) => setApiIntegration(e.target.value as "notion" | "confluence" | "feishu")}
                  disabled={apiSaving || !!apiEditingId}
                >
                  <option value="notion">Notion</option>
                  <option value="confluence">Confluence</option>
                  <option value="feishu">飞书</option>
                </select>
                {!!apiEditingId && <p className="text-[11px] text-app-muted">编辑时不可切换平台类型</p>}
              </label>
              {apiEditingId && <p className="text-[11px] text-app-muted">密钥留空则不修改；当前已配置密钥将保留。</p>}
              {apiIntegration === "notion" && (
                <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                  Integration Token
                  <div className="app-field">
                    <input
                      className="app-input app-input--adorn-end rounded-xl px-3 py-2 text-sm font-mono"
                      type={apiShowKey ? "text" : "password"}
                      autoComplete="off"
                      placeholder="secret_…"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      disabled={apiSaving}
                    />
                    <button
                      type="button"
                      className="app-field__action text-app-muted hover:text-app-ink"
                      tabIndex={-1}
                      onClick={() => void toggleApiKeyVisibility()}
                      disabled={apiKeyLoading}
                      aria-label={apiShowKey ? "隐藏" : "显示"}
                      aria-pressed={apiShowKey}
                    >
                      {apiKeyLoading ? (
                        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                      ) : apiShowKey ? (
                        <IconEyeOff className="h-4 w-4" />
                      ) : (
                        <IconEye className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </label>
              )}
              {apiIntegration === "confluence" && (
                <>
                  <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                    API Token
                    <div className="app-field">
                      <input
                        className="app-input app-input--adorn-end rounded-xl px-3 py-2 text-sm font-mono"
                        type={apiShowKey ? "text" : "password"}
                        autoComplete="off"
                        placeholder="Confluence API Token"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        disabled={apiSaving}
                      />
                      <button
                        type="button"
                        className="app-field__action text-app-muted hover:text-app-ink"
                        tabIndex={-1}
                        onClick={() => void toggleApiKeyVisibility()}
                        disabled={apiKeyLoading}
                        aria-label={apiShowKey ? "隐藏" : "显示"}
                        aria-pressed={apiShowKey}
                      >
                        {apiKeyLoading ? (
                          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                        ) : apiShowKey ? (
                          <IconEyeOff className="h-4 w-4" />
                        ) : (
                          <IconEye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </label>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                      邮箱
                      <input className="app-input rounded-xl px-3 py-2 text-sm font-mono" placeholder="Confluence 账号邮箱" value={apiExtraEmail} onChange={(e) => setApiExtraEmail(e.target.value)} disabled={apiSaving} />
                    </label>
                    <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                      域名
                      <input className="app-input rounded-xl px-3 py-2 text-sm font-mono" placeholder="example.atlassian.net" value={apiExtraDomain} onChange={(e) => setApiExtraDomain(e.target.value)} disabled={apiSaving} />
                    </label>
                  </div>
                </>
              )}
              {apiIntegration === "feishu" && (
                <>
                  <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                    App Secret
                    <div className="app-field">
                      <input
                        className="app-input app-input--adorn-end rounded-xl px-3 py-2 text-sm font-mono"
                        type={apiShowKey ? "text" : "password"}
                        autoComplete="off"
                        placeholder="飞书应用 Secret"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        disabled={apiSaving}
                      />
                      <button
                        type="button"
                        className="app-field__action text-app-muted hover:text-app-ink"
                        tabIndex={-1}
                        onClick={() => void toggleApiKeyVisibility()}
                        disabled={apiKeyLoading}
                        aria-label={apiShowKey ? "隐藏" : "显示"}
                        aria-pressed={apiShowKey}
                      >
                        {apiKeyLoading ? (
                          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                        ) : apiShowKey ? (
                          <IconEyeOff className="h-4 w-4" />
                        ) : (
                          <IconEye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </label>
                  <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                    App ID
                    <input className="app-input rounded-xl px-3 py-2 text-sm font-mono" placeholder="飞书应用 App ID" value={apiExtraAppId} onChange={(e) => setApiExtraAppId(e.target.value)} disabled={apiSaving} />
                  </label>
                </>
              )}
              <label className="flex cursor-pointer items-center gap-2 text-sm text-app-secondary">
                <input type="checkbox" checked={apiEnabled} onChange={(e) => setApiEnabled(e.target.checked)} disabled={apiSaving} />
                启用（禁用后无法从知识库手动导入）
              </label>
            </div>
            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button type="button" className="app-dialog-btn app-dialog-btn-secondary w-full sm:w-auto" onClick={() => setApiModalOpen(false)} disabled={apiSaving}>
                取消
              </button>
              <button type="button" className="app-dialog-btn app-dialog-btn-primary w-full sm:w-auto" disabled={apiSaving} onClick={() => void saveApiSource()}>
                {apiSaving ? "保存中…" : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={apiDeleteId !== null}
        title="删除该 API 源？"
        description="将从全局列表中删除此 API 源，后续无法从知识库引用该源进行导入。"
        confirmText="删除"
        cancelText="取消"
        danger
        loading={apiDeleting}
        onCancel={() => setApiDeleteId(null)}
        onConfirm={() => void confirmDeleteApiSource()}
      />
    </>
  );
}

function IconEye({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function IconEyeOff({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}
