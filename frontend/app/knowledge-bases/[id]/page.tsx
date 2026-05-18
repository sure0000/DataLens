"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ConfirmDialog from "../../../components/ConfirmDialog";
import GitFileBrowser from "../../../components/GitFileBrowser";
import PageHeader from "../../../components/PageHeader";
import Toast from "../../../components/Toast";
import { api, ApiError, formatApiError } from "../../../lib/api";

import type {
  ApiSource,
  BusinessTerm,
  ChunkRow,
  DocRow,
  Entry,
  GitSource,
  Hit,
  KB,
  LineageData,
  MetricDef,
  PipelineStats,
} from "../../../components/knowledge-bases/types";

import {
  computeOutputCards,
  computePipelineSteps,
  docStatusChip,
} from "../../../components/knowledge-bases/utils";

import CategorySection from "../../../components/knowledge-bases/CategorySection";
import CleanPipeline from "../../../components/knowledge-bases/CleanPipeline";
import DetailStatsPanel from "../../../components/knowledge-bases/DetailStatsPanel";
import DocumentTable from "../../../components/knowledge-bases/DocumentTable";
import EditKbModal from "../../../components/knowledge-bases/EditKbModal";
import EntryViewModal from "../../../components/knowledge-bases/EntryViewModal";
import GitSourceCard from "../../../components/knowledge-bases/GitSourceCard";
import GitSourceForm, {
  defaultGitFormData,
  type GitSourceFormData,
} from "../../../components/knowledge-bases/GitSourceForm";
import ImportPickerModal from "../../../components/knowledge-bases/ImportPickerModal";
import KnowledgeSearchPanel from "../../../components/knowledge-bases/KnowledgeSearchPanel";
import LineageGraph from "../../../components/knowledge-bases/LineageGraph";
import MetricList from "../../../components/knowledge-bases/MetricList";
import SourceResultCards from "../../../components/knowledge-bases/SourceResultCards";
import TermList from "../../../components/knowledge-bases/TermList";

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

