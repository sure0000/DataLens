"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConfirmDialog from "../../../components/ConfirmDialog";
import EmptyState from "../../../components/EmptyState";
import GitFileBrowser from "../../../components/GitFileBrowser";
import PageHeader from "../../../components/PageHeader";
import Toast from "../../../components/Toast";
import { api, apiForm, ApiError, formatApiError } from "../../../lib/api";

type KB = { id: number; name: string; description: string; created_at: string };
type Entry = {
  id: number;
  knowledge_base_id: number;
  title: string;
  summary?: string;
  body: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
  source_url?: string | null;
  source_meta?: Record<string, string>;
};

type Hit = { entry_id: number; title: string; summary?: string; snippet: string; score_hint: string };

/** 历史条目可能带旧 kind，用于徽标展示 */
const LEGACY_LINK_KIND_LABEL: Record<string, string> = {
  web: "网页链接",
  notion: "Notion（链接）",
  confluence: "Confluence（链接）",
  obsidian: "Obsidian（链接）",
  notion_api: "Notion（官方 API）",
  confluence_api: "Confluence（官方 API）",
  feishu_api: "飞书（官方 API）",
  obsidian_publish: "Obsidian Publish",
  git_file: "代码仓库",
};

function sourceBadgeText(meta?: Record<string, string> | Record<string, unknown>): string | null {
  if (!meta || typeof meta !== "object") return null;
  const kind = meta.kind != null ? String(meta.kind) : "";
  if (!kind) return null;
  if (typeof meta.label === "string" && meta.label.trim()) return meta.label.trim();
  const ref = meta.ref != null ? String(meta.ref) : "";
  if (kind === "manual") return "手动编写";
  if (kind === "file") return `文件：${ref || "上传"}`;
  if (kind === "git_file") return ref ? `代码：${ref}` : "代码仓库";
  if (kind === "mcp_import") {
    const server = typeof meta.mcp_server === "string" ? meta.mcp_server : "";
    return server ? `MCP：${server}` : "MCP 导入";
  }
  return LEGACY_LINK_KIND_LABEL[kind] ?? kind;
}

