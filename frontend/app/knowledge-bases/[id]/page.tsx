"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ConfirmDialog from "../../../components/ConfirmDialog";
import PageHeader from "../../../components/PageHeader";
import Toast from "../../../components/Toast";
import { api, ApiError, formatApiError } from "../../../lib/api";

import type {
  ApiSource,
  DocRow,
  Entry,
  GitSource,
  KB,
} from "../../../components/knowledge-bases/types";

import EditKbModal from "../../../components/knowledge-bases/EditKbModal";
import GitSourceForm, {
  defaultGitFormData,
  type GitSourceFormData,
} from "../../../components/knowledge-bases/GitSourceForm";
import ImportPickerModal from "../../../components/knowledge-bases/ImportPickerModal";
import type { SourceItem } from "../../../components/knowledge-bases/SourceCard";
import SourceCardGrid from "../../../components/knowledge-bases/SourceCardGrid";

type GitHubDiagProbe = {
  reachable?: boolean;
  http_status?: number;
  error?: string;
  body_preview?: string;
  hint?: string;
  url?: string;
};
type GitHubDiagResponse = {
  summary: string;
  api_github_com: GitHubDiagProbe;
  github_com: GitHubDiagProbe;
};

export default function KnowledgeBaseDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const kbId = Number(params.id);

  // ── Core data ──
  const [kb, setKb] = useState<KB | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [gitSources, setGitSources] = useState<GitSource[]>([]);
  const [apiSources, setApiSources] = useState<ApiSource[]>([]);
  const [documents, setDocuments] = useState<DocRow[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [loading, setLoading] = useState(false);

  // ── Toast ──
  const [message, setMessageText] = useState("");
  const [messageTone, setMessageTone] = useState<"success" | "error" | "info">("success");
  const [toastDurationMs, setToastDurationMs] = useState(4000);

  type NotifyOpts = { persist?: boolean };
  const notifyUser = useCallback(
    (msg: string, tone: "success" | "error" | "info" = "success", opts?: NotifyOpts) => {
      setMessageText(msg);
      if (!msg) { setMessageTone("success"); setToastDurationMs(4000); return; }
      setMessageTone(tone);
      setToastDurationMs(opts?.persist ? 0 : tone === "info" ? 14000 : tone === "error" ? 9000 : 4000);
    },
    [],
  );
  const dismissToast = useCallback(() => {
    setMessageText(""); setMessageTone("success"); setToastDurationMs(4000);
  }, []);

  // ── Modals ──
  const [importPickerOpen, setImportPickerOpen] = useState(false);
  const [editKbOpen, setEditKbOpen] = useState(false);

  // ── Git edit modal ──
  const [gitEditOpen, setGitEditOpen] = useState(false);
  const [editingGitId, setEditingGitId] = useState<number | null>(null);
  const [gitFormData, setGitFormData] = useState<GitSourceFormData>(defaultGitFormData());
  const [gitSaving, setGitSaving] = useState(false);

  // ── Git sync ──
  const [gitSyncingId, setGitSyncingId] = useState<number | null>(null);
  const gitSyncLockRef = useRef(false);

  // ── Confirm dialog ──
  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    confirmName?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  // ── Settings menu ──
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const settingsMenuRef = useRef<HTMLDivElement>(null);

  // ── Tag loading ──
  const [tagLoading, setTagLoading] = useState(false);

  // ═══════════════════════════════════════════════════
  // Data fetching
  // ═══════════════════════════════════════════════════

  async function loadDocuments() {
    setDocsLoading(true);
    try {
      const res = await api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`);
      setDocuments(res.documents ?? []);
    } catch { setDocuments([]); } finally { setDocsLoading(false); }
  }

  async function loadAll() {
    if (!Number.isFinite(kbId)) return;
    setLoading(true);
    try {
      const [res, gitRes, apiRes] = await Promise.all([
        api<{ knowledge_base: KB; entries: Entry[] }>(`/api/knowledge-bases/${kbId}`),
        api<{ git_sources: GitSource[] }>(`/api/knowledge-bases/${kbId}/git-sources`).catch(() => ({ git_sources: [] })),
        api<{ api_sources: ApiSource[] }>(`/api/api-sources`).catch(() => ({ api_sources: [] })),
      ]);
      setKb(res.knowledge_base);
      setEntries(res.entries);
      setGitSources(gitRes.git_sources ?? []);
      setApiSources(apiRes.api_sources ?? []);
      loadDocuments();
    } catch {
      setKb(null); setEntries([]); setGitSources([]); setApiSources([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, [kbId]);

  // Close settings menu on outside click
  useEffect(() => {
    if (!settingsMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (settingsMenuRef.current && !settingsMenuRef.current.contains(e.target as Node)) {
        setSettingsMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [settingsMenuOpen]);

  // ── Document retry ──

  async function retryDocument(docId: number) {
    try {
      await api(`/api/knowledge-bases/${kbId}/documents/${docId}/retry`, { method: "POST" });
      notifyUser("已重新提交处理", "success");
      loadDocuments();
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "重试失败", "error");
    }
  }

  // ═══════════════════════════════════════════════════
  // Confirm actions
  // ═══════════════════════════════════════════════════

  function confirmDeleteKb() {
    if (!kb) return;
    setConfirmState({
      title: "确认删除整个知识库？",
      description: `此操作不可恢复。请输入知识库名称「${kb.name}」以确认删除。`,
      confirmText: "删除",
      confirmName: kb.name,
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}`, { method: "DELETE" });
        router.push("/knowledge-bases");
      },
    });
  }

  async function handleConfirm() {
    if (!confirmState) return;
    setConfirmLoading(true);
    try { await confirmState.action(); setConfirmState(null); }
    finally { setConfirmLoading(false); }
  }

  // ═══════════════════════════════════════════════════
  // Git actions
  // ═══════════════════════════════════════════════════

  async function syncGitSourceNow(id: number) {
    if (gitSyncLockRef.current) return;
    gitSyncLockRef.current = true;
    setGitSyncingId(id);
    notifyUser("正在从 GitHub/GitLab 拉取文件并写入向量索引，可能需要几十秒至数分钟，请稍候…", "info");
    try {
      const res = await api<{ ok?: boolean; files?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/git-sources/${id}/sync`,
        { method: "POST" },
      );
      notifyUser(res.message || `已同步 ${res.files ?? 0} 个文件`, "success", { persist: true });
      await loadAll();
    } catch (e: unknown) {
      let detail = e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "同步失败";
      detail = (detail || "").trim() || "同步失败（未收到具体错误信息，请打开浏览器开发者工具 → Network 查看该请求响应）";
      notifyUser(detail, "error", { persist: true });
      await loadAll();
    } finally { setGitSyncingId(null); gitSyncLockRef.current = false; }
  }

  // ═══════════════════════════════════════════════════
  // Git edit modal helpers
  // ═══════════════════════════════════════════════════

  function openGitEdit(s: GitSource) {
    setEditingGitId(s.id);
    setGitFormData({
      name: s.name,
      provider: s.provider === "gitlab" ? "gitlab" : "github",
      apiBase: s.api_base ?? "",
      owner: s.owner,
      repo: s.repo,
      branch: s.branch ?? "",
      pathPrefix: s.path_prefix ?? "",
      token: s.token ?? "",
      includeGlobs: s.include_globs,
      maxFileKb: s.max_file_kb,
      maxFiles: s.max_files,
      cron: s.cron_expression ?? "",
      enabled: s.enabled,
    });
    setGitEditOpen(true);
  }

  async function saveGitEdit() {
    if (!gitFormData.name.trim() || !gitFormData.owner.trim() || !gitFormData.repo.trim()) {
      notifyUser("请填写显示名称、owner 与仓库名");
      return;
    }
    setGitSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: gitFormData.name.trim(),
        provider: gitFormData.provider,
        api_base: gitFormData.apiBase.trim() || null,
        owner: gitFormData.owner.trim(),
        repo: gitFormData.repo.trim(),
        branch: gitFormData.branch.trim(),
        path_prefix: gitFormData.pathPrefix.trim(),
        include_globs: gitFormData.includeGlobs.trim(),
        max_file_kb: gitFormData.maxFileKb,
        max_files: gitFormData.maxFiles,
        cron_expression: gitFormData.cron.trim() || null,
        enabled: gitFormData.enabled,
      };
      if (gitFormData.token.trim()) body.token = gitFormData.token.trim();
      await api(`/api/knowledge-bases/${kbId}/git-sources/${editingGitId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      notifyUser("代码源已更新");
      setGitEditOpen(false);
      loadAll();
    } catch (e: unknown) {
      notifyUser(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "保存失败", "error");
    } finally { setGitSaving(false); }
  }

  // ═══════════════════════════════════════════════════
  // KB edit
  // ═══════════════════════════════════════════════════

  async function handleSaveKb(name: string, description: string) {
    await api(`/api/knowledge-bases/${kbId}`, {
      method: "PUT",
      body: JSON.stringify({ name, description }),
    });
    notifyUser("知识库信息已更新");
    setEditKbOpen(false);
    loadAll();
  }

  // ── Tag mutations ──

  async function handleAddTag(source: SourceItem, tag: string) {
    const currentTags = getSourceTags(source);
    if (currentTags.includes(tag)) return;
    const newTags = [...currentTags, tag];
    await updateSourceTags(source, newTags);
  }

  async function handleRemoveTag(source: SourceItem, tag: string) {
    const currentTags = getSourceTags(source);
    const newTags = currentTags.filter((t) => t !== tag);
    await updateSourceTags(source, newTags);
  }

  function getSourceTags(source: SourceItem): string[] {
    if (source.kind === "git") return source.data.tags ?? [];
    if (source.kind === "api") return source.data.tags ?? [];
    return source.entry.tags ?? [];
  }

  async function updateSourceTags(source: SourceItem, tags: string[]) {
    setTagLoading(true);
    try {
      if (source.kind === "git") {
        await api(`/api/knowledge-bases/${kbId}/git-sources/${source.data.id}`, {
          method: "PUT",
          body: JSON.stringify({ tags }),
        });
      } else if (source.kind === "api") {
        await api(`/api/knowledge-bases/${kbId}/api-sources/${source.data.id}`, {
          method: "PUT",
          body: JSON.stringify({ tags }),
        });
      } else {
        await api(`/api/knowledge-bases/${kbId}/entries/${source.entry.id}`, {
          method: "PUT",
          body: JSON.stringify({ tags }),
        });
      }
      loadAll();
    } catch (e: unknown) {
      notifyUser(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "标签更新失败", "error");
    } finally { setTagLoading(false); }
  }

  // ═══════════════════════════════════════════════════
  // Render guards
  // ═══════════════════════════════════════════════════

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  if (!loading && !kb) {
    return (
      <main className="app-page">
        <p className="text-app-secondary">知识库不存在或已删除。</p>
        <Link className="app-link mt-2 inline-block" href="/knowledge-bases">返回列表</Link>
      </main>
    );
  }

  // ═══════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", href: "/" },
          { label: "语义知识库", href: "/knowledge-bases" },
          { label: kb?.name || "…" },
        ]}
        title={kb?.name || "语义知识库"}
        subtitle={kb?.description || "文档经过清洗、分块、向量化后进入语义索引，支持混合检索（向量 + 关键词）。"}
        actions={
          <div className="app-toolbar flex-wrap">
            <div className="relative" ref={settingsMenuRef}>
              <button
                className="app-button-secondary app-toolbar-action"
                type="button"
                onClick={() => setSettingsMenuOpen((v) => !v)}
              >
                设置
              </button>
              {settingsMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-50 min-w-[120px] rounded-lg border border-[var(--app-border)] bg-[var(--app-surface)] py-1 shadow-lg">
                  <button
                    className="block w-full px-4 py-2 text-left text-sm text-[var(--app-text-primary)] hover:bg-[var(--app-bg-hover)]"
                    type="button"
                    onClick={() => { setSettingsMenuOpen(false); setEditKbOpen(true); }}
                  >
                    编辑
                  </button>
                  <button
                    className="block w-full px-4 py-2 text-left text-sm text-[var(--app-text-danger)] hover:bg-[var(--app-bg-hover)]"
                    type="button"
                    onClick={() => { setSettingsMenuOpen(false); confirmDeleteKb(); }}
                  >
                    删除知识库
                  </button>
                </div>
              )}
            </div>
            <button className="app-button app-toolbar-action" type="button" onClick={() => setImportPickerOpen(true)}>
              导入
            </button>
          </div>
        }
      />

      <Toast message={message} tone={messageTone} duration={toastDurationMs} onClose={dismissToast} />

      {loading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {!loading && kb && (
        <>
          <div className="mt-6">
            <SourceCardGrid
              gitSources={gitSources}
              entries={entries}
              documents={documents}
              kbId={kbId}
              gitSyncingId={gitSyncingId}
              onSyncGit={syncGitSourceNow}
              onRetryDoc={retryDocument}
              onRefresh={loadAll}
              onAddTag={handleAddTag}
              onRemoveTag={handleRemoveTag}
              tagLoading={tagLoading}
            />
          </div>

          {docsLoading && <p className="text-sm text-app-muted mt-3">加载文档状态…</p>}

          {/* ── Modals ── */}
          <ImportPickerModal
            open={importPickerOpen}
            kbId={kbId}
            apiSources={apiSources}
            onClose={() => setImportPickerOpen(false)}
            onSuccess={loadAll}
            notifyUser={notifyUser}
          />

          <EditKbModal
            open={editKbOpen}
            kbName={kb.name}
            kbDescription={kb.description || ""}
            onSave={handleSaveKb}
            onClose={() => setEditKbOpen(false)}
          />

          {/* Git edit modal */}
          {gitEditOpen && (
            <div className="app-modal-backdrop" role="presentation" onClick={() => !gitSaving && setGitEditOpen(false)}>
              <div
                className="app-card max-h-[90vh] w-full max-w-lg overflow-auto p-5"
                role="dialog"
                aria-modal="true"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="app-section-title">编辑代码源</h2>
                  <button className="app-control-button" type="button" disabled={gitSaving} onClick={() => setGitEditOpen(false)}>
                    关闭
                  </button>
                </div>
                <GitSourceForm
                  data={gitFormData}
                  onChange={(patch) => setGitFormData((prev) => ({ ...prev, ...patch }))}
                  disabled={gitSaving}
                  isEditing
                />
                <div className="mt-4 flex gap-2">
                  <button
                    className={`app-button flex-1 ${gitSaving ? "is-loading" : ""}`}
                    type="button"
                    disabled={gitSaving}
                    onClick={() => void saveGitEdit()}
                  >
                    {gitSaving ? "保存中…" : "保存"}
                  </button>
                  <button className="app-button-secondary flex-1" type="button" disabled={gitSaving} onClick={() => setGitEditOpen(false)}>
                    取消
                  </button>
                </div>
              </div>
            </div>
          )}

          <ConfirmDialog
            open={!!confirmState}
            title={confirmState?.title || ""}
            description={confirmState?.description}
            confirmText={confirmState?.confirmText}
            confirmName={confirmState?.confirmName}
            danger={!!confirmState?.danger}
            loading={confirmLoading}
            onCancel={() => setConfirmState(null)}
            onConfirm={handleConfirm}
          />
        </>
      )}
    </main>
  );
}