type TabId = "documents" | "terms" | "metrics";

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
  const [kbDocCategories, setKbDocCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // ── V2 semantic data ──
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [terms, setTerms] = useState<BusinessTerm[]>([]);
  const [metrics, setMetrics] = useState<MetricDef[]>([]);
  const [lineage, setLineage] = useState<LineageData | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);

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

  // ── Selection ──
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const toggleSelect = useCallback((kind: "doc" | "entry", id: number) => {
    const key = `${kind}-${id}`;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);

  // ── Chunk expansion ──
  const [expandedDocId, setExpandedDocId] = useState<number | null>(null);
  const [chunks, setChunks] = useState<ChunkRow[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);

  // ── Collection / batch expansion ──
  const [expandedCollections, setExpandedCollections] = useState<Set<string>>(new Set());
  const [singleDocPages, setSingleDocPages] = useState<Record<string, number>>({});

  // ── Search ──
  const [searchQuery, setSearchQuery] = useState("");
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);

  // ── Tab ──
  const [activeTab, setActiveTab] = useState<TabId>("documents");

  // ── Modals ──
  const [importPickerOpen, setImportPickerOpen] = useState(false);
  const [editKbOpen, setEditKbOpen] = useState(false);
  const [viewEntry, setViewEntry] = useState<Entry | null>(null);
  const [browsingGitSource, setBrowsingGitSource] = useState<GitSource | null>(null);

  // ── Git edit modal (standalone, for editing existing sources) ──
  const [gitEditOpen, setGitEditOpen] = useState(false);
  const [editingGitId, setEditingGitId] = useState<number | null>(null);
  const [gitFormData, setGitFormData] = useState<GitSourceFormData>(defaultGitFormData());
  const [gitSaving, setGitSaving] = useState(false);

  // ── Git sync ──
  const [gitSyncingId, setGitSyncingId] = useState<number | null>(null);
  const gitSyncLockRef = useRef(false);
  const [githubDiagBusy, setGithubDiagBusy] = useState(false);

  // ── Confirm dialog ──
  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  // ═══════════════════════════════════════════════════
  // Data fetching
  // ═══════════════════════════════════════════════════

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

  async function loadV2Data() {
    const [statsRes, termsRes, metricsRes, lineageRes] = await Promise.all([
      api<PipelineStats>(`/api/knowledge-bases/${kbId}/pipeline-stats`).catch(() => null),
      api<{ terms: BusinessTerm[] }>(`/api/knowledge-bases/${kbId}/terms`).catch(() => ({ terms: [] })),
      api<{ metrics: MetricDef[] }>(`/api/knowledge-bases/${kbId}/metrics`).catch(() => ({ metrics: [] })),
      api<LineageData>(`/api/knowledge-bases/${kbId}/lineage`).catch(() => null),
    ]);
    setStats(statsRes as PipelineStats | null);
    setTerms((termsRes as { terms: BusinessTerm[] })?.terms ?? []);
    setMetrics((metricsRes as { metrics: MetricDef[] })?.metrics ?? []);
    setLineage(lineageRes as LineageData | null);
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
      loadV2Data();
    } catch {
      setKb(null); setEntries([]); setGitSources([]); setApiSources([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, [kbId]);

  /** Scroll to #entry-{id} hash on load */
  useEffect(() => {
    if (typeof window === "undefined" || !entries.length) return;
    const raw = window.location.hash.replace(/^#/, "");
    if (!raw.startsWith("entry-")) return;
    const el = document.getElementById(raw);
    if (el) requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [entries]);

  // ═══════════════════════════════════════════════════
  // Document / chunk actions
  // ═══════════════════════════════════════════════════

  async function loadChunks(docId: number) {
    if (expandedDocId === docId) { setExpandedDocId(null); return; }
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

  // ═══════════════════════════════════════════════════
  // Search
  // ═══════════════════════════════════════════════════

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
    } finally { setSearching(false); }
  }

  function handleHitClick(hit: Hit) {
    const entry = entries.find((e) => e.id === hit.entry_id);
    if (!entry) return;
    const meta = entry.source_meta || {};
    const batchId =
      meta.import_batch && String(meta.import_batch).trim() && String(meta.import_batch) !== "None"
        ? String(meta.import_batch)
        : null;
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

  // ═══════════════════════════════════════════════════
  // Batch delete
  // ═══════════════════════════════════════════════════

  async function handleBatchDelete() {
    if (selectedIds.size === 0) return;
    const entryIds: number[] = [];
    const docIds: number[] = [];
    for (const key of selectedIds) {
      if (key.startsWith("entry-")) entryIds.push(Number(key.slice(6)));
      else if (key.startsWith("doc-")) docIds.push(Number(key.slice(4)));
    }
    await Promise.all([
      entryIds.length > 0
        ? api(`/api/knowledge-bases/${kbId}/entries/batch-delete`, {
            method: "POST", body: JSON.stringify({ entry_ids: entryIds }),
          })
        : Promise.resolve(),
      docIds.length > 0
        ? api(`/api/knowledge-bases/${kbId}/documents/batch-delete`, {
            method: "POST", body: JSON.stringify({ document_ids: docIds }),
          })
        : Promise.resolve(),
    ]);
    setSelectedIds(new Set());
    notifyUser(`已删除 ${selectedIds.size} 项`, "success");
    loadAll();
  }

  // ═══════════════════════════════════════════════════
  // Confirm actions
  // ═══════════════════════════════════════════════════

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
      },
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
      },
    });
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
        loadAll();
      },
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
      const extra = preview ? `\n响应片段：${(preview.length <= 160 ? preview : `${preview.slice(0, 160)}…`)}` : "";
      notifyUser(`${d.summary}\n\n${apiLine}\n${wwwLine}${extra}`, apiOk ? "success" : "error", { persist: true });
    } catch (e: unknown) {
      notifyUser(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "探测失败", "error", { persist: true });
    } finally { setGithubDiagBusy(false); }
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
      category: s.category ?? "",
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
        category: gitFormData.category.trim() || null,
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

  // ═══════════════════════════════════════════════════
  // Semantic pipeline trigger
  // ═══════════════════════════════════════════════════

  async function runSemanticPipeline() {
    setPipelineRunning(true);
    try {
      await api(`/api/knowledge-bases/${kbId}/semantic-pipeline/run`, { method: "POST" });
      notifyUser("语义清洗流水线已启动，请稍后刷新查看结果", "success");
      setTimeout(() => loadV2Data(), 3000);
    } catch (e: unknown) {
      notifyUser(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "启动失败", "error");
    } finally { setPipelineRunning(false); }
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
  // Computed values
  // ═══════════════════════════════════════════════════

  const hasGitSources = gitSources.length > 0;
  const pipelineSteps = computePipelineSteps(stats, hasGitSources);
  const outputCards = computeOutputCards(stats, terms, metrics);

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
            <button className="app-button-secondary app-toolbar-action" type="button" onClick={() => setEditKbOpen(true)}>
              编辑库信息
            </button>
            <button className="app-button app-toolbar-action" type="button" onClick={() => setImportPickerOpen(true)}>
              导入
            </button>
            <button
              className={`app-button-secondary app-toolbar-action ${pipelineRunning ? "is-loading" : ""}`}
              type="button"
              disabled={pipelineRunning}
              onClick={runSemanticPipeline}
            >
              {pipelineRunning ? "启动中…" : "运行清洗"}
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
          {/* ── V2: 清洗流水线 ── */}
          <CleanPipeline steps={pipelineSteps} />

          {/* ── V2: 产出摘要卡片 ── */}
          <SourceResultCards cards={outputCards} />

          {/* ── V2: 数据血缘（仅 Git 源） ── */}
          {hasGitSources && <LineageGraph data={lineage} />}

          {/* ── Tab bar ── */}
          <div className="mt-6 flex items-center gap-1 border-b border-app-border">
            <button
              type="button"
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "documents"
                  ? "border-indigo-500 text-indigo-600"
                  : "border-transparent text-app-muted hover:text-app-primary"
              }`}
              onClick={() => setActiveTab("documents")}
            >
              文档 ({documents.length + entries.filter((e) => e.source_meta?.kind !== "git_file").length})
            </button>
            <button
              type="button"
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "terms"
                  ? "border-indigo-500 text-indigo-600"
                  : "border-transparent text-app-muted hover:text-app-primary"
              }`}
              onClick={() => setActiveTab("terms")}
            >
              术语 ({stats?.term_count ?? terms.length})
            </button>
            <button
              type="button"
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "metrics"
                  ? "border-indigo-500 text-indigo-600"
                  : "border-transparent text-app-muted hover:text-app-primary"
              }`}
              onClick={() => setActiveTab("metrics")}
            >
              指标 ({stats?.metric_count ?? metrics.length})
            </button>
          </div>

          {/* ── Main content area ── */}
          <div className="flex gap-6 mt-4">
            {/* Left: tab content */}
            <div className="flex-1 min-w-0 space-y-4">
              {activeTab === "documents" && (
                <>
                  {/* 检索测试 */}
                  <KnowledgeSearchPanel
                    searching={searching}
                    searched={searched}
                    hits={hits}
                    searchQuery={searchQuery}
                    onSearchQueryChange={setSearchQuery}
                    onSearch={runSearch}
                    onHitClick={handleHitClick}
                  />

                  {/* 分类分组内容 */}
                  <DocumentCategorySections
                    documents={documents}
                    entries={entries}
                    gitSources={gitSources}
                    docsLoading={docsLoading}
                    selectedIds={selectedIds}
                    toggleSelect={toggleSelect}
                    setSelectedIds={setSelectedIds}
                    expandedDocId={expandedDocId}
                    chunks={chunks}
                    chunksLoading={chunksLoading}
                    selectedDocId={selectedDocId}
                    expandedCollections={expandedCollections}
                    setExpandedCollections={setExpandedCollections}
                    singleDocPages={singleDocPages}
                    setSingleDocPages={setSingleDocPages}
                    gitSyncingId={gitSyncingId}
                    githubDiagBusy={githubDiagBusy}
                    onLoadChunks={loadChunks}
                    onRetryDoc={retryDocument}
                    onViewEntry={setViewEntry}
                    onDeleteDoc={confirmDeleteDocument}
                    onDeleteEntry={confirmDeleteEntry}
                    onSyncGit={syncGitSourceNow}
                    onEditGit={openGitEdit}
                    onDeleteGit={confirmDeleteGitSource}
                    onBrowseGit={setBrowsingGitSource}
                    onRefresh={loadAll}
                    onGithubDiag={runGithubConnectivityCheck}
                  />
                </>
              )}

              {activeTab === "terms" && <TermList terms={terms} loading={loading} />}

              {activeTab === "metrics" && <MetricList metrics={metrics} loading={loading} />}
            </div>

            {/* Right: stats sidebar */}
            <DetailStatsPanel stats={stats} loading={loading} />
          </div>

          {/* ── Floating batch delete bar ── */}
          {selectedIds.size > 0 && (
            <div className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-center pb-6 pt-4 bg-gradient-to-t from-white/90 to-transparent pointer-events-none">
              <div className="pointer-events-auto flex items-center gap-4 rounded-xl border border-app-border bg-white px-5 py-3 shadow-lg shadow-black/10">
                <span className="text-sm text-app-primary font-medium whitespace-nowrap">已选 {selectedIds.size} 项</span>
                <div className="h-4 w-px bg-app-border" />
                <button className="text-sm text-app-muted hover:text-app-primary transition-colors" onClick={() => setSelectedIds(new Set())}>
                  取消选择
                </button>
                <button
                  className="app-button-danger text-xs"
                  onClick={() => {
                    setConfirmState({
                      title: "批量删除",
                      description: `确认删除选中的 ${selectedIds.size} 项？删除后无法恢复。`,
                      confirmText: "删除",
                      danger: true,
                      action: handleBatchDelete,
                    });
                  }}
                >
                  删除选中
                </button>
              </div>
            </div>
          )}

          {/* ── Modals ── */}
          <ImportPickerModal
            open={importPickerOpen}
            kbId={kbId}
            kbDocCategories={kbDocCategories}
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

          <EntryViewModal entry={viewEntry} onClose={() => setViewEntry(null)} />

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

// ═══════════════════════════════════════════════════════════
// DocumentCategorySections — category-grouped content renderer
// ═══════════════════════════════════════════════════════════

interface DocumentCategorySectionsProps {
  documents: DocRow[];
  entries: Entry[];
  gitSources: GitSource[];
  docsLoading: boolean;
  selectedIds: Set<string>;
  toggleSelect: (kind: "doc" | "entry", id: number) => void;
  setSelectedIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  expandedDocId: number | null;
  chunks: ChunkRow[];
  chunksLoading: boolean;
  selectedDocId: number | null;
  expandedCollections: Set<string>;
  setExpandedCollections: React.Dispatch<React.SetStateAction<Set<string>>>;
  singleDocPages: Record<string, number>;
  setSingleDocPages: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  gitSyncingId: number | null;
  githubDiagBusy: boolean;
  onLoadChunks: (docId: number) => void;
  onRetryDoc: (docId: number) => void;
  onViewEntry: (entry: Entry) => void;
  onDeleteDoc: (doc: DocRow) => void;
  onDeleteEntry: (entry: Entry) => void;
  onSyncGit: (id: number) => void;
  onEditGit: (s: GitSource) => void;
  onDeleteGit: (s: GitSource) => void;
  onBrowseGit: (s: GitSource) => void;
  onRefresh: () => void;
  onGithubDiag: () => void;
}

function DocumentCategorySections({
  documents,
  entries,
  gitSources,
  docsLoading,
  selectedIds,
  toggleSelect,
  setSelectedIds,
  expandedDocId,
  chunks,
  chunksLoading,
  selectedDocId,
  expandedCollections,
  setExpandedCollections,
  singleDocPages,
  setSingleDocPages,
  gitSyncingId,
  githubDiagBusy,
  onLoadChunks,
  onRetryDoc,
  onViewEntry,
  onDeleteDoc,
  onDeleteEntry,
  onSyncGit,
  onEditGit,
  onDeleteGit,
  onBrowseGit,
  onRefresh,
  onGithubDiag,
}: DocumentCategorySectionsProps) {
  type UnifiedItem = { kind: "doc"; data: DocRow; cat: string } | { kind: "entry"; data: Entry; cat: string };

  const combined: UnifiedItem[] = [
    ...documents.map((d) => ({
      kind: "doc" as const,
      data: d,
      cat: (d.source_meta?.category || "").trim() || "__uncategorized__",
    })),
    ...entries
      .filter((e) => e.source_meta?.kind !== "git_file")
      .map((e) => ({
        kind: "entry" as const,
        data: e,
        cat: (e.source_meta?.category || "").trim() || "__uncategorized__",
      })),
  ];

  // Git sources by category
  const gitByCat: Record<string, GitSource[]> = {};
  for (const gs of gitSources) {
    const c = (gs.category || "").trim() || "__uncategorized__";
    if (!gitByCat[c]) gitByCat[c] = [];
    gitByCat[c].push(gs);
  }

  // Collect all categories
  const allCats = new Set<string>();
  for (const gs of gitSources) allCats.add((gs.category || "").trim() || "__uncategorized__");
  for (const item of combined) allCats.add(item.cat);

  // Batch collections (multi-file imports)
  type Collection = { id: string; title: string; subtitle: string; items: UnifiedItem[] };
  const catCols: Record<string, Collection[]> = {};
  const catSingles: Record<string, UnifiedItem[]> = {};
  for (const c of allCats) { catCols[c] = []; catSingles[c] = []; }
  const assigned = new Set<string>();

  const batchBuckets: Record<string, UnifiedItem[]> = {};
  for (const item of combined) {
    const m = item.kind === "doc" ? item.data.source_meta : item.data.source_meta;
    if (
      m?.kind === "file" &&
      m?.import_batch &&
      String(m.import_batch).trim() &&
      String(m.import_batch) !== "None"
    ) {
      const key = String(m.import_batch);
      if (!batchBuckets[key]) batchBuckets[key] = [];
      batchBuckets[key].push(item);
    }
  }
  for (const [batchId, items] of Object.entries(batchBuckets)) {
    if (items.length > 1) {
      const c = items[0].cat;
      catCols[c].push({ id: `batch-${batchId}`, title: "批量导入", subtitle: `${items.length} 个文件`, items });
      for (const item of items) assigned.add(item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`);
    }
  }

  // Singles (not in any collection)
  const keyToCat: Record<string, string> = {};
  for (const item of combined) {
    const key = item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`;
    if (!assigned.has(key)) catSingles[item.cat].push(item);
    keyToCat[key] = item.cat;
  }
  for (const item of combined) {
    const key = item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`;
    if (!keyToCat[key]) keyToCat[key] = item.cat;
  }

  const sortedCats = Array.from(allCats).sort((a, b) => {
    if (a === "__uncategorized__") return 1;
    if (b === "__uncategorized__") return -1;
    return a.localeCompare(b, "zh-Hans-CN");
  });

  const perPage = 10;

  // Header toolbar
  const totalItems =
    documents.length +
    entries.filter((e) => e.source_meta?.kind !== "git_file").length +
    gitSources.length;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="app-section-title">全部内容</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-app-muted">{totalItems} 项</span>
          <button className="app-button-secondary text-xs" type="button" disabled={githubDiagBusy} onClick={onGithubDiag}>
            {githubDiagBusy ? "检测中…" : "连通性检测"}
          </button>
          <button className="app-button-secondary text-sm" type="button" onClick={onRefresh}>刷新</button>
        </div>
      </div>

      {docsLoading && <p className="app-text-muted text-sm">加载中…</p>}

      {!docsLoading && documents.length === 0 && entries.length === 0 && gitSources.length === 0 && (
        <p className="app-text-muted text-sm">暂无内容。通过「导入」上传文件或接入代码/API 源来添加。</p>
      )}

      {!docsLoading &&
        sortedCats.map((cat) => {
          const gsList = gitByCat[cat] || [];
          const cols = catCols[cat] || [];
          const singles = catSingles[cat] || [];
          singles.sort((a, b) => new Date(b.data.created_at).getTime() - new Date(a.data.created_at).getTime());

          const totalInCat =
            gsList.length + singles.length + cols.reduce((s, c) => s + c.items.length, 0);
          const pg = singleDocPages[cat] || 1;
          const totalPages = Math.max(1, Math.ceil(singles.length / perPage));
          const paged = singles.slice((pg - 1) * perPage, pg * perPage);

          // Item keys in this category (for category-level select-all)
          const catItemKeys = new Set<string>();
          for (const col of cols)
            for (const item of col.items)
              catItemKeys.add(item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`);
          for (const item of singles)
            catItemKeys.add(item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`);

          return (
            <div key={cat}>
              <CategorySection
                name={cat}
                count={totalInCat}
                itemKeys={catItemKeys}
                selectedIds={selectedIds}
                onSelectAll={(checked) => {
                  if (checked) {
                    setSelectedIds((prev) => {
                      const n = new Set(prev);
                      for (const k of catItemKeys) n.add(k);
                      return n;
                    });
                  } else {
                    setSelectedIds((prev) => {
                      const n = new Set(prev);
                      for (const k of catItemKeys) n.delete(k);
                      return n;
                    });
                  }
                }}
              >
                <div className="space-y-3">
                  {/* Git source cards */}
                  {gsList.length > 0 && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      {gsList.map((s) => (
                        <GitSourceCard
                          key={s.id}
                          source={s}
                          syncing={gitSyncingId === s.id}
                          onSync={() => onSyncGit(s.id)}
                          onBrowse={() => onBrowseGit(s)}
                          onEdit={() => onEditGit(s)}
                          onDelete={() => onDeleteGit(s)}
                        />
                      ))}
                    </div>
                  )}

                  {/* Batch collections */}
                  {cols.map((col) => {
                    const expanded = expandedCollections.has(col.id);
                    return (
                      <div key={col.id} id={`col-${col.id}`} className="app-card overflow-hidden">
                        <button
                          type="button"
                          className="flex w-full items-center gap-3 p-4 text-left hover:bg-app-hover transition-colors"
                          onClick={() =>
                            setExpandedCollections((prev) => {
                              const next = new Set(prev);
                              expanded ? next.delete(col.id) : next.add(col.id);
                              return next;
                            })
                          }
                        >
                          <svg
                            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
                            className={`shrink-0 text-app-muted transition-transform ${expanded ? "rotate-90" : ""}`}
                            aria-hidden="true"
                          >
                            <polyline points="9 18 15 12 9 6" />
                          </svg>
                          <div className="min-w-0 flex-1">
                            <p className="font-semibold text-sm text-app-primary truncate">{col.title}</p>
                            <p className="text-xs text-app-muted mt-0.5">{col.subtitle}</p>
                          </div>
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                            className="shrink-0 text-indigo-400" aria-hidden="true"
                          >
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                          </svg>
                        </button>
                        {expanded && (
                          <div className="border-t border-app-border divide-y divide-app-border">
                            {col.items.map((item) => {
                              const key = item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`;
                              const isSelected = selectedIds.has(key);

                              if (item.kind === "doc") {
                                const doc = item.data;
                                const chip = docStatusChip(doc.status);
                                return (
                                  <div key={key} className="flex items-start justify-between gap-3 px-4 py-3 pl-10">
                                    <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                                      <input type="checkbox" className="shrink-0 accent-indigo-500" checked={isSelected} onChange={() => toggleSelect("doc", doc.id)} />
                                      <div className="min-w-0 flex-1">
                                        <p className="text-sm text-app-primary truncate">{doc.title}</p>
                                        <p className="text-xs text-app-muted mt-0.5">
                                          {doc.char_count != null ? `${doc.char_count.toLocaleString()} 字符` : "—"} · {new Date(doc.created_at).toLocaleString()}
                                        </p>
                                      </div>
                                    </label>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${chip.className}`}>{chip.text}</span>
                                      {doc.status === "failed" && <button className="app-button text-xs" type="button" onClick={() => onRetryDoc(doc.id)}>重试</button>}
                                      <button className="app-button-danger text-xs" type="button" onClick={() => onDeleteDoc(doc)}>删除</button>
                                    </div>
                                  </div>
                                );
                              } else {
                                const entry = item.data;
                                const label = entry.source_meta?.label || entry.source_meta?.kind || "API";
                                return (
                                  <div key={key} className="flex items-start justify-between gap-3 px-4 py-3 pl-10">
                                    <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                                      <input type="checkbox" className="shrink-0 accent-indigo-500" checked={isSelected} onChange={() => toggleSelect("entry", entry.id)} />
                                      <div className="min-w-0 flex-1">
                                        <p className="text-sm text-app-primary truncate">{entry.title}</p>
                                        <p className="text-xs text-app-muted mt-0.5">{label} · {new Date(entry.created_at).toLocaleString()}</p>
                                      </div>
                                    </label>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <button className="app-button-secondary text-xs" type="button" onClick={() => onViewEntry(entry)}>查看</button>
                                      <button className="app-button-danger text-xs" type="button" onClick={() => onDeleteEntry(entry)}>删除</button>
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

                  {/* Singles table with pagination */}
                  {paged.length > 0 && (() => {
                    const pagedKeys = new Set(
                      paged.map((item) =>
                        item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`
                      )
                    );
                    const pagedSelected = new Set(
                      Array.from(selectedIds).filter((k) => pagedKeys.has(k))
                    );
                    const allPagedSelected = pagedKeys.size > 0 && pagedKeys.size === pagedSelected.size;

                    const docItems = paged
                      .filter((item) => item.kind === "doc")
                      .map((item) => ({ kind: "doc" as const, data: item.data }));
                    const entryItems = paged
                      .filter((item) => item.kind === "entry")
                      .map((item) => ({ kind: "entry" as const, data: item.data }));
                    const unifiedItems = [...docItems, ...entryItems];

                    return (
                      <DocumentTable
                        items={unifiedItems}
                        selectedIds={selectedIds}
                        onToggleSelect={toggleSelect}
                        onSelectAll={(checked) => {
                          if (checked) {
                            setSelectedIds((prev) => {
                              const n = new Set(prev);
                              for (const k of pagedKeys) n.add(k);
                              return n;
                            });
                          } else {
                            setSelectedIds((prev) => {
                              const n = new Set(prev);
                              for (const k of pagedKeys) n.delete(k);
                              return n;
                            });
                          }
                        }}
                        allSelected={allPagedSelected}
                        onViewEntry={onViewEntry}
                        onDeleteDoc={onDeleteDoc}
                        onDeleteEntry={onDeleteEntry}
                        onRetryDoc={onRetryDoc}
                        onViewChunks={onLoadChunks}
                        expandedDocId={expandedDocId}
                        chunks={chunks}
                        chunksLoading={chunksLoading}
                        selectedDocId={selectedDocId}
                      />
                    );
                  })()}

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2 px-1 py-3">
                      <button
                        type="button"
                        className={`app-button-secondary text-xs ${pg <= 1 ? "opacity-40 cursor-not-allowed" : ""}`}
                        disabled={pg <= 1}
                        onClick={() => setSingleDocPages((prev) => ({ ...prev, [cat]: pg - 1 }))}
                      >
                        上一页
                      </button>
                      <span className="text-xs text-app-muted">{pg} / {totalPages}</span>
                      <button
                        type="button"
                        className={`app-button-secondary text-xs ${pg >= totalPages ? "opacity-40 cursor-not-allowed" : ""}`}
                        disabled={pg >= totalPages}
                        onClick={() => setSingleDocPages((prev) => ({ ...prev, [cat]: pg + 1 }))}
                      >
                        下一页
                      </button>
                    </div>
                  )}
                </div>
              </CategorySection>
            </div>
          );
        })}
    </section>
  );
}