type GitSource = {
  id: number;
  knowledge_base_id: number;
  name: string;
  provider: string;
  api_base?: string | null;
  owner: string;
  repo: string;
  branch: string;
  uses_default_branch?: boolean;
  path_prefix: string;
  has_token: boolean;
  token?: string;
  include_globs: string;
  max_file_kb: number;
  max_files: number;
  cron_expression?: string | null;
  enabled: boolean;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

/** 与 GET /api/diagnostics/github 响应对齐（在后端进程所在机器探测出网，与同步一致） */
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

function gitBranchLabel(s: GitSource): string {
  const b = s.branch != null ? String(s.branch) : "";
  if (s.uses_default_branch || !b.trim()) return "默认分支";
  return b;
}

function snippetText(raw: unknown, maxLen: number): string {
  const t = typeof raw === "string" ? raw : raw != null ? String(raw) : "";
  const s = t.trim();
  if (!s) return "";
  if (s.length <= maxLen) return s;
  return `${s.slice(0, maxLen)}…`;
}

function gitSyncStatusChip(status: string | null | undefined): { text: string; className: string } {
  const raw = (status || "").trim();
  const s = raw.toLowerCase();
  if (s === "success") {
    return { text: "成功", className: "border-emerald-200 bg-emerald-50 text-emerald-800" };
  }
  if (s === "error") {
    return { text: "失败", className: "border-rose-200 bg-rose-50 text-rose-800" };
  }
  if (raw) {
    return { text: raw, className: "border-app-border bg-white text-app-secondary" };
  }
  return { text: "尚未同步", className: "border-app-border bg-app-hover text-app-muted" };
}

export default function KnowledgeBaseDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const kbId = Number(params.id);
  const [kb, setKb] = useState<KB | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessageText] = useState("");
  const [messageTone, setMessageTone] = useState<"success" | "error" | "info">("success");
  /** Toast 自动关闭毫秒数；0 表示仅手动关闭（用于代码库同步最终结果） */
  const [toastDurationMs, setToastDurationMs] = useState(4000);
  const gitSyncLockRef = useRef(false);

  type NotifyOpts = { persist?: boolean };

  /** 顶部 Toast（避免命名为 toast，以防与浏览器扩展注入的全局冲突） */
  const notifyUser = useCallback((msg: string, tone: "success" | "error" | "info" = "success", opts?: NotifyOpts) => {
    setMessageText(msg);
    if (!msg) {
      setMessageTone("success");
      setToastDurationMs(4000);
      return;
    }
    setMessageTone(tone);
    if (opts?.persist) {
      setToastDurationMs(0);
    } else {
      setToastDurationMs(tone === "info" ? 14000 : tone === "error" ? 9000 : 4000);
    }
  }, []);

  const dismissToast = useCallback(() => {
    setMessageText("");
    setMessageTone("success");
    setToastDurationMs(4000);
  }, []);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);
  const [entryKeyword, setEntryKeyword] = useState("");

  const [isKbEditOpen, setIsKbEditOpen] = useState(false);
  const [kbNameDraft, setKbNameDraft] = useState("");
  const [kbDescDraft, setKbDescDraft] = useState("");

  const [isEntryModalOpen, setIsEntryModalOpen] = useState(false);
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  const [entryTitle, setEntryTitle] = useState("");
  const [entrySummary, setEntrySummary] = useState("");
  const [entryBody, setEntryBody] = useState("");
  const [entrySaving, setEntrySaving] = useState(false);

  const [viewEntry, setViewEntry] = useState<Entry | null>(null);

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importTab, setImportTab] = useState<"url" | "file" | "mcp">("url");
  const [importUrl, setImportUrl] = useState("");
  const [importTitle, setImportTitle] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [importFileKey, setImportFileKey] = useState(0);

  const [gitSources, setGitSources] = useState<GitSource[]>([]);
  const [gitModalOpen, setGitModalOpen] = useState(false);
  const [gitSaving, setGitSaving] = useState(false);
  const [gitSyncingId, setGitSyncingId] = useState<number | null>(null);
  const [githubDiagBusy, setGithubDiagBusy] = useState(false);
  const [editingGitId, setEditingGitId] = useState<number | null>(null);
  const [browsingGitSource, setBrowsingGitSource] = useState<GitSource | null>(null);
  const [viewEntryFromGit, setViewEntryFromGit] = useState(false);
  const [selectedEntryIds, setSelectedEntryIds] = useState<Set<number>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [showGToken, setShowGToken] = useState(false);
  const [gName, setGName] = useState("");
  const [gProvider, setGProvider] = useState<"github" | "gitlab">("github");
  const [gApiBase, setGApiBase] = useState("");
  const [gOwner, setGOwner] = useState("");
  const [gRepo, setGRepo] = useState("");
  const [gBranch, setGBranch] = useState("");
  const [gPathPrefix, setGPathPrefix] = useState("");
  const [gToken, setGToken] = useState("");
  const [gIncludeGlobs, setGIncludeGlobs] = useState(
    "*.md,*.sql,*.py,*.ts,*.tsx,*.java,*.go,*.rs,*.yml,*.yaml,*.json"
  );
  const [gMaxFileKb, setGMaxFileKb] = useState(512);
  const [gMaxFiles, setGMaxFiles] = useState(200);
  const [gCron, setGCron] = useState("");
  const [gEnabled, setGEnabled] = useState(true);

  // MCP 导入
  const [mcpImportSources, setMcpImportSources] = useState<
    { id: number; name: string; mcp_transport: string; last_import_status?: string; last_import_error?: string; last_import_entries?: number; last_import_at?: string; last_import_kb_id?: number }[]
  >([]);
  const [selectedMcpSourceId, setSelectedMcpSourceId] = useState<number | null>(null);
  const [mcpImportPrompt, setMcpImportPrompt] = useState("");
  const [mcpPhase, setMcpPhase] = useState<"form" | "confirming" | "importing" | "done">("form");
  const [mcpImportResult, setMcpImportResult] = useState<{ status: "success" | "failed"; entries?: number; error?: string } | null>(null);

  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  async function load() {
    if (!Number.isFinite(kbId)) return;
    setLoading(true);
    try {
      const [res, gitRes] = await Promise.all([
        api<{ knowledge_base: KB; entries: Entry[] }>(`/api/knowledge-bases/${kbId}`),
        api<{ git_sources: GitSource[] }>(`/api/knowledge-bases/${kbId}/git-sources`).catch(() => ({ git_sources: [] as GitSource[] }))
      ]);
      setKb(res.knowledge_base);
      setEntries(res.entries);
      setGitSources(gitRes.git_sources ?? []);
    } catch {
      setKb(null);
      setEntries([]);
      setGitSources([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [kbId]);

  /** 从表详情等页带 #entry-{id} 跳转时滚动到对应条目卡片 */
  useEffect(() => {
    if (typeof window === "undefined" || !entries.length) return;
    const raw = window.location.hash.replace(/^#/, "");
    if (!raw.startsWith("entry-")) return;
    const el = document.getElementById(raw);
    if (el) {
      requestAnimationFrame(() => {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }, [entries]);

  useEffect(() => {
    const open = isKbEditOpen || isEntryModalOpen || importModalOpen || gitModalOpen || !!viewEntry;
    if (!open) return;
    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") {
        setIsKbEditOpen(false);
        setIsEntryModalOpen(false);
        if (mcpPhase !== "importing") setImportModalOpen(false);
        setGitModalOpen(false);
        setViewEntry(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isKbEditOpen, isEntryModalOpen, importModalOpen, gitModalOpen, viewEntry, mcpPhase]);

  function openGitModalCreate() {
    setEditingGitId(null);
    setGName("");
    setGProvider("github");
    setGApiBase("");
    setGOwner("");
    setGRepo("");
    setGBranch("");
    setGPathPrefix("");
    setGToken("");
    setShowGToken(false);
    setGIncludeGlobs("*.md,*.sql,*.py,*.ts,*.tsx,*.java,*.go,*.rs,*.yml,*.yaml,*.json");
    setGMaxFileKb(512);
    setGMaxFiles(200);
    setGCron("");
    setGEnabled(true);
    setGitModalOpen(true);
  }

  function openGitModalEdit(s: GitSource) {
    setEditingGitId(s.id);
    setGName(s.name);
    setGProvider(s.provider === "gitlab" ? "gitlab" : "github");
    setGApiBase(s.api_base ?? "");
    setGOwner(s.owner);
    setGRepo(s.repo);
    setGBranch(s.branch ?? "");
    setGPathPrefix(s.path_prefix ?? "");
    setGToken(s.token ?? "");
    setShowGToken(false);
    setGIncludeGlobs(s.include_globs);
    setGMaxFileKb(s.max_file_kb);
    setGMaxFiles(s.max_files);
    setGCron(s.cron_expression ?? "");
    setGEnabled(s.enabled);
    setGitModalOpen(true);
  }

  async function saveGitSource() {
    if (!gName.trim() || !gOwner.trim() || !gRepo.trim()) {
      notifyUser("请填写显示名称、owner 与仓库名");
      return;
    }
    if (!editingGitId && !gToken.trim()) {
      notifyUser("新建代码源时必须填写访问令牌");
      return;
    }
    setGitSaving(true);
    try {
      if (editingGitId) {
        const body: Record<string, unknown> = {
          name: gName.trim(),
          provider: gProvider,
          api_base: gApiBase.trim() || null,
          owner: gOwner.trim(),
          repo: gRepo.trim(),
          branch: gBranch.trim(),
          path_prefix: gPathPrefix.trim(),
          include_globs: gIncludeGlobs.trim(),
          max_file_kb: gMaxFileKb,
          max_files: gMaxFiles,
          cron_expression: gCron.trim() || null,
          enabled: gEnabled
        };
        if (gToken.trim()) body.token = gToken.trim();
        await api(`/api/knowledge-bases/${kbId}/git-sources/${editingGitId}`, {
          method: "PUT",
          body: JSON.stringify(body)
        });
        notifyUser("代码源已更新");
      } else {
        await api(`/api/knowledge-bases/${kbId}/git-sources`, {
          method: "POST",
          body: JSON.stringify({
            name: gName.trim(),
            provider: gProvider,
            api_base: gApiBase.trim() || null,
            owner: gOwner.trim(),
            repo: gRepo.trim(),
            branch: gBranch.trim(),
            path_prefix: gPathPrefix.trim(),
            token: gToken.trim(),
            include_globs: gIncludeGlobs.trim(),
            max_file_kb: gMaxFileKb,
            max_files: gMaxFiles,
            cron_expression: gCron.trim() || null,
            enabled: gEnabled
          })
        });
        notifyUser("代码源已添加，可点击「立即同步」拉取文件");
      }
      setGitModalOpen(false);
      load();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "保存失败",
        "error"
      );
    } finally {
      setGitSaving(false);
    }
  }

  async function syncGitSourceNow(id: number) {
    if (gitSyncLockRef.current) return;
    gitSyncLockRef.current = true;
    setGitSyncingId(id);
    notifyUser("正在从 GitHub/GitLab 拉取文件并写入向量索引，可能需要几十秒至数分钟，请稍候…", "info");
    try {
      const res = await api<{ ok?: boolean; files?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/git-sources/${id}/sync`,
        { method: "POST" }
      );
      notifyUser(res.message || `已同步 ${res.files ?? 0} 个文件`, "success", { persist: true });
      await load();
    } catch (e: unknown) {
      let detail =
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "同步失败";
      detail = (detail || "").trim() || "同步失败（未收到具体错误信息，请打开浏览器开发者工具 → Network 查看该请求响应）";
      notifyUser(detail, "error", { persist: true });
      // 后端会把具体原因写入 git_sources.last_error；刷新列表便于卡片红框展示完整原因
      await load();
    } finally {
      setGitSyncingId(null);
      gitSyncLockRef.current = false;
    }
  }

  async function runGithubConnectivityCheck() {
    if (githubDiagBusy) return;
    setGithubDiagBusy(true);
    notifyUser("正在从后端探测到 GitHub 的连通性（与代码同步使用同一出口）…", "info");
    try {
      const d = await api<GitHubDiagResponse>("/api/diagnostics/github");
      const apiOk = Boolean(d.api_github_com?.reachable);
      const apiLine = apiOk
        ? `api.github.com：可达（HTTP ${d.api_github_com.http_status ?? "?"})`
        : `api.github.com：不可达 — ${(d.api_github_com.error || "").trim() || "未知错误"}`;
      const wwwOk = Boolean(d.github_com?.reachable);
      const wwwLine = wwwOk
        ? `github.com：可达（HTTP ${d.github_com.http_status ?? "?"})`
        : `github.com：不可达 — ${(d.github_com.error || "").trim() || "未知错误"}`;
      const preview = (d.api_github_com.body_preview || "").trim();
      const extra = preview ? `\n响应片段：${snippetText(preview, 160)}` : "";
      notifyUser(`${d.summary}\n\n${apiLine}\n${wwwLine}${extra}`, apiOk ? "success" : "error", { persist: true });
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "探测失败",
        "error",
        { persist: true }
      );
    } finally {
      setGithubDiagBusy(false);
    }
  }

  function confirmDeleteGitSource(s: GitSource) {
    setConfirmState({
      title: "删除该代码源？",
      description: `将删除「${s.name}」及其同步产生的知识条目与索引，定时任务也会移除。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}/git-sources/${s.id}`, { method: "DELETE" });
        notifyUser("代码源已删除");
        load();
      }
    });
  }

  function openKbEdit() {
    if (!kb) return;
    setKbNameDraft(kb.name);
    setKbDescDraft(kb.description || "");
    setIsKbEditOpen(true);
  }

  async function saveKbMeta() {
    if (!kbNameDraft.trim()) return;
    await api(`/api/knowledge-bases/${kbId}`, {
      method: "PUT",
      body: JSON.stringify({ name: kbNameDraft.trim(), description: kbDescDraft.trim() })
    });
    notifyUser("知识库信息已更新");
    setIsKbEditOpen(false);
    load();
  }

  function openNewEntry() {
    setEditingEntryId(null);
    setEntryTitle("");
    setEntrySummary("");
    setEntryBody("");
    setIsEntryModalOpen(true);
  }

  function openEditEntry(e: Entry) {
    setEditingEntryId(e.id);
    setEntryTitle(e.title);
    setEntrySummary(e.summary ?? "");
    setEntryBody(e.body);
    setIsEntryModalOpen(true);
  }

  async function saveEntry() {
    if (!entryTitle.trim()) return;
    setEntrySaving(true);
    try {
      if (editingEntryId) {
        await api(`/api/knowledge-bases/${kbId}/entries/${editingEntryId}`, {
          method: "PUT",
          body: JSON.stringify({
            title: entryTitle.trim(),
            summary: entrySummary.trim(),
            body: entryBody,
          }),
        });
        notifyUser("条目已更新");
      } else {
        await api(`/api/knowledge-bases/${kbId}/entries`, {
          method: "POST",
          body: JSON.stringify({
            title: entryTitle.trim(),
            summary: entrySummary.trim(),
            body: entryBody,
          }),
        });
        notifyUser("条目已添加");
      }
      setIsEntryModalOpen(false);
      load();
    } finally {
      setEntrySaving(false);
    }
  }

  function openImportModal() {
    setImportTab("url");
    setImportUrl("");
    setImportTitle("");
    setImportFileKey((k) => k + 1);
    setSelectedMcpSourceId(null);
    setMcpImportPrompt("");
    setMcpPhase("form");
    setMcpImportResult(null);
    loadMcpSourcesForImport();
    setImportModalOpen(true);
  }

  async function loadMcpSourcesForImport() {
    try {
      const sources = await api<typeof mcpImportSources[number][]>("/api/mcp-sources");
      setMcpImportSources(Array.isArray(sources) ? sources : []);
    } catch {
      setMcpImportSources([]);
    }
  }

  async function pollMcpImportStatus() {
    // 轮询最多 5 分钟（150 次 × 2 秒）
    try {
      for (let i = 0; i < 150; i++) {
        const sources = await api<typeof mcpImportSources[number][]>("/api/mcp-sources");
        if (!Array.isArray(sources)) break;
        setMcpImportSources(sources);
        const stillImporting = sources.some(
          (s) => s.last_import_status === "importing" && s.last_import_kb_id === kbId
        );
        if (!stillImporting) {
          const recent = sources.find(
            (s) => s.last_import_kb_id === kbId && s.last_import_status !== "importing"
          );
          if (recent?.last_import_status === "success") {
            setMcpImportResult({ status: "success", entries: recent.last_import_entries ?? 0 });
          } else if (recent?.last_import_status === "failed") {
            setMcpImportResult({ status: "failed", error: recent.last_import_error || "未知错误" });
          } else {
            setMcpImportResult({ status: "failed", error: "未获取到导入结果" });
          }
          setMcpPhase("done");
          load();
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
      // 超时
      setMcpImportResult({ status: "failed", error: "导入超时（超过 5 分钟），请稍后在条目列表查看结果" });
      setMcpPhase("done");
      load();
    } catch {
      setMcpImportResult({ status: "failed", error: "轮询期间发生网络错误" });
      setMcpPhase("done");
    } finally {
      setImportBusy(false);
    }
  }

  async function submitUrlImport() {
    const u = importUrl.trim();
    if (!u) {
      notifyUser("请填写链接地址");
      return;
    }
    setImportBusy(true);
    try {
      await api(`/api/knowledge-bases/${kbId}/entries/import-url`, {
        method: "POST",
        body: JSON.stringify({
          url: u,
          title: importTitle.trim() || null,
        }),
      });
      notifyUser("已从链接创建条目，可继续手动润色");
      setImportModalOpen(false);
      load();
    } finally {
      setImportBusy(false);
    }
  }

  function requestMcpImport() {
    if (!selectedMcpSourceId) {
      notifyUser("请选择 MCP 源");
      return;
    }
    setMcpPhase("confirming");
  }

  async function doMcpImport() {
    if (!selectedMcpSourceId) return;
    setMcpPhase("importing");
    setImportBusy(true);
    try {
      const body: Record<string, unknown> = {};
      const prompt = mcpImportPrompt.trim();
      if (prompt) body.prompt = prompt;
      await api<{ ok?: boolean; entries?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/import-from-mcp/${selectedMcpSourceId}`,
        { method: "POST", body: JSON.stringify(body) }
      );
      pollMcpImportStatus();
    } catch (e: unknown) {
      setMcpImportResult({
        status: "failed",
        error: e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "MCP 导入失败",
      });
      setMcpPhase("done");
      setImportBusy(false);
    }
  }

  async function onImportFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setImportBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      await apiForm<{ entry: Entry }>(`/api/knowledge-bases/${kbId}/entries/import-file`, fd);
      notifyUser("已从文件创建条目");
      setImportModalOpen(false);
      setImportFileKey((k) => k + 1);
      load();
    } finally {
      setImportBusy(false);
    }
  }

  function confirmDeleteEntry(id: number) {
    const target = entries.find((e) => e.id === id);
    setConfirmState({
      title: "确认删除该条目？",
      description: `将删除「${target?.title || id}」及其向量索引，不可撤销。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}/entries/${id}`, { method: "DELETE" });
        notifyUser("条目已删除");
        load();
      }
    });
  }

  function confirmBatchDelete() {
    const count = selectedEntryIds.size;
    if (count === 0) return;
    setConfirmState({
      title: `确认删除选中的 ${count} 个条目？`,
      description: "将删除所选条目及其向量索引，不可撤销。",
      confirmText: "批量删除",
      danger: true,
      action: async () => {
        setBatchDeleting(true);
        try {
          await api(`/api/knowledge-bases/${kbId}/entries/batch-delete`, {
            method: "POST",
            body: JSON.stringify({ entry_ids: Array.from(selectedEntryIds) }),
          });
          notifyUser(`已删除 ${count} 个条目`);
          setSelectedEntryIds(new Set());
          load();
        } finally {
          setBatchDeleting(false);
        }
      }
    });
  }

  function confirmDeleteKb() {
    if (!kb) return;
    setConfirmState({
      title: "确认删除整个知识库？",
      description: `将删除「${kb.name}」及其中全部条目与索引。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}`, { method: "DELETE" });
        router.push("/knowledge-bases");
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

  async function runSemanticSearch() {
    const q = searchQuery.trim();
    if (!q) return;
    setSearching(true);
    try {
      const res = await api<{ hits: Hit[] }>(`/api/knowledge-bases/${kbId}/search`, {
        method: "POST",
        body: JSON.stringify({ query: q, top_k: 10 })
      });
      setHits(res.hits);
    } finally {
      setSearching(false);
    }
  }

  const filteredEntries = useMemo(() => {
    const q = entryKeyword.trim().toLowerCase();
    return entries.filter(
      (e) => {
        if (e.source_meta?.kind === "git_file") return false;
        if (!q) return true;
        return (
          e.title.toLowerCase().includes(q) ||
          (e.summary ?? "").toLowerCase().includes(q) ||
          e.body.toLowerCase().includes(q)
        );
      }
    );
  }, [entries, entryKeyword]);

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  if (!loading && !kb) {
    return (
      <main className="app-page">
        <p className="text-app-secondary">知识库不存在或已删除。</p>
        <Link className="app-link mt-2 inline-block" href="/knowledge-bases">
          返回列表
        </Link>
      </main>
    );
  }

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", href: "/" },
          { label: "知识库", href: "/knowledge-bases" },
          { label: kb?.name || "…" }
        ]}
        title={kb?.name || "知识库"}
        subtitle={kb?.description || "在此维护条目；保存条目时会写入向量索引，供语义检索与下游 RAG 使用。"}
        actions={
          <div className="app-toolbar flex-wrap">
            <button className="app-button-secondary app-toolbar-action" type="button" onClick={openKbEdit}>
              编辑库信息
            </button>
            <button className="app-button app-toolbar-action" type="button" onClick={openNewEntry}>
              手动新增
            </button>
            <button className="app-button app-toolbar-action" type="button" onClick={openImportModal}>
              导入资料
            </button>
            <button className="app-button-secondary app-toolbar-action" type="button" onClick={openGitModalCreate}>
              代码库同步
            </button>
            <button className="app-button-danger app-toolbar-action" type="button" onClick={confirmDeleteKb}>
              删除知识库
            </button>
          </div>
        }
      />
      <Toast message={message} tone={messageTone} duration={toastDurationMs} onClose={dismissToast} />

      {loading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {!loading && kb && (
        <>
          <section className="app-card mt-6 p-4">
            <h2 className="app-section-title">语义检索（向量）</h2>
            <p className="app-text-muted mt-1 text-xs">
              与常见 RAG 知识库一致：用自然语言提问，按向量相似度返回最相关条目。未配置 OPENAI_API_KEY 时使用确定性本地向量，仅适合联调。
            </p>
            <div className="app-toolbar mt-3 flex-wrap">
              <input
                className="app-input app-toolbar-input min-w-[200px] flex-1"
                placeholder="例如：退款口径如何定义？"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runSemanticSearch();
                }}
              />
              <button className={`app-button app-toolbar-action ${searching ? "is-loading" : ""}`} type="button" onClick={runSemanticSearch} disabled={searching}>
                检索
              </button>
            </div>
            {hits.length > 0 && (
              <ul className="mt-4 space-y-2">
                {hits.map((h) => (
                  <li key={`${h.entry_id}-${h.snippet.slice(0, 20)}`} className="rounded-lg border border-app-border bg-app-hover p-3 text-sm">
                    <p className="font-semibold text-app-primary">{h.title}</p>
                    {(h.summary ?? "").trim() ? (
                      <p className="app-text-muted mt-1 line-clamp-2 text-xs leading-relaxed">{h.summary}</p>
                    ) : null}
                    <p className="app-text-secondary mt-1 line-clamp-4 whitespace-pre-wrap break-words">{h.snippet}</p>
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
                      <button
                        type="button"
                        className="app-link text-xs"
                        onClick={() => {
                          const found = entries.find((x) => x.id === h.entry_id);
                          if (found) setViewEntry(found);
                        }}
                      >
                        查看正文
                      </button>
                      <button
                        type="button"
                        className="app-link text-xs"
                        onClick={() => {
                          const found = entries.find((x) => x.id === h.entry_id);
                          if (found) openEditEntry(found);
                        }}
                      >
                        编辑此条目
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="app-card mt-6 p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="app-section-title">代码库同步（GitHub / GitLab）</h2>
              </div>
              <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-start">
                <button
                  className={`app-button-secondary text-sm ${githubDiagBusy ? "is-loading" : ""}`}
                  type="button"
                  disabled={githubDiagBusy}
                  onClick={() => void runGithubConnectivityCheck()}
                  title="请求由后端发起，与「立即同步」走同一网络路径"
                >
                  {githubDiagBusy ? "探测中…" : "检测 GitHub 网络"}
                </button>
                <button className="app-button-secondary text-sm" type="button" onClick={openGitModalCreate}>
                  添加代码源
                </button>
              </div>
            </div>
            {!gitSources.length ? (
              <p className="app-text-muted mt-4 text-sm">尚未配置代码源。</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {gitSources.map((s) => {
                  const syncChip = gitSyncStatusChip(s.last_sync_status);
                  return (
                  <li
                    key={s.id}
                    className="flex flex-col gap-3 rounded-lg border border-app-border bg-app-hover p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="font-semibold text-app-primary">
                        {s.name}{" "}
                        <span className="font-normal text-app-secondary">
                          ({s.provider} · {s.owner}/{s.repo} · {gitBranchLabel(s)})
                        </span>
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        <span className="app-text-muted">
                          上次同步：{s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : "—"}
                        </span>
                        <span
                          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${syncChip.className}`}
                        >
                          {syncChip.text}
                        </span>
                      </div>
                      {(s.last_sync_status || "").toLowerCase() === "error" &&
                      s.last_error != null &&
                      String(s.last_error).trim() ? (
                        <p className="mt-2 rounded-md border border-rose-100 bg-rose-50/80 px-2 py-1.5 text-[11px] font-medium leading-snug text-rose-900 whitespace-pre-wrap break-words">
                          {String(s.last_error).trim()}
                        </p>
                      ) : null}
                      {s.cron_expression ? (
                        <p className="app-text-muted mt-1 text-xs">定时：{s.cron_expression}</p>
                      ) : (
                        <p className="app-text-muted mt-1 text-xs">定时：仅手动</p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <button
                        className={`app-button text-xs ${gitSyncingId === s.id ? "is-loading" : ""}`}
                        type="button"
                        title={!s.enabled ? "请先在编辑中启用该代码源" : undefined}
                        disabled={!s.enabled || (gitSyncingId !== null && gitSyncingId !== s.id)}
                        onClick={() => void syncGitSourceNow(s.id)}
                      >
                        {gitSyncingId === s.id ? "同步中…" : "立即同步"}
                      </button>
                      <button className="app-button-secondary text-xs" type="button" onClick={() => openGitModalEdit(s)}>
                        编辑
                      </button>
                      <button
                        className="app-button-secondary text-xs"
                        type="button"
                        onClick={() => setBrowsingGitSource(s)}
                      >
                        浏览文件
                      </button>
                      <button
                        className="app-button-danger text-xs"
                        type="button"
                        onClick={() => confirmDeleteGitSource(s)}
                      >
                        删除
                      </button>
                    </div>
                  </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="mt-6 space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <h2 className="app-section-title mb-0">知识条目</h2>
                {filteredEntries.length > 0 && (
                  <label className="flex items-center gap-1.5 text-xs text-app-secondary cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={filteredEntries.length > 0 && filteredEntries.every((e) => selectedEntryIds.has(e.id))}
                      onChange={(ev) => {
                        if (ev.target.checked) {
                          setSelectedEntryIds(new Set(filteredEntries.map((e) => e.id)));
                        } else {
                          setSelectedEntryIds(new Set());
                        }
                      }}
                    />
                    全选
                  </label>
                )}
                {selectedEntryIds.size > 0 && (
                  <button
                    className={`app-button-danger text-xs ${batchDeleting ? "is-loading" : ""}`}
                    type="button"
                    disabled={batchDeleting}
                    onClick={confirmBatchDelete}
                  >
                    删除选中 ({selectedEntryIds.size})
                  </button>
                )}
              </div>
              <input
                className="app-input max-w-md"
                placeholder="在当前库内过滤标题、简述或正文"
                value={entryKeyword}
                onChange={(e) => setEntryKeyword(e.target.value)}
              />
            </div>
            {!filteredEntries.length && (
              <EmptyState
                title={entries.length ? "没有匹配的条目" : "还没有条目"}
                description="手写 Markdown，或先用「导入资料」从网页/Office 文件抓取后再编辑。"
                actionLabel="手动新增"
                onAction={openNewEntry}
              />
            )}
            {filteredEntries.map((e) => (
              <div key={e.id} id={`entry-${e.id}`} className="app-card app-list-item p-4">
                <input
                  type="checkbox"
                  className="mt-1 shrink-0"
                  checked={selectedEntryIds.has(e.id)}
                  onChange={(ev) => {
                    setSelectedEntryIds((prev) => {
                      const next = new Set(prev);
                      if (ev.target.checked) next.add(e.id);
                      else next.delete(e.id);
                      return next;
                    });
                  }}
                />
                <div className="app-list-item-main min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-app-primary">{e.title}</p>
                    {sourceBadgeText(e.source_meta) ? (
                      <span className="rounded-full border border-app-activeBorder bg-app-activeBg px-2 py-0.5 text-[11px] font-medium text-app-chipText">
                        {sourceBadgeText(e.source_meta)}
                      </span>
                    ) : null}
                  </div>
                  <p className="app-text-secondary-strong mt-2 line-clamp-3 whitespace-pre-wrap break-words text-sm">
                    {(e.summary ?? "").trim() || "（无简述）"}
                  </p>
                  {e.source_url ? (
                    <a
                      href={e.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="app-link mt-2 inline-block max-w-full truncate text-xs"
                      title={e.source_url}
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      {e.source_url}
                    </a>
                  ) : null}
                  <p className="app-text-muted mt-2 text-xs">
                    更新：{e.updated_at ? new Date(e.updated_at).toLocaleString() : "-"}
                  </p>
                </div>
                <div className="app-list-item-actions shrink-0">
                  <button className="app-button-secondary" type="button" onClick={() => setViewEntry(e)}>
                    查看正文
                  </button>
                  <button className="app-button-secondary" type="button" onClick={() => openEditEntry(e)}>
                    编辑
                  </button>
                  <button className="app-button-danger" type="button" onClick={() => confirmDeleteEntry(e.id)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </section>
        </>
      )}

      {viewEntry && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => { setViewEntry(null); setViewEntryFromGit(false); }}>
          <div
            className="app-card flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="view-entry-title"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 shrink-0 flex flex-wrap items-start justify-between gap-2">
              <h2 id="view-entry-title" className="app-section-title pr-6">
                {viewEntry.title}
              </h2>
              <div className="flex shrink-0 gap-2">
                {viewEntryFromGit && browsingGitSource === null && (
                  <button
                    className="app-button-secondary text-sm"
                    type="button"
                    onClick={() => {
                      const src = gitSources.find((s) => String(s.id) === viewEntry.source_meta?.git_source_id);
                      setViewEntry(null);
                      setViewEntryFromGit(false);
                      if (src) setBrowsingGitSource(src);
                    }}
                  >
                    ← 返回文件列表
                  </button>
                )}
                <button
                  className="app-button-secondary text-sm"
                  type="button"
                  onClick={() => {
                    const v = viewEntry;
                    setViewEntry(null);
                    setViewEntryFromGit(false);
                    openEditEntry(v);
                  }}
                >
                  编辑
                </button>
                <button className="app-control-button" type="button" onClick={() => { setViewEntry(null); setViewEntryFromGit(false); }}>
                  关闭
                </button>
              </div>
            </div>
            {(viewEntry.summary ?? "").trim() ? (
              <p className="app-text-secondary shrink-0 whitespace-pre-wrap border-b border-app-border pb-4 text-sm leading-relaxed">
                {viewEntry.summary}
              </p>
            ) : (
              <p className="app-text-muted shrink-0 pb-4 text-sm">暂无简述。</p>
            )}
            {viewEntry.source_url ? (
              <a
                href={viewEntry.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="app-link mb-2 mt-2 inline-block shrink-0 break-all text-sm"
              >
                来源链接
              </a>
            ) : null}
            <p className="app-text-muted mt-2 mb-2 shrink-0 text-[11px]">正文</p>
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <pre className="app-text-secondary-strong whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">
                {viewEntry.body || "（空正文）"}
              </pre>
            </div>
          </div>
        </div>
      )}

      {isKbEditOpen && (
        <div
          className="app-modal-backdrop"
          role="presentation"
          onClick={() => setIsKbEditOpen(false)}
        >
          <div className="app-card w-full max-w-lg p-5" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">编辑知识库</h2>
              <button className="app-control-button" type="button" onClick={() => setIsKbEditOpen(false)}>
                关闭
              </button>
            </div>
            <label className="app-form-label">
              <span>名称</span>
              <input className="app-input" value={kbNameDraft} onChange={(ev) => setKbNameDraft(ev.target.value)} />
            </label>
            <label className="app-form-label mt-2">
              <span>描述</span>
              <textarea className="app-input min-h-[88px]" value={kbDescDraft} onChange={(ev) => setKbDescDraft(ev.target.value)} />
            </label>
            <div className="mt-3 flex gap-2">
              <button className="app-button flex-1" type="button" onClick={saveKbMeta} disabled={!kbNameDraft.trim()}>
                保存
              </button>
              <button className="app-button-secondary flex-1" type="button" onClick={() => setIsKbEditOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {isEntryModalOpen && (
        <div
          className="app-modal-backdrop"
          role="presentation"
          onClick={() => setIsEntryModalOpen(false)}
        >
          <div
            className="app-card max-h-[90vh] w-full max-w-2xl overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">{editingEntryId ? "编辑条目" : "手动新增条目"}</h2>
              <button className="app-control-button" type="button" onClick={() => setIsEntryModalOpen(false)}>
                关闭
              </button>
            </div>
            <label className="app-form-label">
              <span>标题</span>
              <input className="app-input" placeholder="简短标题" value={entryTitle} onChange={(ev) => setEntryTitle(ev.target.value)} />
            </label>
            <label className="app-form-label mt-2">
              <span>简述（列表展示）</span>
              <textarea
                className="app-input min-h-[72px]"
                placeholder="留空则从正文自动生成截断简述"
                value={entrySummary}
                onChange={(ev) => setEntrySummary(ev.target.value)}
              />
            </label>
            <label className="app-form-label mt-2">
              <span>正文（支持 Markdown）</span>
              <textarea
                className="app-input min-h-[220px] font-mono text-sm"
                placeholder={"## 说明\n- 要点一\n- 要点二"}
                value={entryBody}
                onChange={(ev) => setEntryBody(ev.target.value)}
              />
            </label>
            <div className="mt-3 flex gap-2">
              <button className={`app-button flex-1 ${entrySaving ? "is-loading" : ""}`} type="button" onClick={saveEntry} disabled={entrySaving || !entryTitle.trim()}>
                {entrySaving ? "保存中…" : "保存"}
              </button>
              <button className="app-button-secondary flex-1" type="button" onClick={() => setIsEntryModalOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {importModalOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => !importBusy && mcpPhase !== "importing" && setImportModalOpen(false)}>
          <div
            className="app-card max-h-[90vh] w-full max-w-lg overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">导入资料</h2>
              <button className="app-control-button" type="button" disabled={importBusy || mcpPhase === "importing"} onClick={() => setImportModalOpen(false)}>
                关闭
              </button>
            </div>
            <p className="app-text-muted text-xs leading-relaxed">
              <strong>链接</strong>：普通 <code className="rounded bg-app-hover px-1">http(s)</code> 网页。
              <strong>MCP 导入</strong>：从偏好设置中配置的 MCP Server 拉取数据。
            </p>
            <div className="mt-3 flex rounded-lg border border-app-border p-0.5">
              <button
                type="button"
                className={`flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  importTab === "url" ? "bg-app-primary text-white" : "text-app-secondary hover:text-app-ink"
                }`}
                onClick={() => setImportTab("url")}
                disabled={importBusy}
              >
                链接抓取
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  importTab === "file" ? "bg-app-primary text-white" : "text-app-secondary hover:text-app-ink"
                }`}
                onClick={() => setImportTab("file")}
                disabled={importBusy}
              >
                上传文件
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  importTab === "mcp" ? "bg-app-primary text-white" : "text-app-secondary hover:text-app-ink"
                }`}
                onClick={() => setImportTab("mcp")}
                disabled={importBusy}
              >
                MCP 导入
              </button>
            </div>

            {importTab === "url" ? (
              <div className="mt-4 space-y-3">
                <label className="app-form-label">
                  <span>网页 URL</span>
                  <input className="app-input font-mono text-sm" placeholder="https://…" value={importUrl} onChange={(ev) => setImportUrl(ev.target.value)} disabled={importBusy} />
                </label>
                <label className="app-form-label">
                  <span>标题（可选，不填则尝试用页面标题或链接摘要）</span>
                  <input className="app-input" value={importTitle} onChange={(ev) => setImportTitle(ev.target.value)} disabled={importBusy} />
                </label>
                <button className={`app-button w-full ${importBusy ? "is-loading" : ""}`} type="button" disabled={importBusy} onClick={() => void submitUrlImport()}>
                  {importBusy ? "导入中…" : "创建条目"}
                </button>
              </div>
            ) : importTab === "file" ? (
              <div className="mt-4 space-y-3">
                <p className="text-xs text-app-secondary">支持：.md、.txt、.html、.docx、.pdf（单文件不超过 12MB）</p>
                <label className="app-form-label">
                  <span>选择文件</span>
                  <input
                    key={importFileKey}
                    type="file"
                    className="app-input cursor-pointer py-2 file:mr-3 file:rounded-md file:border-0 file:bg-app-hover file:px-3 file:py-1.5 file:text-xs"
                    accept=".md,.markdown,.txt,.html,.htm,.docx,.pdf"
                    disabled={importBusy}
                    onChange={(ev) => void onImportFilePicked(ev)}
                  />
                </label>
                {importBusy ? <p className="text-xs text-app-muted">正在解析并写入索引…</p> : null}
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                {/* phase: importing — 进度展示 */}
                {mcpPhase === "importing" && (
                  <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-6 text-center">
                    <p className="text-sm font-medium text-sky-700">正在从 MCP 导入数据…</p>
                    <p className="mt-1 text-xs text-sky-600">后台处理中，请勿关闭此窗口</p>
                    <div className="mt-3 flex justify-center">
                      <div className="h-1.5 w-40 overflow-hidden rounded-full bg-sky-200">
                        <div className="h-full w-1/2 animate-[slide_1.2s_ease-in-out_infinite] rounded-full bg-sky-500" />
                      </div>
                    </div>
                  </div>
                )}

                {/* phase: done — 结果展示 */}
                {mcpPhase === "done" && mcpImportResult && (
                  mcpImportResult.status === "success" ? (
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-5 text-center">
                      <p className="text-sm font-medium text-emerald-700">导入完成</p>
                      <p className="mt-1 text-xs text-emerald-600">共写入 {mcpImportResult.entries ?? 0} 个条目</p>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-5 text-center">
                      <p className="text-sm font-medium text-rose-700">导入失败</p>
                      <p className="mt-1 text-xs text-rose-600">{mcpImportResult.error}</p>
                    </div>
                  )
                )}

                {/* phase: form / confirming — 表单 */}
                {(mcpPhase === "form" || mcpPhase === "confirming") && (
                  mcpImportSources.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-app-border bg-app-hover/30 px-4 py-8 text-center text-sm text-app-muted">
                      暂无 MCP 源，请先在「偏好设置 → MCP 管理」中配置。
                    </div>
                  ) : (
                    <>
                      <label className="app-form-label">
                        <span>选择 MCP 源</span>
                        <select
                          className="app-input"
                          value={selectedMcpSourceId ?? ""}
                          onChange={(ev) => {
                            setSelectedMcpSourceId(ev.target.value ? Number(ev.target.value) : null);
                            setMcpPhase("form");
                          }}
                          disabled={mcpPhase === "confirming"}
                        >
                          <option value="">请选择…</option>
                          {mcpImportSources.map((s) => {
                            const importingThis = s.last_import_status === "importing" && s.last_import_kb_id === kbId;
                            const failedThis = s.last_import_status === "failed" && s.last_import_kb_id === kbId;
                            const successThis = s.last_import_status === "success" && s.last_import_kb_id === kbId;
                            let suffix = `（${s.mcp_transport === "http" ? "HTTP" : "stdio"}）`;
                            if (importingThis) suffix = " ⏳ 导入中…";
                            else if (failedThis) suffix = " ❌ 上次失败";
                            else if (successThis) suffix = ` ✅ ${s.last_import_entries ?? 0} 条`;
                            return (
                              <option key={s.id} value={s.id}>
                                {s.name}{suffix}
                              </option>
                            );
                          })}
                        </select>
                      </label>
                      {/* 上次导入状态提示 */}
                      {(() => {
                        const selected = mcpImportSources.find((s) => s.id === selectedMcpSourceId);
                        if (selected?.last_import_status === "failed" && selected.last_import_kb_id === kbId) {
                          return (
                            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                              上次导入失败：{selected.last_import_error || "未知错误"}
                            </p>
                          );
                        }
                        return null;
                      })()}
                      <label className="app-form-label">
                        <span>自定义提示词（可选，传递给 MCP Tool）</span>
                        <textarea
                          className="app-input min-h-[80px] text-sm"
                          placeholder="例如：获取 Confluence 空间中「产品需求」页面及其子页面"
                          value={mcpImportPrompt}
                          onChange={(ev) => setMcpImportPrompt(ev.target.value)}
                          disabled={mcpPhase === "confirming"}
                          maxLength={2000}
                        />
                        <span className="mt-1 block text-right text-[11px] text-app-muted">
                          {mcpImportPrompt.length}/2000
                        </span>
                      </label>

                      {/* 确认步骤 */}
                      {mcpPhase === "confirming" ? (
                        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 space-y-3">
                          <p className="text-xs font-medium text-amber-800">确认导入</p>
                          <p className="text-xs text-amber-700">
                            此操作会<strong>替换</strong>该 MCP 源在此知识库中之前导入的全部条目，不可撤销。确认继续？
                          </p>
                          <div className="flex gap-2">
                            <button
                              className="app-button-secondary flex-1 text-xs"
                              type="button"
                              onClick={() => setMcpPhase("form")}
                            >
                              取消
                            </button>
                            <button
                              className="app-button flex-1 text-xs"
                              type="button"
                              onClick={() => void doMcpImport()}
                            >
                              确认导入
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          className="app-button w-full"
                          type="button"
                          disabled={!selectedMcpSourceId}
                          onClick={() => requestMcpImport()}
                        >
                          从 MCP 导入
                        </button>
                      )}
                    </>
                  )
                )}

                {/* done 阶段底部操作 */}
                {mcpPhase === "done" && (
                  <button
                    className="app-button-secondary w-full text-xs"
                    type="button"
                    onClick={() => {
                      setMcpPhase("form");
                      setMcpImportResult(null);
                      setSelectedMcpSourceId(null);
                      setMcpImportPrompt("");
                      loadMcpSourcesForImport();
                    }}
                  >
                    重新导入
                  </button>
                )}

                <p className="text-[11px] text-app-muted">
                  MCP 源在「偏好设置 → MCP 管理」中配置。导入的数据会替换该源在此知识库中之前导入的全部条目。
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {gitModalOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => !gitSaving && setGitModalOpen(false)}>
          <div
            className="app-card max-h-[90vh] w-full max-w-lg overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">{editingGitId ? "编辑代码源" : "添加代码源"}</h2>
              <button className="app-control-button" type="button" disabled={gitSaving} onClick={() => setGitModalOpen(false)}>
                关闭
              </button>
            </div>
            <label className="app-form-label">
              <span>显示名称</span>
              <input className="app-input" value={gName} onChange={(ev) => setGName(ev.target.value)} disabled={gitSaving} />
            </label>
            <label className="app-form-label mt-2">
              <span>平台</span>
              <select
                className="app-input"
                value={gProvider}
                onChange={(ev) => setGProvider(ev.target.value as "github" | "gitlab")}
                disabled={gitSaving}
              >
                <option value="github">GitHub</option>
                <option value="gitlab">GitLab（含自建，填 API Base）</option>
              </select>
            </label>
            <label className="app-form-label mt-2">
              <span>API Base（可选）</span>
              <input
                className="app-input font-mono text-xs"
                placeholder={gProvider === "gitlab" ? "https://gitlab.com/api/v4" : "https://api.github.com"}
                value={gApiBase}
                onChange={(ev) => setGApiBase(ev.target.value)}
                disabled={gitSaving}
              />
            </label>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label className="app-form-label">
                <span>Owner / 命名空间</span>
                <input className="app-input font-mono text-sm" placeholder="org 或 user" value={gOwner} onChange={(ev) => setGOwner(ev.target.value)} disabled={gitSaving} />
              </label>
              <label className="app-form-label">
                <span>仓库名</span>
                <input className="app-input font-mono text-sm" placeholder="repo" value={gRepo} onChange={(ev) => setGRepo(ev.target.value)} disabled={gitSaving} />
              </label>
            </div>
            <label className="app-form-label mt-2">
              <span>分支（可选）</span>
              <input
                className="app-input font-mono text-sm"
                placeholder="留空 = 每次用仓库默认分支；填写则固定该分支"
                value={gBranch}
                onChange={(ev) => setGBranch(ev.target.value)}
                disabled={gitSaving}
              />
            </label>
            <label className="app-form-label mt-2">
              <span>子路径前缀（可选）</span>
              <input
                className="app-input font-mono text-sm"
                placeholder="例如 docs/ 或 src/"
                value={gPathPrefix}
                onChange={(ev) => setGPathPrefix(ev.target.value)}
                disabled={gitSaving}
              />
            </label>
            <div className="app-form-label mt-2">
              <span>访问令牌 {editingGitId ? "（留空则不修改）" : ""}</span>
              <div className="relative">
                <input
                  className="app-input font-mono text-sm pr-9"
                  type={showGToken ? "text" : "password"}
                  autoComplete="off"
                  placeholder={gProvider === "gitlab" ? "glpat-… 或 Private Token" : "ghp_… 或 fine-grained PAT"}
                  value={gToken}
                  onChange={(ev) => setGToken(ev.target.value)}
                  disabled={gitSaving}
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-app-muted hover:text-app-primary"
                  tabIndex={-1}
                  onClick={() => setShowGToken((v) => !v)}
                  aria-label={showGToken ? "隐藏令牌" : "显示令牌"}
                >
                  {showGToken ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
            <label className="app-form-label mt-2">
              <span>包含 glob（逗号分隔）</span>
              <input className="app-input font-mono text-xs" value={gIncludeGlobs} onChange={(ev) => setGIncludeGlobs(ev.target.value)} disabled={gitSaving} />
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <label className="app-form-label">
                <span>单文件上限 KB</span>
                <input
                  className="app-input"
                  type="number"
                  min={8}
                  max={4096}
                  value={gMaxFileKb}
                  onChange={(ev) => setGMaxFileKb(Number(ev.target.value) || 512)}
                  disabled={gitSaving}
                />
              </label>
              <label className="app-form-label">
                <span>最多文件数</span>
                <input
                  className="app-input"
                  type="number"
                  min={1}
                  max={5000}
                  value={gMaxFiles}
                  onChange={(ev) => setGMaxFiles(Number(ev.target.value) || 200)}
                  disabled={gitSaving}
                />
              </label>
            </div>
            <label className="app-form-label mt-2">
              <span>Cron（可选，UTC 五段）</span>
              <input
                className="app-input font-mono text-sm"
                placeholder="留空仅手动；例 0 */6 * * * 每 6 小时"
                value={gCron}
                onChange={(ev) => setGCron(ev.target.value)}
                disabled={gitSaving}
              />
            </label>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-app-secondary">
              <input type="checkbox" checked={gEnabled} onChange={(ev) => setGEnabled(ev.target.checked)} disabled={gitSaving} />
              启用（禁用后不会参与定时同步，也无法手动同步）
            </label>
            <div className="mt-4 flex gap-2">
              <button className={`app-button flex-1 ${gitSaving ? "is-loading" : ""}`} type="button" disabled={gitSaving} onClick={() => void saveGitSource()}>
                {gitSaving ? "保存中…" : "保存"}
              </button>
              <button className="app-button-secondary flex-1" type="button" disabled={gitSaving} onClick={() => setGitModalOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {browsingGitSource && (
        <GitFileBrowser
          source={browsingGitSource}
          entries={entries}
          onClose={() => setBrowsingGitSource(null)}
          onViewEntry={(entry) => {
            setViewEntryFromGit(true);
            setBrowsingGitSource(null);
            setViewEntry(entry);
          }}
        />
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
