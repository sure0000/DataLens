"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { gitSourceValidationError } from "../../../lib/parseGitRepoUrl";
import ImportPickerModal from "../../../components/knowledge-bases/ImportPickerModal";
import EvidencePackageList from "../../../components/knowledge-bases/EvidencePackageList";
import { kbModelingSectionUrl } from "../../../lib/ontologyRoutes";
import type { SourceItem } from "../../../components/knowledge-bases/SourceCard";
import SourceCardGrid from "../../../components/knowledge-bases/SourceCardGrid";
import type { ModelingStatus } from "../../../components/ontology/ModelingPipelineStatus";
import {
  cleaningStatsRunningFingerprint,
  cleaningStatsSnapshotFingerprint,
  documentIndexingPollFingerprint,
  entriesDocumentsSnapshotFingerprint,
  modelingStatusFingerprint,
} from "../../../components/knowledge-bases/kbTaskActivity";
import { useBackgroundTaskPolling } from "../../../hooks/useBackgroundTaskPolling";
import {
  fetchKbEntriesAndDocuments,
  fetchKbSourcesSnapshot,
} from "../../../lib/knowledgeBaseSources";
import SemanticCleanChoiceDialog, {
  type SemanticCleanResumeOptions,
} from "../../../components/knowledge-bases/SemanticCleanChoiceDialog";
import { databaseImportDisplayTitle } from "../../../components/knowledge-bases/pipelineDisplay";
import { importSourceCleaningKey } from "../../../components/knowledge-bases/sourceCleaningKey";
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
  const [initialLoading, setInitialLoading] = useState(true);

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
  const [settingsSchemaSyncing, setSettingsSchemaSyncing] = useState(false);
  const settingsMenuRef = useRef<HTMLDivElement>(null);

  // ── Database imports ──
  const [databaseImports, setDatabaseImports] = useState<DatabaseImport[]>([]);

  // ── Semantic cleaning ──
  /** 当前清洗中的导入源键，形如 source:database:3（勿仅用数字 id，会与 git 等源冲突）。 */
  const [cleaningSourceKey, setCleaningSourceKey] = useState<string | null>(null);
  const cleaningSourceKeyRef = useRef<string | null>(null);
  const cleaningStatsRef = useRef<Record<string, SourceCleaningStat> | null>(null);
  const documentsRef = useRef(documents);
  documentsRef.current = documents;
  const [evidenceRefreshSeq, setEvidenceRefreshSeq] = useState(0);
  const entriesDocsFpRef = useRef("");
  const cleaningStatsFpRef = useRef("");
  const modelingFpRef = useRef("");
  /** 导入/清洗触发后强制轮询截止时间（ms），覆盖 pending 索引尚未进入 worker 态的窗口 */
  const [pollBurstDeadline, setPollBurstDeadline] = useState(0);
  const armPollBurst = useCallback(() => {
    setPollBurstDeadline(Date.now() + 15 * 60 * 1000);
  }, []);
  const [modelingStatus, setModelingStatus] = useState<ModelingStatus | null>(null);
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

  /** 轮询用：只更新条目与文档，不触发整页 loading */
  const refreshIndexingSnapshot = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    try {
      const { entries: nextEntries, documents: nextDocs } = await fetchKbEntriesAndDocuments(kbId);
      const fp = entriesDocumentsSnapshotFingerprint(nextEntries, nextDocs);
      if (fp === entriesDocsFpRef.current) return;
      entriesDocsFpRef.current = fp;
      setEntries(nextEntries);
      setDocuments(nextDocs);
    } catch {
      /* 轮询失败保留上一帧状态 */
    }
  }, [kbId]);

  const fetchSourceCleaningStats = useCallback(async () => {
    try {
      const res = await api<{ ok: boolean; kb_id: number; stats: Record<string, SourceCleaningStat> }>(
        `/api/knowledge-bases/${kbId}/source-cleaning-stats`,
      );
      const stats = res.stats ?? null;
      const fp = cleaningStatsSnapshotFingerprint(stats);
      if (fp !== cleaningStatsFpRef.current) {
        cleaningStatsFpRef.current = fp;
        setCleaningStats(stats);
      }
      cleaningStatsRef.current = stats;
      return stats;
    } catch {
      if (cleaningStatsFpRef.current !== "") {
        cleaningStatsFpRef.current = "";
        setCleaningStats(null);
      }
      cleaningStatsRef.current = null;
      return null;
    }
  }, [kbId]);

  const applySourcesSnapshot = useCallback((snap: Awaited<ReturnType<typeof fetchKbSourcesSnapshot>>) => {
    setKb(snap.kb);
    setGitSources(snap.gitSources);
    setApiSources(snap.apiSources);
    setDatabaseImports(snap.databaseImports);
    const fp = entriesDocumentsSnapshotFingerprint(snap.entries, snap.documents);
    entriesDocsFpRef.current = fp;
    setEntries(snap.entries);
    setDocuments(snap.documents);
  }, []);

  const refreshSources = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    try {
      const snap = await fetchKbSourcesSnapshot(kbId);
      applySourcesSnapshot(snap);
      await fetchSourceCleaningStats();
    } catch {
      setKb(null);
      setEntries([]);
      setGitSources([]);
      setApiSources([]);
    }
  }, [kbId, applySourcesSnapshot, fetchSourceCleaningStats]);

  async function checkRunningPipeline() {
    const stats = await fetchSourceCleaningStats();
    if (!stats) return;
    for (const [key, stat] of Object.entries(stats)) {
      if (stat.status === "running") {
        setCleaningSourceKey(key);
        return;
      }
    }
  }

  const loadCleaningResults = useCallback(async () => {
    setCleaningResultsLoading(true);
    try {
      const res = await api<OntologyCleaningResults>(`/api/ontology/knowledge-bases/${kbId}/ontology-cleaning-results`);
      setCleaningResults(res);
    } catch {
      setCleaningResults(null);
    } finally {
      setCleaningResultsLoading(false);
    }
  }, [kbId]);

  const refreshModelingSnapshot = useCallback(async () => {
    try {
      const res = await api<ModelingStatus>(
        `/api/ontology/knowledge-bases/${kbId}/modeling/status`,
      );
      const fp = modelingStatusFingerprint(res);
      if (fp !== modelingFpRef.current) {
        modelingFpRef.current = fp;
        setModelingStatus(res);
      }
    } catch {
      if (modelingFpRef.current !== "") {
        modelingFpRef.current = "";
        setModelingStatus(null);
      }
    }
  }, [kbId]);

  const loadInitial = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    setInitialLoading(true);
    try {
      await refreshSources();
      await loadCleaningResults();
      await refreshModelingSnapshot();
      await checkRunningPipeline();
    } finally {
      setInitialLoading(false);
    }
  }, [kbId, refreshSources, loadCleaningResults, refreshModelingSnapshot]);

  useEffect(() => { void loadInitial(); }, [loadInitial]);


  useEffect(() => {
    if (initialLoading || !kb) return;
    const hash = typeof window !== "undefined" ? window.location.hash.slice(1) : "";
    if (hash) {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [initialLoading, kb]);

  useEffect(() => {
    cleaningSourceKeyRef.current = cleaningSourceKey;
  }, [cleaningSourceKey]);

  const cleaningRunningFp = useMemo(
    () => cleaningStatsRunningFingerprint(cleaningStats),
    [cleaningStats],
  );
  const docsPollFp = useMemo(
    () => documentIndexingPollFingerprint(documents),
    [documents],
  );
  const tasksActive = useMemo(() => {
    if (Date.now() < pollBurstDeadline) return true;
    return cleaningRunningFp.length > 0 || docsPollFp.length > 0;
  }, [pollBurstDeadline, cleaningRunningFp, docsPollFp]);

  const pollBackgroundTasks = useCallback(async () => {
    const prev = cleaningStatsRef.current;
    if (documentIndexingPollFingerprint(documentsRef.current).length > 0) {
      await refreshIndexingSnapshot();
    }
    const stats = await fetchSourceCleaningStats();
    const cleaningRunning = cleaningStatsRunningFingerprint(stats).length > 0;
    if (cleaningRunning || Date.now() < pollBurstDeadline) {
      await refreshModelingSnapshot();
    }
    if (!stats) return;

    for (const [key, stat] of Object.entries(stats)) {
      if (stat.status === "running") {
        setCleaningSourceKey((cur) => cur ?? key);
      }
      const wasRunning = prev?.[key]?.status === "running";
      const now = stat.status;
      if (wasRunning && now && now !== "running") {
        void loadCleaningResults();
        setEvidenceRefreshSeq((n) => n + 1);
        if (cleaningSourceKeyRef.current === key) {
          clearCleaningState();
          if (now === "failed") {
            const reason = (stat.message || stat.failure_reason || "").trim();
            notifyUser(
              reason ? `语义清洗失败：${reason}` : "语义清洗失败，请重试",
              "error",
            );
          } else if (now === "completed") {
            notifyUser("语义清洗已完成", "success");
          }
        }
      }
    }
  }, [
    refreshIndexingSnapshot,
    fetchSourceCleaningStats,
    refreshModelingSnapshot,
    loadCleaningResults,
    notifyUser,
    pollBurstDeadline,
  ]);

  useBackgroundTaskPolling({
    tasksActive: Number.isFinite(kbId) && tasksActive,
    onTick: pollBackgroundTasks,
    onTasksCompleted: () => {
      setPollBurstDeadline(0);
      setEvidenceRefreshSeq((n) => n + 1);
      void loadCleaningResults();
      void refreshModelingSnapshot();
      if (cleaningSourceKeyRef.current) {
        clearCleaningState();
      }
    },
  });

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

  // ── Semantic clean ──

  function clearCleaningState() {
    setCleaningSourceKey(null);
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
        label: databaseImportDisplayTitle(source.data),
      };
    }
    if (source.kind === "api") {
      return { sourceId: source.data.id, sourceType: "api", label: source.data.name };
    }
    if (source.kind === "manual") {
      return { sourceId: source.entry.id, sourceType: "manual", label: source.entry.title };
    }
    if (source.kind === "api_entry") {
      const rawApiSourceId =
        typeof source.entry.source_meta?.api_source_id === "string" ||
        typeof source.entry.source_meta?.api_source_id === "number"
          ? Number(source.entry.source_meta?.api_source_id)
          : NaN;
      if (Number.isFinite(rawApiSourceId) && rawApiSourceId > 0) {
        return { sourceId: rawApiSourceId, sourceType: "api", label: source.entry.title };
      }
      return { sourceId: source.entry.id, sourceType: "file", label: source.entry.title };
    }
    return { sourceId: source.entry.id, sourceType: "file", label: source.entry.title };
  }

  function cleaningKeyForSourceType(sourceType: string, sourceId: number): string {
    const kind =
      sourceType === "api_entry"
        ? "api_entry"
        : (sourceType as "git" | "api" | "database" | "file" | "manual");
    return importSourceCleaningKey(kind, sourceId);
  }

  async function startSemanticClean(
    sourceId: number,
    sourceType: string,
    opts: { resume: boolean; resumeFromRunId?: number },
  ) {
    const isDatabase = sourceType === "database";
    setCleaningSourceKey(cleaningKeyForSourceType(sourceType, sourceId));
    armPollBurst();
    notifyUser(
      opts.resume
        ? "正在从上次失败处续跑…"
        : isDatabase
          ? "正在触发语义清洗（表结构入本体）…"
          : "正在触发语义清洗（完整重跑）…",
      "info",
    );
    try {
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
      notifyUser(
        opts.resume
          ? "续跑已启动，正在后台运行…"
          : isDatabase
            ? "语义清洗已启动，可在「建模与质量 → 五层结果 → 属性层」查看进度"
            : "语义清洗已触发，正在后台运行…",
        "success",
      );
      void fetchSourceCleaningStats();
      void refreshModelingSnapshot();
      void loadCleaningResults();
      setEvidenceRefreshSeq((n) => n + 1);
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError
          ? formatApiError(e)
          : e instanceof Error
            ? e.message
            : isDatabase
              ? "语义清洗启动失败"
              : "清洗启动失败",
        "error",
      );
      setCleaningSourceKey(null);
    }
  }

  async function syncAllDatabaseSchemasFromSettings() {
    if (databaseImports.length === 0) {
      notifyUser("暂无数据库导入源，请先通过「导入数据」接入数据源", "info");
      return;
    }
    setSettingsSchemaSyncing(true);
    setSettingsMenuOpen(false);
    armPollBurst();
    notifyUser(
      databaseImports.length > 1
        ? `正在为 ${databaseImports.length} 个数据库源触发语义清洗…`
        : "正在触发语义清洗（表结构入本体）…",
      "info",
    );
    try {
      for (const di of databaseImports) {
        setCleaningSourceKey(importSourceCleaningKey("database", di.id));
        await api(
          `/api/knowledge-bases/${kbId}/sources/${di.id}/clean?source_type=database`,
          { method: "POST" },
        );
      }
      notifyUser(
        "语义清洗已启动，可在「建模与质量 → 五层结果 → 属性层」查看进度",
        "success",
      );
      void fetchSourceCleaningStats();
      void refreshModelingSnapshot();
      void loadCleaningResults();
      setEvidenceRefreshSeq((n) => n + 1);
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "语义清洗启动失败",
        "error",
      );
      setCleaningSourceKey(null);
    } finally {
      setSettingsSchemaSyncing(false);
    }
  }

  async function handleSemanticClean(source: SourceItem) {
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
      enableDocumentIndexing: !!s.enable_document_indexing,
      extractionProfile:
        s.extraction_config?.extraction_profile === "data_warehouse" ? "data_warehouse" : "mixed",
      cron: s.cron_expression ?? "",
      enabled: s.enabled,
    });
    setGitEditOpen(true);
  }

  async function saveGitEdit() {
    const validationError = gitSourceValidationError(gitFormData, { isEditing: true });
    if (validationError) {
      notifyUser(validationError);
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
        enable_document_indexing: gitFormData.enableDocumentIndexing,
        extraction_config: {
          extraction_profile: gitFormData.extractionProfile,
          enable_regex_extractors: true,
          enable_llm_fallback: true,
          min_body_chars: 50,
        },
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
      void refreshSources();
      setEvidenceRefreshSeq((n) => n + 1);
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
    const res = await api<{ knowledge_base: KB }>(`/api/knowledge-bases/${kbId}`);
    setKb(res.knowledge_base);
  }

  // ═══════════════════════════════════════════════════
  // Render guards
  // ═══════════════════════════════════════════════════

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  if (!initialLoading && !kb) {
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
          { label: "本体知识库", href: "/knowledge-bases" },
          { label: kb?.name || "…" },
        ]}
        title={kb?.name || "本体知识库"}
        subtitle={kb?.description || "本体知识库：登记证据包并在导入源上触发语义清洗。"}
        actions={
          <div className="app-toolbar flex-wrap">
            <Link
              href={kbModelingSectionUrl(kbId)}
              className="app-button-secondary app-toolbar-action no-underline"
            >
              建模与质量
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
                <div className="absolute right-0 top-full mt-1 z-50 min-w-[200px] rounded-lg border border-[var(--app-border)] bg-[var(--app-surface)] py-1 shadow-lg">
                  {databaseImports.length > 0 && (
                    <>
                      <button
                        className="block w-full px-4 py-2 text-left text-sm text-[var(--app-text-primary)] hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                        type="button"
                        disabled={settingsSchemaSyncing || cleaningSourceKey != null}
                        title={
                          databaseImports.length > 1
                            ? `为 ${databaseImports.length} 个数据库导入源触发语义清洗（表结构入本体）`
                            : "将已分析表结构与字段语义写入本体属性层"
                        }
                        onClick={() => void syncAllDatabaseSchemasFromSettings()}
                      >
                        {settingsSchemaSyncing ? "清洗中…" : "语义清洗"}
                      </button>
                      <div className="my-1 border-t border-[var(--app-border)]" role="separator" />
                    </>
                  )}
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
              导入数据
            </button>
          </div>
        }
      />

      <Toast message={message} tone={messageTone} duration={toastDurationMs} onClose={dismissToast} />

      {initialLoading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {kb && (
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
                  apiSources={apiSources}
                  entries={entries}
                  documents={documents}
                  databaseImports={databaseImports}
                  kbId={kbId}
                  onRefresh={() => void refreshSources()}
                  onSemanticClean={handleSemanticClean}
                  cleaningSourceKey={cleaningSourceKey}
                  cleaningStats={cleaningStats}
                  ontologyCounts={ontologyCounts}
                />
              </div>
            );
          })()}

          <section className="mt-8 space-y-3">
            <h2 className="app-section-title">证据包登记</h2>
            <p className="text-xs text-app-muted">
              导入层统一视图：按连接器/导入源自动登记，仅作溯源与进度展示。数据库源可在右上角「设置 → 语义清洗」或源卡片按钮触发入图。
            </p>
            <EvidencePackageList
              kbId={kbId}
              cleaningStats={cleaningStats}
              documents={documents}
              modeling={modelingStatus}
              refreshSeq={evidenceRefreshSeq}
            />
          </section>

          {/* ── Modals ── */}
          <ImportPickerModal
            open={importPickerOpen}
            kbId={kbId}
            apiSources={apiSources}
            onClose={() => setImportPickerOpen(false)}
            onSuccess={async (opts) => {
              armPollBurst();
              if (opts?.databaseImportId != null) {
                setCleaningSourceKey(
                  importSourceCleaningKey("database", opts.databaseImportId),
                );
              }
              try {
                const snap = await fetchKbSourcesSnapshot(kbId);
                applySourcesSnapshot(snap);
              } catch {
                /* 保留上一帧 */
              }
              void fetchSourceCleaningStats();
              void refreshModelingSnapshot();
              setEvidenceRefreshSeq((n) => n + 1);
            }}
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
