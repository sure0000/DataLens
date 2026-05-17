"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ConfirmDialog from "../../../components/ConfirmDialog";
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
  category?: string | null;
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

type Hit = {
  entry_id: number;
  title: string;
  summary?: string;
  snippet: string;
  rrf_score?: number;
  vector_rank?: number;
  bm25_rank?: number;
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

  const [isKbEditOpen, setIsKbEditOpen] = useState(false);
  const [kbNameDraft, setKbNameDraft] = useState("");
  const [kbDescDraft, setKbDescDraft] = useState("");

  const [gitSources, setGitSources] = useState<GitSource[]>([]);
  const [gitModalOpen, setGitModalOpen] = useState(false);
  const [gitSaving, setGitSaving] = useState(false);
  const [gitSyncingId, setGitSyncingId] = useState<number | null>(null);
  const [githubDiagBusy, setGithubDiagBusy] = useState(false);
  const [editingGitId, setEditingGitId] = useState<number | null>(null);
  const [browsingGitSource, setBrowsingGitSource] = useState<GitSource | null>(null);
  const [viewEntry, setViewEntry] = useState<Entry | null>(null);
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

  const [apiSources, setApiSources] = useState<ApiSource[]>([]);
  const [apiSourceSyncingId, setApiSourceSyncingId] = useState<number | null>(null);
  const [apiImportModalOpen, setApiImportModalOpen] = useState(false);
  const [apiImportSource, setApiImportSource] = useState<ApiSource | null>(null);
  const [apiImportObjectId, setApiImportObjectId] = useState("");

  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  // 统一导入 Modal 状态
  type ImportStep = "pick" | "file" | "api" | "git";
  const [importPickerOpen, setImportPickerOpen] = useState(false);
  const [importStep, setImportStep] = useState<ImportStep>("pick");
  const [importFileKey, setImportFileKey] = useState(0);

  // 文档分类状态
  const [importCategory, setImportCategory] = useState("");
  const [importCategoryInput, setImportCategoryInput] = useState("");
  const [showImportCategory, setShowImportCategory] = useState(false);
  const [kbDocCategories, setKbDocCategories] = useState<string[]>([]);
  const [gCategory, setGCategory] = useState("");
  const importCatRef = useRef<HTMLInputElement>(null);

  function openImportPicker() { setImportStep("pick"); setImportCategory(""); setImportCategoryInput(""); setImportPickerOpen(true); }
  function closeImportPicker() { setImportPickerOpen(false); }

  // 文档流水线 Tab 状态
  type DocStatus = "pending" | "extracting" | "cleaning" | "chunking" | "embedding" | "indexed" | "failed";
  type DocRow = {
    id: number; title: string; source_type: string; source_meta: Record<string, string>;
    char_count: number | null; status: DocStatus; error_message: string | null;
    stage_timings: Record<string, number>; created_at: string; updated_at: string;
  };
  type ChunkRow = { id: number; chunk_index: number; content: string; quality_score: number | null; char_start: number | null; char_end: number | null; };
  const [documents, setDocuments] = useState<DocRow[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);
  const [expandedDocId, setExpandedDocId] = useState<number | null>(null);
  const [chunks, setChunks] = useState<ChunkRow[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [expandedCollections, setExpandedCollections] = useState<Set<string>>(new Set());
  const [singleDocPages, setSingleDocPages] = useState<Record<string, number>>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 检索测试
  const [searchQuery, setSearchQuery] = useState("");
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);

  async function loadDocuments() {
    setDocsLoading(true);
    try {
      const res = await api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`);
      const docs = res.documents ?? [];
      setDocuments(docs);
      const cats = new Set<string>();
      for (const d of docs) {
        const c = (d.source_meta?.category || "").trim();
        if (c) cats.add(c);
      }
      setKbDocCategories(Array.from(cats).sort((a, b) => a.localeCompare(b, "zh-Hans-CN")));
    } catch { setDocuments([]); } finally { setDocsLoading(false); }
  }

  async function loadChunks(docId: number) {
    if (expandedDocId === docId) {
      setExpandedDocId(null);
      return;
    }
    setChunksLoading(true);
    setSelectedDocId(docId);
    setExpandedDocId(docId);
    try {
      const res = await api<{ chunks: ChunkRow[] }>(`/api/knowledge-bases/${kbId}/documents/${docId}/chunks`);
      setChunks(res.chunks ?? []);
    } catch { setChunks([]); } finally { setChunksLoading(false); }
  }

  async function retryDocument(docId: number) {
    try {
      await api(`/api/knowledge-bases/${kbId}/documents/${docId}/retry`, { method: "POST" });
      notifyUser("已重新提交处理", "success");
      loadDocuments();
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "重试失败", "error");
    }
  }

  async function runSearch() {
    const q = searchQuery.trim();
    if (!q) { notifyUser("请输入搜索关键词", "error"); return; }
    setSearching(true);
    setSearched(true);
    try {
      const res = await api<{ hits: Hit[] }>(`/api/knowledge-bases/${kbId}/search`, {
        method: "POST",
        body: JSON.stringify({ query: q, top_k: 8 }),
      });
      setHits(res.hits ?? []);
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "搜索失败", "error");
    } finally {
      setSearching(false);
    }
  }

  function handleHitClick(hit: Hit) {
    const entry = entries.find((e) => e.id === hit.entry_id);
    if (!entry) return;
    const meta = entry.source_meta || {};
    const batchId = meta.import_batch && String(meta.import_batch).trim() && String(meta.import_batch) !== "None" ? String(meta.import_batch) : null;
    if (batchId) {
      const colId = `batch-${batchId}`;
      setExpandedCollections((prev) => {
        const next = new Set(prev);
        next.add(colId);
        return next;
      });
      setTimeout(() => {
        document.getElementById(`col-${colId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    } else {
      setViewEntry(entry);
    }
  }

  function toggleSelect(kind: "doc" | "entry", id: number) {
    const key = `${kind}-${id}`;
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function clearSelection() { setSelectedIds(new Set()); }

  async function handleBatchDelete() {
    if (selectedIds.size === 0) return;
    setConfirmState({
      title: "批量删除",
      description: `确认删除选中的 ${selectedIds.size} 项？删除后无法恢复。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        const entryIds: number[] = [];
        const docIds: number[] = [];
        for (const key of selectedIds) {
          if (key.startsWith("entry-")) entryIds.push(Number(key.slice(6)));
          else if (key.startsWith("doc-")) docIds.push(Number(key.slice(4)));
        }
        await Promise.all([
          entryIds.length > 0 ? api(`/api/knowledge-bases/${kbId}/entries/batch-delete`, {
            method: "POST",
            body: JSON.stringify({ entry_ids: entryIds }),
          }) : Promise.resolve(),
          docIds.length > 0 ? api(`/api/knowledge-bases/${kbId}/documents/batch-delete`, {
            method: "POST",
            body: JSON.stringify({ document_ids: docIds }),
          }) : Promise.resolve(),
        ]);
        clearSelection();
        notifyUser(`已删除 ${selectedIds.size} 项`, "success");
        load();
      }
    });
  }

  async function deleteDocumentRow(docId: number) {
    try {
      await api(`/api/knowledge-bases/${kbId}/documents/${docId}`, { method: "DELETE" });
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      if (selectedDocId === docId) { setSelectedDocId(null); setChunks([]); }
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "删除失败", "error");
    }
  }

  function docStatusChip(status: DocStatus): { text: string; className: string } {
    const map: Record<DocStatus, { text: string; className: string }> = {
      pending:    { text: "等待中",   className: "border-app-border bg-app-hover text-app-muted" },
      extracting: { text: "提取中",   className: "border-blue-200 bg-blue-50 text-blue-700" },
      cleaning:   { text: "清洗中",   className: "border-blue-200 bg-blue-50 text-blue-700" },
      chunking:   { text: "分块中",   className: "border-blue-200 bg-blue-50 text-blue-700" },
      embedding:  { text: "向量化中", className: "border-indigo-200 bg-indigo-50 text-indigo-700" },
      indexed:    { text: "已索引",   className: "border-emerald-200 bg-emerald-50 text-emerald-800" },
      failed:     { text: "失败",     className: "border-rose-200 bg-rose-50 text-rose-800" },
    };
    return map[status] ?? { text: status, className: "border-app-border bg-white text-app-secondary" };
  }

  async function load() {
    if (!Number.isFinite(kbId)) return;
    setLoading(true);
    try {
      const [res, gitRes, apiRes] = await Promise.all([
        api<{ knowledge_base: KB; entries: Entry[] }>(`/api/knowledge-bases/${kbId}`),
        api<{ git_sources: GitSource[] }>(`/api/knowledge-bases/${kbId}/git-sources`).catch(() => ({ git_sources: [] as GitSource[] })),
        api<{ api_sources: ApiSource[] }>(`/api/api-sources`).catch(() => ({ api_sources: [] as ApiSource[] }))
      ]);
      setKb(res.knowledge_base);
      setEntries(res.entries);
      setGitSources(gitRes.git_sources ?? []);
      setApiSources(apiRes.api_sources ?? []);
      // load documents in parallel
      loadDocuments();
    } catch {
      setKb(null);
      setEntries([]);
      setGitSources([]);
      setApiSources([]);
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
    if (importStep !== "git") return;
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
    setGCategory("");
  }, [importStep]);

  useEffect(() => {
    const open = isKbEditOpen || apiImportModalOpen || gitModalOpen || !!viewEntry;
    if (!open) return;
    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") {
        setIsKbEditOpen(false);
        setApiImportModalOpen(false);
        setGitModalOpen(false);
        setViewEntry(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isKbEditOpen, apiImportModalOpen, gitModalOpen, viewEntry]);

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
    setGCategory("");
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
    setGCategory(s.category ?? "");
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
          enabled: gEnabled,
          category: gCategory.trim() || null,
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
            enabled: gEnabled,
            category: gCategory.trim() || null,
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

  async function importFromApiSource(id: number, objectId: string, category?: string) {
    setApiSourceSyncingId(id);
    notifyUser("正在从 API 源导入内容…", "info");
    try {
      const res = await api<{ ok?: boolean; entries_created?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/api-sources/${id}/import`,
        { method: "POST", body: JSON.stringify({ object_id: objectId.trim(), category: (category || "").trim() }) }
      );
      notifyUser(`已导入 ${res.entries_created ?? 0} 个条目`, "success", { persist: true });
      await load();
    } catch (e: unknown) {
      let detail =
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "导入失败";
      detail = (detail || "").trim() || "导入失败";
      notifyUser(detail, "error", { persist: true });
      await load();
    } finally {
      setApiSourceSyncingId(null);
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

  function confirmDeleteDocument(doc: DocRow) {
    setConfirmState({
      title: "删除该文档？",
      description: `将删除「${doc.title}」及其分块与向量索引。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}/documents/${doc.id}`, { method: "DELETE" });
        setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
        if (selectedDocId === doc.id) { setSelectedDocId(null); setChunks([]); }
        notifyUser("文档已删除", "success");
      }
    });
  }

  function confirmDeleteEntry(entry: Entry) {
    setConfirmState({
      title: "删除该条目？",
      description: `将删除「${entry.title}」及其向量索引。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}/entries/${entry.id}`, { method: "DELETE" });
        setEntries((prev) => prev.filter((e) => e.id !== entry.id));
        notifyUser("条目已删除", "success");
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
          { label: "语义知识库", href: "/knowledge-bases" },
          { label: kb?.name || "…" }
        ]}
        title={kb?.name || "语义知识库"}
        subtitle={kb?.description || "文档经过清洗、分块、向量化后进入语义索引，支持混合检索（向量 + 关键词）。"}
        actions={
          <div className="app-toolbar flex-wrap">
            <button className="app-button-secondary app-toolbar-action" type="button" onClick={openKbEdit}>
              编辑库信息
            </button>
            <button className="app-button app-toolbar-action" type="button" onClick={openImportPicker}>
              导入
            </button>
            <div className="flex items-center gap-1.5">
              <input
                className="app-input h-8 w-44 text-xs"
                placeholder="检索测试…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              />
              <button className={`app-button text-xs h-8 ${searching ? "is-loading" : ""}`} type="button" disabled={searching || !searchQuery.trim()} onClick={runSearch}>
                {searching ? "…" : "搜索"}
              </button>
            </div>
            <button className="app-button-danger app-toolbar-action" type="button" onClick={confirmDeleteKb}>
              删除知识库
            </button>
          </div>
        }
      />
      <Toast message={message} tone={messageTone} duration={toastDurationMs} onClose={dismissToast} />

      {/* ── 检索测试结果 ── */}
      {searched && (hits.length > 0 || !searching) && (
        <section className="mt-4 app-card p-4 space-y-3">
          <h2 className="app-section-title">检索结果</h2>
          {searching && <p className="app-text-muted text-sm">搜索中…</p>}
          {!searching && hits.length === 0 && <p className="app-text-muted text-sm">无匹配结果</p>}
          {hits.length > 0 && (
            <div className="divide-y divide-app-border rounded-lg border border-app-border">
              {hits.map((hit) => (
                <div key={hit.entry_id} className="p-3 space-y-1 cursor-pointer hover:bg-app-hover transition-colors" onClick={() => handleHitClick(hit)}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-app-primary truncate">{hit.title}</p>
                    <span className="shrink-0 text-[11px] text-app-muted">
                      {hit.rrf_score != null && <>RRF: {hit.rrf_score.toFixed(4)}</>}
                      {hit.vector_rank != null && <> · V#{hit.vector_rank}</>}
                      {hit.bm25_rank != null && <> · BM25#{hit.bm25_rank}</>}
                    </span>
                  </div>
                  {(hit.summary || hit.snippet) && (
                    <p className="text-xs text-app-muted line-clamp-3 leading-relaxed">
                      {hit.summary || hit.snippet}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}


      {loading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {!loading && kb && (
        <>
          {/* ── 统一知识库：分类分层展示 ── */}
          <section className="mt-6 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="app-section-title">全部内容</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-app-muted">{documents.length + entries.length + gitSources.length} 项</span>
                <button className="app-button-secondary text-sm" type="button" onClick={() => { loadDocuments(); load(); }}>刷新</button>
              </div>
            </div>
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-3 rounded-xl border border-app-border bg-app-hover px-4 py-2.5">
                <span className="text-sm text-app-primary font-medium">已选 {selectedIds.size} 项</span>
                <button className="app-button-secondary text-xs" type="button" onClick={clearSelection}>取消选择</button>
                <button className="app-button-danger text-xs ml-auto" type="button" onClick={handleBatchDelete}>删除选中</button>
              </div>
            )}
            {docsLoading && <p className="app-text-muted text-sm">加载中…</p>}
            {!docsLoading && documents.length === 0 && entries.length === 0 && gitSources.length === 0 && (
              <p className="app-text-muted text-sm">暂无内容。通过「导入」上传文件或接入代码/API 源来添加。</p>
            )}
            {!docsLoading && (documents.length > 0 || entries.length > 0 || gitSources.length > 0) && (() => {
              type UnifiedItem = { kind: "doc"; data: DocRow; cat: string } | { kind: "entry"; data: Entry; cat: string };
              const combined: UnifiedItem[] = [
                ...documents.map((d) => ({ kind: "doc" as const, data: d, cat: (d.source_meta?.category || "").trim() || "__uncategorized__" })),
                ...entries.map((e) => ({ kind: "entry" as const, data: e, cat: (e.source_meta?.category || "").trim() || "__uncategorized__" })),
              ];

              // 1. 按分类整理 Git 源
              const gitByCat: Record<string, GitSource[]> = {};
              for (const gs of gitSources) {
                const c = (gs.category || "").trim() || "__uncategorized__";
                if (!gitByCat[c]) gitByCat[c] = [];
                gitByCat[c].push(gs);
              }

              // 2. 收集全部分类名
              const allCats = new Set<string>();
              for (const gs of gitSources) allCats.add((gs.category || "").trim() || "__uncategorized__");
              for (const item of combined) allCats.add(item.cat);

              // 3. 整理多文件集合（同批上传的文档归集）
              type Collection = { id: string; title: string; subtitle: string; items: UnifiedItem[] };
              const catCols: Record<string, Collection[]> = {};
              const catSingles: Record<string, UnifiedItem[]> = {};
              for (const c of allCats) { catCols[c] = []; catSingles[c] = []; }
              const assigned = new Set<string>();

              // 同批上传文件（import_batch）归集
              const batchBuckets: Record<string, UnifiedItem[]> = {};
              for (const item of combined) {
                const m = item.kind === "doc" ? item.data.source_meta : item.data.source_meta;
                if (m?.kind === "file" && m?.import_batch && String(m.import_batch).trim() && String(m.import_batch) !== "None") {
                  const key = String(m.import_batch);
                  if (!batchBuckets[key]) batchBuckets[key] = [];
                  batchBuckets[key].push(item);
                }
              }
              for (const [batchId, items] of Object.entries(batchBuckets)) {
                if (items.length > 1) {
                  const c = items[0].cat;
                  catCols[c].push({
                    id: `batch-${batchId}`,
                    title: "批量导入",
                    subtitle: `${items.length} 个文件`,
                    items,
                  });
                  for (const item of items) assigned.add(item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`);
                }
              }

              // 4. 剩余未归集条目 → 单文档列表
              for (const item of combined) {
                const key = item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`;
                if (!assigned.has(key)) catSingles[item.cat].push(item);
              }

              // 5. 分类排序（未分类在最后）
              const sortedCats = Array.from(allCats).sort((a, b) => {
                if (a === "__uncategorized__") return 1;
                if (b === "__uncategorized__") return -1;
                return a.localeCompare(b, "zh-Hans-CN");
              });

              const perPage = 10;

              function toggleCol(id: string) {
                setExpandedCollections(prev => {
                  const next = new Set(prev);
                  if (next.has(id)) next.delete(id);
                  else next.add(id);
                  return next;
                });
              }

              return sortedCats.map((cat) => {
                const gsList = gitByCat[cat] || [];
                const cols = catCols[cat] || [];
                const singles = catSingles[cat] || [];
                singles.sort((a, b) => new Date(b.data.created_at).getTime() - new Date(a.data.created_at).getTime());

                const totalInCat = gsList.length + singles.length + cols.reduce((s, c) => s + c.items.length, 0);
                const pg = singleDocPages[cat] || 1;
                const totalPages = Math.max(1, Math.ceil(singles.length / perPage));
                const paged = singles.slice((pg - 1) * perPage, pg * perPage);

                return (
                  <div key={cat} className="space-y-2">
                    <h3 className="text-sm font-semibold text-app-primary px-1">
                      {cat === "__uncategorized__" ? "未分类" : cat}
                      <span className="ml-1.5 text-xs text-app-muted font-normal">({totalInCat})</span>
                    </h3>

                    {/* — Tier 1: Git 源卡片 — */}
                    {gsList.length > 0 && (
                      <div className="grid gap-3 sm:grid-cols-2">
                        {gsList.map((s) => {
                          const chip = gitSyncStatusChip(s.last_sync_status);
                          const syncing = gitSyncingId === s.id;
                          return (
                            <div key={s.id} className="app-card p-4 flex flex-col gap-3">
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0 flex-1">
                                  <p className="font-semibold text-sm text-app-primary truncate">{s.name}</p>
                                  <p className="text-xs text-app-muted mt-0.5">
                                    {s.provider === "gitlab" ? "GitLab" : "GitHub"} · {s.owner}/{s.repo}
                                  </p>
                                </div>
                                <span className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${chip.className}`}>{chip.text}</span>
                              </div>
                              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-app-muted">
                                <span>分支：{gitBranchLabel(s)}</span>
                                {s.path_prefix && <span>路径：{s.path_prefix}</span>}
                                <span>限制：{s.max_files} 文件 / {s.max_file_kb} KB</span>
                                {s.cron_expression && <span>定时：{s.cron_expression}</span>}
                              </div>
                              {s.last_error && <p className="text-xs text-rose-600 leading-relaxed">{s.last_error}</p>}
                              {s.last_sync_at && <p className="text-xs text-app-muted">上次同步：{new Date(s.last_sync_at).toLocaleString()}</p>}
                              <div className="flex flex-wrap items-center gap-2">
                                <button className={`app-button text-xs ${syncing ? "is-loading" : ""}`} type="button" disabled={syncing} onClick={() => syncGitSourceNow(s.id)}>
                                  {syncing ? "同步中…" : "立即同步"}
                                </button>
                                <button className="app-button-secondary text-xs" type="button" onClick={() => setBrowsingGitSource(s)}>浏览文件</button>
                                <button className="app-button-secondary text-xs" type="button" onClick={() => openGitModalEdit(s)}>编辑</button>
                                <button className="app-button-danger text-xs" type="button" onClick={() => confirmDeleteGitSource(s)}>删除</button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* — Tier 2: 多文件集合卡片（可展开） — */}
                    {cols.length > 0 && cols.map((col) => {
                      const expanded = expandedCollections.has(col.id);
                      return (
                        <div key={col.id} id={`col-${col.id}`} className="app-card overflow-hidden">
                          <button
                            type="button"
                            className="flex w-full items-center gap-3 p-4 text-left hover:bg-app-hover transition-colors"
                            onClick={() => toggleCol(col.id)}
                          >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
                              className={`shrink-0 text-app-muted transition-transform ${expanded ? "rotate-90" : ""}`} aria-hidden="true"
                            >
                              <polyline points="9 18 15 12 9 6" />
                            </svg>
                            <div className="min-w-0 flex-1">
                              <p className="font-semibold text-sm text-app-primary truncate">{col.title}</p>
                              <p className="text-xs text-app-muted mt-0.5">{col.subtitle}</p>
                            </div>
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-indigo-400" aria-hidden="true">
                              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                            </svg>
                          </button>
                          {expanded && (
                            <div className="border-t border-app-border divide-y divide-app-border">
                              {col.items.map((item) => {
                                if (item.kind === "doc") {
                                  const doc = item.data;
                                  const chip = docStatusChip(doc.status);
                                  return (
                                    <div key={`doc-${doc.id}`} className="flex items-start justify-between gap-3 px-4 py-3 pl-10">
                                      <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                                        <input type="checkbox" className="shrink-0 accent-indigo-500" checked={selectedIds.has(`doc-${doc.id}`)} onChange={() => toggleSelect("doc", doc.id)} />
                                        <div className="min-w-0 flex-1">
                                          <p className="text-sm text-app-primary truncate">{doc.title}</p>
                                          <p className="text-xs text-app-muted mt-0.5">
                                            {doc.char_count != null ? `${doc.char_count.toLocaleString()} 字符` : "—"} · {new Date(doc.created_at).toLocaleString()}
                                          </p>
                                        </div>
                                      </label>
                                      <div className="flex shrink-0 items-center gap-2">
                                        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${chip.className}`}>{chip.text}</span>
                                        {doc.status === "failed" && <button className="app-button text-xs" type="button" onClick={() => retryDocument(doc.id)}>重试</button>}
                                        <button className="app-button-danger text-xs" type="button" onClick={() => confirmDeleteDocument(doc)}>删除</button>
                                      </div>
                                    </div>
                                  );
                                } else {
                                  const entry = item.data;
                                  const label = entry.source_meta?.label || entry.source_meta?.kind || "API";
                                  return (
                                    <div key={`entry-${entry.id}`} className="flex items-start justify-between gap-3 px-4 py-3 pl-10">
                                      <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                                        <input type="checkbox" className="shrink-0 accent-indigo-500" checked={selectedIds.has(`entry-${entry.id}`)} onChange={() => toggleSelect("entry", entry.id)} />
                                        <div className="min-w-0 flex-1">
                                          <p className="text-sm text-app-primary truncate">{entry.title}</p>
                                          <p className="text-xs text-app-muted mt-0.5">{label} · {new Date(entry.created_at).toLocaleString()}</p>
                                        </div>
                                      </label>
                                      <div className="flex shrink-0 items-center gap-2">
                                        <button className="app-button-secondary text-xs" type="button" onClick={() => setViewEntry(entry)}>查看</button>
                                        <button className="app-button-danger text-xs" type="button" onClick={() => confirmDeleteEntry(entry)}>删除</button>
                                      </div>
                                    </div>
                                  );
                                }
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}

                    {/* — Tier 3: 单文档列表（分页） — */}
                    {paged.length > 0 && paged.map((item) => {
                      if (item.kind === "doc") {
                        const doc = item.data;
                        const chip = docStatusChip(doc.status);
                        const isExpanded = expandedDocId === doc.id;
                        return (
                          <div key={`doc-${doc.id}`} className="app-card">
                            <div className="flex items-start justify-between gap-3 p-4">
                              <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                                <input type="checkbox" className="shrink-0 accent-indigo-500" checked={selectedIds.has(`doc-${doc.id}`)} onChange={() => toggleSelect("doc", doc.id)} />
                                <div className="min-w-0 flex-1">
                                  <p className="app-text-primary font-medium text-sm truncate">{doc.title}</p>
                                  <p className="app-text-muted text-xs mt-0.5">
                                    {doc.source_meta?.label || doc.source_type} · {doc.char_count != null ? `${doc.char_count.toLocaleString()} 字符` : "—"} · {new Date(doc.created_at).toLocaleString()}
                                  </p>
                                  {doc.error_message && <p className="mt-1 text-xs text-rose-600">{doc.error_message}</p>}
                                {doc.status === "indexed" && Object.keys(doc.stage_timings).length > 0 && (
                                  <p className="mt-1 text-[11px] text-app-muted">
                                    {Object.entries(doc.stage_timings).map(([k, v]) => `${k}: ${v}ms`).join(" · ")}
                                  </p>
                                )}
                              </div></label>
                              <div className="flex shrink-0 items-center gap-2">
                                <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${chip.className}`}>{chip.text}</span>
                                {doc.status === "indexed" && (
                                  <button className="app-button-secondary text-xs" type="button" onClick={() => loadChunks(doc.id)}>
                                    {isExpanded ? "收起分块" : "查看分块"}
                                  </button>
                                )}
                                {doc.status === "failed" && <button className="app-button text-xs" type="button" onClick={() => retryDocument(doc.id)}>重试</button>}
                                <button className="app-button-danger text-xs" type="button" onClick={() => confirmDeleteDocument(doc)}>删除</button>
                              </div>
                            </div>
                            {isExpanded && (
                              <div className="border-t border-app-border px-4 pb-4 pt-3 space-y-2">
                                {chunksLoading && selectedDocId === doc.id && <p className="app-text-muted text-sm">加载中…</p>}
                                {!chunksLoading && chunks.length === 0 && <p className="app-text-muted text-sm">该文档暂无分块数据。</p>}
                                {chunks.map((c) => (
                                  <div key={c.id} className="rounded-lg border border-app-border bg-app-hover p-3">
                                    <div className="flex items-center justify-between gap-2 mb-1">
                                      <span className="text-xs text-app-muted">块 #{c.chunk_index + 1}</span>
                                      {c.quality_score != null && (
                                        <span className={`text-[11px] font-medium ${c.quality_score >= 0.7 ? "text-emerald-600" : c.quality_score >= 0.4 ? "text-amber-600" : "text-rose-500"}`}>
                                          质量 {c.quality_score.toFixed(2)}
                                        </span>
                                      )}
                                    </div>
                                    <pre className="whitespace-pre-wrap break-words text-xs text-app-secondary">{c.content}</pre>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      } else {
                        const entry = item.data;
                        const label = entry.source_meta?.label || entry.source_meta?.kind || "API";
                        return (
                          <div key={`entry-${entry.id}`} className="app-card" id={`entry-${entry.id}`}>
                            <div className="flex items-start justify-between gap-3 p-4">
                              <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                                <input type="checkbox" className="shrink-0 accent-indigo-500" checked={selectedIds.has(`entry-${entry.id}`)} onChange={() => toggleSelect("entry", entry.id)} />
                                <div className="min-w-0 flex-1">
                                  <p className="app-text-primary font-medium text-sm truncate">{entry.title}</p>
                                  <p className="app-text-muted text-xs mt-0.5">
                                    {label} · {new Date(entry.created_at).toLocaleString()}
                                    {entry.source_url && <> · <a className="app-link" href={entry.source_url} target="_blank" rel="noreferrer">源链接</a></>}
                                  </p>
                                  {entry.summary && <p className="app-text-muted text-xs mt-1 line-clamp-2">{entry.summary}</p>}
                                </div></label>
                              <div className="flex shrink-0 items-center gap-2">
                                <button className="app-button-secondary text-xs" type="button" onClick={() => setViewEntry(entry)}>查看</button>
                                <button className="app-button-danger text-xs" type="button" onClick={() => confirmDeleteEntry(entry)}>删除</button>
                              </div>
                            </div>
                          </div>
                        );
                      }
                    })}

                    {/* — 分页 — */}
                    {totalPages > 1 && (
                      <div className="flex items-center justify-center gap-2 px-1 py-2">
                        <button
                          type="button"
                          className={`app-button-secondary text-xs ${pg <= 1 ? "opacity-40 cursor-not-allowed" : ""}`}
                          disabled={pg <= 1}
                          onClick={() => setSingleDocPages(prev => ({ ...prev, [cat]: pg - 1 }))}
                        >
                          上一页
                        </button>
                        <span className="text-xs text-app-muted">{pg} / {totalPages}</span>
                        <button
                          type="button"
                          className={`app-button-secondary text-xs ${pg >= totalPages ? "opacity-40 cursor-not-allowed" : ""}`}
                          disabled={pg >= totalPages}
                          onClick={() => setSingleDocPages(prev => ({ ...prev, [cat]: pg + 1 }))}
                        >
                          下一页
                        </button>
                      </div>
                    )}
                  </div>
                );
              });
            })()}
          </section>

        </>
      )}

      {/* ── 统一导入 Modal ── */}
      {importPickerOpen && (
        <div
          className="app-modal-backdrop"
          role="presentation"
          onClick={closeImportPicker}
        >
          <div
            className="app-card w-full max-w-2xl max-h-[90vh] overflow-auto p-6"
            role="dialog"
            aria-modal="true"
            aria-labelledby="import-picker-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center justify-between">
              <div>
                {importStep !== "pick" && (
                  <button
                    type="button"
                    className="app-control-button mb-1 text-xs text-app-muted"
                    onClick={() => setImportStep("pick")}
                  >
                    ← 返回
                  </button>
                )}
                <h2 id="import-picker-title" className="app-section-title">
                  {importStep === "pick" && "选择导入方式"}
                  {importStep === "file" && "文档导入"}
                  {importStep === "api" && "官方 API 导入"}
                  {importStep === "git" && "代码库同步"}
                </h2>
              </div>
              <button className="app-control-button" onClick={closeImportPicker}>关闭</button>
            </div>

            {/* Step 1: 选择方式 */}
            {importStep === "pick" && (
              <div className="grid grid-cols-3 gap-4">
                {([
                  {
                    key: "file" as ImportStep,
                    icon: (
                      <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                        <line x1="16" y1="13" x2="8" y2="13" />
                        <line x1="16" y1="17" x2="8" y2="17" />
                        <polyline points="10 9 9 9 8 9" />
                      </svg>
                    ),
                    title: "文档导入",
                    desc: "上传 md / pdf / docx / xlsx / csv / txt",
                  },
                  {
                    key: "api" as ImportStep,
                    icon: (
                      <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="2" y1="12" x2="22" y2="12" />
                        <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
                      </svg>
                    ),
                    title: "官方 API",
                    desc: "Notion / Confluence / 飞书",
                  },
                  {
                    key: "git" as ImportStep,
                    icon: (
                      <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="18" cy="18" r="3" />
                        <circle cx="6" cy="6" r="3" />
                        <path d="M13 6h3a2 2 0 012 2v7" />
                        <line x1="6" y1="9" x2="6" y2="21" />
                      </svg>
                    ),
                    title: "代码库",
                    desc: "GitHub / GitLab 仓库同步",
                  },
                ] as { key: ImportStep; icon: React.ReactNode; title: string; desc: string }[]).map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className="app-card app-card-interactive flex flex-col items-center gap-3 p-5 text-center"
                    onClick={() => setImportStep(item.key)}
                  >
                    <span className="text-indigo-500">{item.icon}</span>
                    <span className="font-semibold text-sm text-app-primary">{item.title}</span>
                    <span className="text-xs text-app-muted leading-relaxed">{item.desc}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Step 2a: 文档导入 */}
            {importStep === "file" && (
              <div className="space-y-4">
                <p className="app-text-muted text-sm">支持 .md .txt .html .docx .pdf .xlsx .csv，单文件最大 12MB。</p>

                {/* 分类 combobox */}
                <div className="relative">
                  <label className="app-form-label">
                    <span>分类（选填）</span>
                    <input
                      ref={importCatRef}
                      className="app-input"
                      placeholder="选择已有分类或输入新分类名"
                      value={importCategoryInput}
                      onChange={(e) => {
                        setImportCategoryInput(e.target.value);
                        setImportCategory(e.target.value);
                        setShowImportCategory(true);
                      }}
                      onFocus={() => setShowImportCategory(true)}
                      onBlur={() => setTimeout(() => setShowImportCategory(false), 150)}
                    />
                  </label>
                  {showImportCategory && (
                    <div className="absolute left-0 right-0 z-20 mt-1 rounded-xl border border-app-border bg-white shadow-lg overflow-hidden">
                      {kbDocCategories
                        .filter((c) => c.toLowerCase().includes(importCategoryInput.toLowerCase()) && c !== importCategoryInput)
                        .map((c) => (
                          <button
                            key={c}
                            type="button"
                            className="w-full px-3 py-2 text-left text-sm hover:bg-app-hover text-app-primary"
                            onMouseDown={() => {
                              setImportCategory(c);
                              setImportCategoryInput(c);
                              setShowImportCategory(false);
                            }}
                          >
                            {c}
                          </button>
                        ))}
                      {importCategoryInput.trim() && !kbDocCategories.includes(importCategoryInput.trim()) && (
                        <button
                          type="button"
                          className="w-full px-3 py-2 text-left text-sm hover:bg-app-hover text-indigo-600"
                          onMouseDown={() => {
                            setImportCategory(importCategoryInput.trim());
                            setImportCategoryInput(importCategoryInput.trim());
                            setShowImportCategory(false);
                          }}
                        >
                          新建分类 &ldquo;{importCategoryInput.trim()}&rdquo;
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <label
                  className="flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-app-border bg-app-hover p-8 cursor-pointer hover:border-indigo-400 transition-colors"
                >
                  <svg className="h-10 w-10 text-app-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="16 16 12 12 8 16" />
                    <line x1="12" y1="12" x2="12" y2="21" />
                    <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3" />
                  </svg>
                  <span className="text-sm text-app-secondary">点击选择文件或拖拽到此处</span>
                  <input
                    key={importFileKey}
                    type="file"
                    className="sr-only"
                    accept=".md,.txt,.html,.htm,.docx,.pdf,.xlsx,.csv"
                    multiple
                    onChange={async (e) => {
                      const files = Array.from(e.target.files ?? []);
                      if (!files.length) return;
                      const cat = importCategory.trim();
                      const importBatch = crypto.randomUUID();
                      let successCount = 0;
                      for (const file of files) {
                        try {
                          const fd = new FormData();
                          fd.append("file", file);
                          fd.append("import_batch", importBatch);
                          if (cat) fd.append("category", cat);
                          await apiForm(`/api/knowledge-bases/${kbId}/entries/import-file`, fd);
                          successCount++;
                        } catch (err: unknown) {
                          notifyUser(`${file.name} 导入失败：${err instanceof Error ? err.message : "未知错误"}`, "error");
                        }
                      }
                      if (successCount > 0) {
                        notifyUser(`成功导入 ${successCount} 个文件，流水线处理中…`, "success");
                        setImportFileKey((k) => k + 1);
                        closeImportPicker();
                        load();
                      }
                    }}
                  />
                </label>
              </div>
            )}

            {/* Step 2b: 官方 API 导入 */}
            {importStep === "api" && (
              <div className="space-y-4">
                {apiSources.length === 0 && (
                  <p className="app-text-muted text-sm">暂无已配置的 API 源，请前往「设置 → API 源」添加。</p>
                )}
                {apiSources.map((s) => (
                  <div key={s.id} className="app-card p-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-sm text-app-primary">{s.name}</p>
                      <p className="text-xs text-app-muted">{s.integration}</p>
                    </div>
                    <button
                      type="button"
                      className="app-button-secondary text-sm shrink-0"
                      onClick={() => {
                        setApiImportSource(s);
                        setApiImportObjectId("");
                        setApiImportModalOpen(true);
                        closeImportPicker();
                      }}
                    >
                      导入
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Step 2c: 代码库同步 — 直接展示配置项 */}
            {importStep === "git" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="app-form-label sm:col-span-2">
                    <span>显示名称</span>
                    <input className="app-input" value={gName} onChange={(ev) => setGName(ev.target.value)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
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
                  <label className="app-form-label">
                    <span>API Base（可选）</span>
                    <input
                      className="app-input font-mono text-xs"
                      placeholder={gProvider === "gitlab" ? "https://gitlab.com/api/v4" : "https://api.github.com"}
                      value={gApiBase}
                      onChange={(ev) => setGApiBase(ev.target.value)}
                      disabled={gitSaving}
                    />
                  </label>
                  <label className="app-form-label">
                    <span>Owner</span>
                    <input className="app-input font-mono text-sm" placeholder="org 或 user" value={gOwner} onChange={(ev) => setGOwner(ev.target.value)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
                    <span>仓库名</span>
                    <input className="app-input font-mono text-sm" placeholder="repo" value={gRepo} onChange={(ev) => setGRepo(ev.target.value)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
                    <span>分支（可选）</span>
                    <input
                      className="app-input font-mono text-sm"
                      placeholder="留空 = 默认分支"
                      value={gBranch}
                      onChange={(ev) => setGBranch(ev.target.value)}
                      disabled={gitSaving}
                    />
                  </label>
                  <label className="app-form-label">
                    <span>子路径前缀（可选）</span>
                    <input
                      className="app-input font-mono text-sm"
                      placeholder="例如 docs/"
                      value={gPathPrefix}
                      onChange={(ev) => setGPathPrefix(ev.target.value)}
                      disabled={gitSaving}
                    />
                  </label>
                  <label className="app-form-label sm:col-span-2">
                    <span>访问令牌</span>
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
                  </label>
                  <label className="app-form-label sm:col-span-2">
                    <span>包含 glob（逗号分隔）</span>
                    <input className="app-input font-mono text-xs" value={gIncludeGlobs} onChange={(ev) => setGIncludeGlobs(ev.target.value)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
                    <span>单文件上限 KB</span>
                    <input className="app-input" type="number" min={8} max={4096} value={gMaxFileKb} onChange={(ev) => setGMaxFileKb(Number(ev.target.value) || 512)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
                    <span>最多文件数</span>
                    <input className="app-input" type="number" min={1} max={5000} value={gMaxFiles} onChange={(ev) => setGMaxFiles(Number(ev.target.value) || 200)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
                    <span>分类（选填）</span>
                    <input className="app-input" placeholder="例如：API 文档、业务规范" value={gCategory} onChange={(ev) => setGCategory(ev.target.value)} disabled={gitSaving} />
                  </label>
                  <label className="app-form-label">
                    <span>Cron（可选）</span>
                    <input className="app-input font-mono text-sm" placeholder="例 0 */6 * * * 每 6 小时" value={gCron} onChange={(ev) => setGCron(ev.target.value)} disabled={gitSaving} />
                  </label>
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-sm text-app-secondary">
                  <input type="checkbox" checked={gEnabled} onChange={(ev) => setGEnabled(ev.target.checked)} disabled={gitSaving} />
                  启用
                </label>
                <div className="flex gap-2 pt-1">
                  <button
                    className={`app-button flex-1 ${gitSaving ? "is-loading" : ""}`}
                    type="button"
                    disabled={gitSaving || !gName.trim() || !gOwner.trim() || !gRepo.trim() || !gToken.trim()}
                    onClick={async () => {
                      if (gitSaving) return;
                      setGitSaving(true);
                      try {
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
                            enabled: gEnabled,
                            category: gCategory.trim() || null,
                          })
                        });
                        notifyUser("代码源已添加，可点击「立即同步」拉取文件");
                        closeImportPicker();
                        load();
                      } catch (e: unknown) {
                        notifyUser(
                          e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "保存失败",
                          "error"
                        );
                      } finally {
                        setGitSaving(false);
                      }
                    }}
                  >
                    {gitSaving ? "保存中…" : "保存"}
                  </button>
                  <button className="app-button-secondary flex-1" type="button" onClick={() => setImportStep("pick")}>返回</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {viewEntry && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setViewEntry(null)}>
          <div
            className="app-card flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden p-5"
            role="dialog"
            aria-modal="true"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 shrink-0 flex items-start justify-between gap-2">
              <h2 className="app-section-title pr-6">{viewEntry.title}</h2>
              <button className="app-control-button shrink-0" type="button" onClick={() => setViewEntry(null)}>关闭</button>
            </div>
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
              <span>分类（选填）</span>
              <input
                className="app-input"
                placeholder="例如：API 文档、业务规范"
                value={gCategory}
                onChange={(ev) => setGCategory(ev.target.value)}
                disabled={gitSaving}
              />
            </label>
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

      {apiImportModalOpen && apiImportSource && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setApiImportModalOpen(false)}>
          <div
            className="app-card max-h-[90vh] w-full max-w-md overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="api-import-title"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 id="api-import-title" className="app-section-title">导入到知识库</h2>
              <button className="app-control-button" type="button" onClick={() => setApiImportModalOpen(false)}>
                关闭
              </button>
            </div>
            <p className="text-sm text-app-secondary">
              源：<span className="font-semibold text-app-primary">{apiImportSource.name}</span>
              <span className="text-app-muted">（{apiImportSource.integration === "notion" ? "Notion" : apiImportSource.integration === "confluence" ? "Confluence" : "飞书"}）</span>
            </p>
            <label className="app-form-label mt-3">
              <span>
                {apiImportSource.integration === "notion" ? "Page / Database ID" :
                 apiImportSource.integration === "confluence" ? "Page ID" :
                 "Doc Token"}
              </span>
              <input
                className="app-input font-mono text-sm"
                placeholder={
                  apiImportSource.integration === "notion" ? "Notion 页面或数据库的 UUID" :
                  apiImportSource.integration === "confluence" ? "Confluence 页面 ID（数字）" :
                  "飞书文档 Token"
                }
                value={apiImportObjectId}
                onChange={(ev) => setApiImportObjectId(ev.target.value)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" && apiImportObjectId.trim()) {
                    void importFromApiSource(apiImportSource.id, apiImportObjectId, importCategory).then(() => setApiImportModalOpen(false));
                  }
                }}
              />
            </label>
            <div className="app-form-label mt-3 relative">
              <span>分类（选填）</span>
              <input
                className="app-input"
                placeholder="选择已有分类或输入新分类名"
                value={importCategoryInput}
                onChange={(e) => {
                  setImportCategoryInput(e.target.value);
                  setImportCategory(e.target.value);
                  setShowImportCategory(true);
                }}
                onFocus={() => setShowImportCategory(true)}
                onBlur={() => setTimeout(() => setShowImportCategory(false), 150)}
              />
              {showImportCategory && (
                <div className="absolute left-0 right-0 z-20 mt-1 rounded-xl border border-app-border bg-white shadow-lg overflow-hidden">
                  {kbDocCategories
                    .filter((c) => c.toLowerCase().includes(importCategoryInput.toLowerCase()) && c !== importCategoryInput)
                    .map((c) => (
                      <button
                        key={c}
                        type="button"
                        className="w-full px-3 py-2 text-left text-sm hover:bg-app-hover text-app-primary"
                        onMouseDown={() => {
                          setImportCategory(c);
                          setImportCategoryInput(c);
                          setShowImportCategory(false);
                        }}
                      >
                        {c}
                      </button>
                    ))}
                  {importCategoryInput.trim() && !kbDocCategories.includes(importCategoryInput.trim()) && (
                    <button
                      type="button"
                      className="w-full px-3 py-2 text-left text-sm hover:bg-app-hover text-indigo-600"
                      onMouseDown={() => {
                        setImportCategory(importCategoryInput.trim());
                        setImportCategoryInput(importCategoryInput.trim());
                        setShowImportCategory(false);
                      }}
                    >
                      新建分类 &ldquo;{importCategoryInput.trim()}&rdquo;
                    </button>
                  )}
                </div>
              )}
            </div>
            <div className="mt-4 flex gap-2">
              <button
                className={`app-button flex-1 ${apiSourceSyncingId === apiImportSource.id ? "is-loading" : ""}`}
                type="button"
                disabled={!apiImportObjectId.trim() || apiSourceSyncingId === apiImportSource.id}
                onClick={() => void importFromApiSource(apiImportSource.id, apiImportObjectId, importCategory).then(() => setApiImportModalOpen(false))}
              >
                {apiSourceSyncingId === apiImportSource.id ? "导入中…" : "导入"}
              </button>
              <button className="app-button-secondary flex-1" type="button" onClick={() => setApiImportModalOpen(false)} disabled={apiSourceSyncingId === apiImportSource.id}>
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
