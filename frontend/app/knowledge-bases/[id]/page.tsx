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
  DatabaseImport,
  DocRow,
  Entry,
  GitSource,
  KB,
  OntologyCleaningResults,
  OntologyCounts,
  SourceCleaningStat,
} from "../../../components/knowledge-bases/types";

import EditKbModal from "../../../components/knowledge-bases/EditKbModal";
import GitSourceForm, {
  defaultGitFormData,
  type GitSourceFormData,
} from "../../../components/knowledge-bases/GitSourceForm";
import ImportPickerModal from "../../../components/knowledge-bases/ImportPickerModal";
import EvidencePackageList from "../../../components/knowledge-bases/EvidencePackageList";
import { kbModelingSectionUrl, ontologyUrl } from "../../../lib/ontologyRoutes";
import type { SourceItem } from "../../../components/knowledge-bases/SourceCard";
import SourceCardGrid from "../../../components/knowledge-bases/SourceCardGrid";
import {
  canSemanticCleanSource,
  isDocumentIndexingInProgress,
  semanticCleanDisabledReason,
} from "../../../components/knowledge-bases/documentIndexPolicy";
import SemanticCleanChoiceDialog, {
  type SemanticCleanResumeOptions,
} from "../../../components/knowledge-bases/SemanticCleanChoiceDialog";

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

  // ── Database imports ──
  const [databaseImports, setDatabaseImports] = useState<DatabaseImport[]>([]);

  // ── Semantic cleaning ──
  const [cleaningSourceId, setCleaningSourceId] = useState<number | null>(null);
  const cleaningPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [cleanChoiceOpen, setCleanChoiceOpen] = useState(false);
  const [cleanChoiceOptions, setCleanChoiceOptions] = useState<SemanticCleanResumeOptions | null>(null);
  const [cleanChoicePending, setCleanChoicePending] = useState<{
    source: SourceItem;
    sourceId: number;
    sourceType: string;
    label: string;
  } | null>(null);
  const [cleanChoiceLoading, setCleanChoiceLoading] = useState(false);

  // ── Ontology cleaning results ──
  const [cleaningResults, setCleaningResults] = useState<OntologyCleaningResults | null>(null);
  const [, setCleaningResultsLoading] = useState(false);

  // ── Per-source cleaning stats ──
  const [cleaningStats, setCleaningStats] = useState<Record<string, SourceCleaningStat> | null>(null);

  // ═══════════════════════════════════════════════════
  // Data fetching
  // ═══════════════════════════════════════════════════

  const loadDocuments = useCallback(async () => {
    setDocsLoading(true);
    try {
      const res = await api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`);
      setDocuments(res.documents ?? []);
    } catch {
      setDocuments([]);
    } finally {
      setDocsLoading(false);
    }
  }, [kbId]);

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
      const dbRes = await api<{ imports: DatabaseImport[] }>(`/api/knowledge-bases/${kbId}/database-imports`).catch(() => ({ imports: [] }));
      setDatabaseImports(dbRes.imports ?? []);
      loadDocuments();
      loadCleaningResults();
      loadSourceCleaningStats();
      checkRunningPipeline();
    } catch {
      setKb(null); setEntries([]); setGitSources([]); setApiSources([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!documents.some((d) => isDocumentIndexingInProgress(d))) return;
    const t = setInterval(() => {
      void loadDocuments();
    }, 3000);
    return () => clearInterval(t);
  }, [documents, loadDocuments]);

  function checkRunningPipeline() {
    if (cleaningPollRef.current) return;

    api<{ last_pipeline_run: { id: number; status: string; source_id: number | null } | null }>(
      `/api/knowledge-bases/${kbId}/pipeline-stats`
    ).then(stats => {
      const run = stats.last_pipeline_run;
      if (run && run.status === "running") {
        // Restore cleaning source ID from the pipeline record (persisted in DB)
        if (run.source_id != null) setCleaningSourceId(run.source_id);
        startCleaningPoll(run.id);
      }
    }).catch(() => { /* ignore */ });
  }

  async function loadCleaningResults() {
    setCleaningResultsLoading(true);
    try {
      const res = await api<OntologyCleaningResults>(`/api/ontology/knowledge-bases/${kbId}/ontology-cleaning-results`);
      setCleaningResults(res);
    } catch {
      setCleaningResults(null);
    } finally {
      setCleaningResultsLoading(false);
    }
    loadSourceCleaningStats();
  }

  async function loadSourceCleaningStats() {
    try {
      const res = await api<{ ok: boolean; kb_id: number; stats: Record<string, SourceCleaningStat> }>(
        `/api/knowledge-bases/${kbId}/source-cleaning-stats`
      );
      setCleaningStats(res.stats ?? null);
    } catch {
      setCleaningStats(null);
    }
  }

  useEffect(() => { loadAll(); }, [kbId]);

  useEffect(() => {
    if (loading || !kb) return;
    const hash = typeof window !== "undefined" ? window.location.hash.slice(1) : "";
    if (hash) {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [loading, kb]);

  // Cleanup polling interval on unmount
  useEffect(() => {
    return () => {
      if (cleaningPollRef.current) clearInterval(cleaningPollRef.current);
    };
  }, [kbId]);

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
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "重试失败",
        "error",
      );
    }
  }

  async function manualIndexDocument(docId: number) {
    try {
      await api(`/api/knowledge-bases/${kbId}/documents/${docId}/manual-index`, { method: "POST" });
      notifyUser("已提交手动索引，正在后台处理", "success");
      loadDocuments();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "手动索引失败",
        "error",
      );
    }
  }

  // ── Semantic clean ──

  function clearCleaningState() {
    if (cleaningPollRef.current) clearInterval(cleaningPollRef.current);
    cleaningPollRef.current = null;
    setCleaningSourceId(null);
  }

  function startCleaningPoll(previousRunId: number | null) {
    if (cleaningPollRef.current) clearInterval(cleaningPollRef.current);

    const pollStart = Date.now();
    const MAX_POLL_MS = 10 * 60 * 1000;
    let seenRunning = false;

    cleaningPollRef.current = setInterval(async () => {
      try {
        const stats = await api<{ last_pipeline_run: { id: number; status: string } | null }>(
          `/api/knowledge-bases/${kbId}/pipeline-stats`
        );
        const run = stats.last_pipeline_run;

        // Track this run if: it's a new run, it's currently running, or we already confirmed it
        const isOurRun = run && (
          run.id !== previousRunId || run.status === "running" || seenRunning
        );

        if (!run || !isOurRun) {
          if (Date.now() - pollStart > 30000) {
            clearCleaningState();
            notifyUser("语义清洗可能未能启动，请重试", "error");
          }
          return;
        }

        if (run.status === "running") {
          seenRunning = true;
          void loadSourceCleaningStats();
          return;
        }

        if (seenRunning || Date.now() - pollStart > 6000) {
          clearCleaningState();
          loadCleaningResults();
          if (run.status === "failed") {
            notifyUser("语义清洗失败，请重试", "error");
          } else {
            notifyUser("语义清洗已完成", "success");
          }
          return;
        }
      } catch {
        // Keep polling on transient errors
      }

      if (Date.now() - pollStart > MAX_POLL_MS) {
        clearCleaningState();
        loadCleaningResults();
        notifyUser("语义清洗超时，请手动刷新查看结果", "error");
      }
    }, 3000);
  }

  function resolveSemanticCleanTarget(source: SourceItem): {
    sourceId: number;
    sourceType: string;
    label: string;
  } {
    if (source.kind === "git") {
      return { sourceId: source.data.id, sourceType: "git", label: source.data.name };
    }
    if (source.kind === "database") {
      return {
        sourceId: source.data.id,
        sourceType: "database",
        label: source.data.datasource_name || "数据库导入",
      };
    }
    if (source.kind === "api") {
      return { sourceId: source.data.id, sourceType: "api", label: source.data.name };
    }
    if (source.kind === "manual") {
      return { sourceId: source.entry.id, sourceType: "manual", label: source.entry.title };
    }
    const sourceType = source.kind === "api_entry" ? "api" : "file";
    return { sourceId: source.entry.id, sourceType, label: source.entry.title };
  }

  async function startSemanticClean(
    sourceId: number,
    sourceType: string,
    opts: { resume: boolean; resumeFromRunId?: number },
  ) {
    setCleaningSourceId(sourceId);
    notifyUser(opts.resume ? "正在从上次失败处续跑…" : "正在触发语义清洗（完整重跑）…", "info");
    try {
      let previousRunId: number | null = null;
      try {
        const stats = await api<{ last_pipeline_run: { id: number } | null }>(
          `/api/knowledge-bases/${kbId}/pipeline-stats`,
        );
        previousRunId = stats.last_pipeline_run?.id ?? null;
      } catch {
        /* proceed */
      }

      const params = new URLSearchParams({ source_type: sourceType });
      if (opts.resume) {
        params.set("resume", "true");
        if (opts.resumeFromRunId != null) {
          params.set("resume_from_run_id", String(opts.resumeFromRunId));
        }
      }
      await api(`/api/knowledge-bases/${kbId}/sources/${sourceId}/clean?${params.toString()}`, {
        method: "POST",
      });
      notifyUser(opts.resume ? "续跑已启动，正在后台运行…" : "语义清洗已触发，正在后台运行…", "success");
      void loadSourceCleaningStats();
      startCleaningPoll(previousRunId);
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "清洗启动失败",
        "error",
      );
      setCleaningSourceId(null);
    }
  }

  async function handleSemanticClean(source: SourceItem) {
    if (!canSemanticCleanSource(source)) {
      notifyUser(semanticCleanDisabledReason(source) ?? "文档尚未完成索引", "error");
      return;
    }

    const { sourceId, sourceType, label } = resolveSemanticCleanTarget(source);

    try {
      const options = await api<SemanticCleanResumeOptions & { ok?: boolean }>(
        `/api/knowledge-bases/${kbId}/sources/${sourceId}/clean-resume-options?source_type=${encodeURIComponent(sourceType)}`,
      );
      if (options.can_resume) {
        setCleanChoicePending({ source, sourceId, sourceType, label });
        setCleanChoiceOptions(options);
        setCleanChoiceOpen(true);
        return;
      }
    } catch {
      /* 无法查询续跑选项时仍允许完整重跑 */
    }

    await startSemanticClean(sourceId, sourceType, { resume: false });
  }

  async function confirmSemanticCleanChoice(mode: "resume" | "restart") {
    if (!cleanChoicePending) return;
    setCleanChoiceLoading(true);
    const { sourceId, sourceType } = cleanChoicePending;
    try {
      if (mode === "resume") {
        await startSemanticClean(sourceId, sourceType, {
          resume: true,
          resumeFromRunId: cleanChoiceOptions?.resume_from_run_id,
        });
      } else {
        await startSemanticClean(sourceId, sourceType, { resume: false });
      }
      setCleanChoiceOpen(false);
      setCleanChoicePending(null);
      setCleanChoiceOptions(null);
    } finally {
      setCleanChoiceLoading(false);
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
    if (source.kind === "database") return [];
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
      } else if (source.kind === "database") {
        // Database imports don't support tags yet
        return;
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
          { label: "语义知识库", href: "/knowledge-bases" },
          { label: kb?.name || "…" },
        ]}
        title={kb?.name || "语义知识库"}
        subtitle={kb?.description || "数据接入：登记证据包并在导入源上触发语义清洗。"}
        actions={
          <div className="app-toolbar flex-wrap">
            <Link
              href={kbModelingSectionUrl(kbId)}
              className="app-button-secondary app-toolbar-action no-underline"
            >
              建模与质量
            </Link>
            <Link
              href={ontologyUrl({ kbId })}
              className="app-button-secondary app-toolbar-action no-underline"
            >
              本体浏览
            </Link>
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
              数据接入
            </button>
          </div>
        }
      />

      <Toast message={message} tone={messageTone} duration={toastDurationMs} onClose={dismissToast} />

      {loading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {!loading && kb && (
        <>
          {/* Derive ontology counts from cleaning results layers */}
          {(() => {
            const layers = cleaningResults?.layers;
            const ontologyCounts: OntologyCounts | undefined = layers ? {
              entity: (layers.vocabulary?.total ?? 0) + (layers["entity-concept"]?.total ?? 0),
              relation: layers.relation?.total ?? 0,
            } : undefined;

            return (
              <div className="mt-6">
                <SourceCardGrid
                  gitSources={gitSources}
                  entries={entries}
                  documents={documents}
                  databaseImports={databaseImports}
                  kbId={kbId}
                  gitSyncingId={gitSyncingId}
                  onSyncGit={syncGitSourceNow}
                  onRetryDoc={retryDocument}
                  onManualIndexDoc={manualIndexDocument}
                  onRefresh={loadAll}
                  onAddTag={handleAddTag}
                  onRemoveTag={handleRemoveTag}
                  tagLoading={tagLoading}
                  onSemanticClean={handleSemanticClean}
                  cleaningSourceId={cleaningSourceId}
                  cleaningStats={cleaningStats}
                  ontologyCounts={ontologyCounts}
                />
              </div>
            );
          })()}

          <section className="mt-8 space-y-3">
            <h2 className="app-section-title">证据包登记</h2>
            <p className="text-xs text-app-muted">
              导入层统一视图：按语义资产类型与连接器登记的证据（写入 RDF 前仅作溯源与进度展示）。需推进建模时，请在上方对应导入源上点击「语义清洗」。
            </p>
            <EvidencePackageList kbId={kbId} cleaningStats={cleaningStats} />
          </section>

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

          <SemanticCleanChoiceDialog
            open={cleanChoiceOpen}
            sourceLabel={cleanChoicePending?.label ?? "导入源"}
            options={cleanChoiceOptions}
            loading={cleanChoiceLoading}
            onResume={() => void confirmSemanticCleanChoice("resume")}
            onRestart={() => void confirmSemanticCleanChoice("restart")}
            onCancel={() => {
              if (cleanChoiceLoading) return;
              setCleanChoiceOpen(false);
              setCleanChoicePending(null);
              setCleanChoiceOptions(null);
            }}
          />

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
