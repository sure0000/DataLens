"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConfirmDialog from "../../../../../components/ConfirmDialog";
import PageHeader from "../../../../../components/PageHeader";
import Toast from "../../../../../components/Toast";
import { api, ApiError, formatApiError } from "../../../../../lib/api";
import {
  docMatchesApiSource,
  entryMatchesApiSource,
} from "../../../../../components/knowledge-bases/apiSourceMatching";

import type {
  ApiSource,
  ChunkRow,
  DatabaseImport,
  DatabaseTableNode,
  DocRow,
  Entry,
  GitSource,
  KB,
} from "../../../../../components/knowledge-bases/types";

import { linkAccent } from "../../../../../lib/themeClasses";
import {
  canManualDocumentIndex,
  canRetryDocumentIndex,
} from "../../../../../components/knowledge-bases/documentIndexPolicy";
import {
  documentWorkerActiveFingerprint,
  entriesDocumentsSnapshotFingerprint,
} from "../../../../../components/knowledge-bases/kbTaskActivity";
import {
  useBackgroundTaskPolling,
  useTaskActivityFlag,
} from "../../../../../hooks/useBackgroundTaskPolling";
import {
  fetchKbEntriesAndDocuments,
  fetchKbSourcesSnapshot,
} from "../../../../../lib/knowledgeBaseSources";
import CodeEditorView from "../../../../../components/CodeEditorView";
import GitSourceFileTree from "../../../../../components/knowledge-bases/GitSourceFileTree";
import {
  databaseImportDisplaySubtitle,
  databaseImportDisplayTitle,
} from "../../../../../components/knowledge-bases/pipelineDisplay";
import { docStatusChip, gitSyncStatusChip } from "../../../../../components/knowledge-bases/utils";

export default function SourceDetailPage({
  params,
  searchParams,
}: {
  params: { id: string; sourceId: string };
  searchParams: { type?: string };
}) {
  const router = useRouter();
  const kbId = Number(params.id);
  const sourceId = Number(params.sourceId);
  const sourceType = searchParams.type || "git";

  // ── Core data ──
  const [kb, setKb] = useState<KB | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [gitSources, setGitSources] = useState<GitSource[]>([]);
  const [apiSources, setApiSources] = useState<ApiSource[]>([]);
  const [documents, setDocuments] = useState<DocRow[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);

  // ── Database import detail ──
  const [dbImport, setDbImport] = useState<DatabaseImport | null>(null);
  const [dbTables, setDbTables] = useState<DatabaseTableNode[]>([]);
  const [dbDetailLoading, setDbDetailLoading] = useState(false);

  // ── Chunks: auto-loaded for all source documents ──
  const [docChunks, setDocChunks] = useState<Record<number, ChunkRow[]>>({});
  const [chunksLoading, setChunksLoading] = useState(false);

  // ── Settings menu ──
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const settingsMenuRef = useRef<HTMLDivElement>(null);

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
  const [settingsActionLoading, setSettingsActionLoading] = useState(false);
  const [gitSyncing, setGitSyncing] = useState(false);
  const [dbSchemaSyncing, setDbSchemaSyncing] = useState(false);

  // ── Git 文件树选中 ──
  const [selectedGitPath, setSelectedGitPath] = useState<string | null>(null);
  const [selectedGitEntry, setSelectedGitEntry] = useState<Entry | null>(null);
  const entriesDocsFpRef = useRef("");

  // ── Toast ──
  const [message, setMessageText] = useState("");
  const [messageTone, setMessageTone] = useState<"success" | "error" | "info">("success");
  const [toastDurationMs, setToastDurationMs] = useState(4000);

  const notifyUser = useCallback(
    (msg: string, tone: "success" | "error" | "info" = "success") => {
      setMessageText(msg);
      if (!msg) { setMessageTone("success"); setToastDurationMs(4000); return; }
      setMessageTone(tone);
      setToastDurationMs(tone === "info" ? 14000 : tone === "error" ? 9000 : 4000);
    },
    [],
  );
  const dismissToast = useCallback(() => {
    setMessageText(""); setMessageTone("success"); setToastDurationMs(4000);
  }, []);

  // ═══════════════════════════════════════════════════
  // Data fetching
  // ═══════════════════════════════════════════════════

  const loadDatabaseDetail = useCallback(async () => {
    setDbDetailLoading(true);
    try {
      const res = await api<{ import: DatabaseImport; tables: DatabaseTableNode[] }>(
        `/api/knowledge-bases/${kbId}/database-imports/${sourceId}`,
      );
      setDbImport(res.import);
      setDbTables(res.tables ?? []);
    } catch {
      setDbImport(null);
      setDbTables([]);
    } finally {
      setDbDetailLoading(false);
    }
  }, [kbId, sourceId]);

  const applySourcesSnapshot = useCallback(
    (snap: Awaited<ReturnType<typeof fetchKbSourcesSnapshot>>) => {
      setKb(snap.kb);
      setGitSources(snap.gitSources);
      setApiSources(snap.apiSources);
      const fp = entriesDocumentsSnapshotFingerprint(snap.entries, snap.documents);
      entriesDocsFpRef.current = fp;
      setEntries(snap.entries);
      setDocuments(snap.documents);
    },
    [],
  );

  const refreshSources = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    try {
      const snap = await fetchKbSourcesSnapshot(kbId);
      applySourcesSnapshot(snap);
      if (sourceType === "database") {
        await loadDatabaseDetail();
      }
    } catch {
      setKb(null);
      setEntries([]);
      setGitSources([]);
    }
  }, [kbId, sourceType, applySourcesSnapshot, loadDatabaseDetail]);

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
      /* 轮询失败保留上一帧 */
    }
  }, [kbId]);

  const loadInitial = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    setInitialLoading(true);
    try {
      await refreshSources();
    } finally {
      setInitialLoading(false);
    }
  }, [kbId, refreshSources]);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

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

  // ═══════════════════════════════════════════════════
  // Delete source
  // ═══════════════════════════════════════════════════

  function confirmDeleteSource() {
    const name = sourceTitle;
    setConfirmState({
      title: `确认删除「${name}」？`,
      description: `此操作不可恢复。请输入名称「${name}」以确认删除。`,
      confirmText: "删除",
      confirmName: name,
      danger: true,
      action: async () => {
        if (sourceType === "git" && gitSource) {
          await api(`/api/knowledge-bases/${kbId}/git-sources/${sourceId}`, { method: "DELETE" });
        } else if (sourceType === "database") {
          await api(`/api/knowledge-bases/${kbId}/database-imports/${sourceId}`, { method: "DELETE" });
        } else if (sourceType === "api") {
          if (apiSource) {
            const apiDeleteUrl =
              apiSource.knowledge_base_id != null
                ? `/api/knowledge-bases/${kbId}/api-sources/${sourceId}`
                : `/api/api-sources/${sourceId}`;
            await api(apiDeleteUrl, { method: "DELETE" });
          } else {
            await api(`/api/knowledge-bases/${kbId}/entries/${sourceId}`, { method: "DELETE" });
          }
        } else {
          await api(`/api/knowledge-bases/${kbId}/entries/${sourceId}`, { method: "DELETE" });
        }
        router.push(`/knowledge-bases/${kbId}`);
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
  // Chunk loading
  // ═══════════════════════════════════════════════════

  async function loadAllChunks(docs: DocRow[]) {
    if (docs.length === 0) { setDocChunks({}); return; }
    setChunksLoading(true);
    const pairs = await Promise.all(
      docs.map(async (doc): Promise<[number, ChunkRow[]]> => {
        try {
          const res = await api<{ chunks: ChunkRow[] }>(`/api/knowledge-bases/${kbId}/documents/${doc.id}/chunks`);
          return [doc.id, res.chunks ?? []];
        } catch {
          return [doc.id, []];
        }
      }),
    );
    const map: Record<number, ChunkRow[]> = Object.fromEntries(pairs);
    setDocChunks(map);
    setChunksLoading(false);
  }

  // ═══════════════════════════════════════════════════
  // Filtering helpers
  // ═══════════════════════════════════════════════════

  const apiSource = sourceType === "api" ? apiSources.find((s) => s.id === sourceId) : null;

  function isSourceEntry(e: Entry): boolean {
    const meta = e.source_meta || {};
    if (sourceType === "git") {
      return meta.kind === "git_file" && String(meta.git_source_id) === String(sourceId);
    }
    if (sourceType === "api") {
      if (apiSource) return entryMatchesApiSource(e, apiSource);
      return e.id === sourceId;
    }
    if (sourceType === "file" || sourceType === "manual") {
      return e.id === sourceId;
    }
    return false;
  }

  const sourceEntries = entries.filter(isSourceEntry);
  const linkedEntryIds = new Set(sourceEntries.map((e) => e.id));

  function isSourceDoc(d: DocRow): boolean {
    const meta = d.source_meta || {};
    if (sourceType === "git") {
      return meta.kind === "git_file" && String(meta.git_source_id) === String(sourceId);
    }
    if (sourceType === "api") {
      if (apiSource) return docMatchesApiSource(d, apiSource, linkedEntryIds);
      return d.knowledge_entry_id === sourceId || d.id === sourceId;
    }
    if (sourceType === "file" || sourceType === "manual") {
      return d.knowledge_entry_id === sourceId || d.id === sourceId;
    }
    return false;
  }

  const sourceDocs = documents.filter(isSourceDoc);
  const primaryDoc = sourceDocs[0] ?? null;

  async function retryDocumentIndex(docId: number) {
    try {
      await api(`/api/knowledge-bases/${kbId}/documents/${docId}/retry`, { method: "POST" });
      notifyUser("已重新提交索引", "success");
      await refreshIndexingSnapshot();
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "重试失败", "error");
    }
  }

  async function manualDocumentIndex(docId: number) {
    try {
      await api(`/api/knowledge-bases/${kbId}/documents/${docId}/manual-index`, { method: "POST" });
      notifyUser("已提交手动索引", "success");
      await refreshIndexingSnapshot();
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "手动索引失败", "error");
    }
  }

  async function syncGitSource() {
    if (!gitSource) return;
    setGitSyncing(true);
    setSettingsActionLoading(true);
    notifyUser("正在从 GitHub/GitLab 拉取文件，可能需要几十秒至数分钟…", "info");
    try {
      const res = await api<{ ok?: boolean; message?: string; files?: number }>(
        `/api/knowledge-bases/${kbId}/git-sources/${gitSource.id}/sync`,
        { method: "POST" },
      );
      notifyUser(res.message || `同步完成，处理 ${res.files ?? 0} 个文件`, "success");
      await refreshSources();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "同步失败",
        "error",
      );
    } finally {
      setGitSyncing(false);
      setSettingsActionLoading(false);
      setSettingsMenuOpen(false);
    }
  }

  async function reindexGitSourceEntries() {
    if (!gitSource) return;
    setSettingsActionLoading(true);
    notifyUser("正在为已有文件条目重建文档索引…", "info");
    try {
      const res = await api<{ ok?: boolean; queued?: number; skipped?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/git-sources/${gitSource.id}/reindex-entries`,
        { method: "POST" },
      );
      const msg = res.message
        || `已排队 ${res.queued ?? 0} 个条目重新索引${(res.skipped ?? 0) > 0 ? `（跳过 ${res.skipped}）` : ""}`;
      notifyUser(msg, "success");
      await refreshIndexingSnapshot();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "重新索引失败",
        "error",
      );
    } finally {
      setSettingsActionLoading(false);
      setSettingsMenuOpen(false);
    }
  }

  async function reimportApiSource() {
    if (!apiSource) return;
    setSettingsActionLoading(true);
    notifyUser("正在从 Notion/API 重新拉取内容…", "info");
    try {
      const oid = (apiSource.object_id || "").trim()
        || String(sourceEntries[0]?.source_meta?.ref || "").trim();
      const res = await api<{ ok?: boolean; entries_created?: number }>(
        `/api/knowledge-bases/${kbId}/api-sources/${apiSource.id}/import`,
        {
          method: "POST",
          body: JSON.stringify(oid ? { object_id: oid } : {}),
        },
      );
      notifyUser(`重新导入已启动，新增 ${res.entries_created ?? 0} 个条目`, "success");
      await refreshSources();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "重新导入失败",
        "error",
      );
    } finally {
      setSettingsActionLoading(false);
      setSettingsMenuOpen(false);
    }
  }

  async function syncDatabaseSchema() {
    if (sourceType !== "database" || !Number.isFinite(sourceId)) return;
    setDbSchemaSyncing(true);
    notifyUser("正在触发语义清洗（表结构入本体）…", "info");
    try {
      await api(
        `/api/knowledge-bases/${kbId}/sources/${sourceId}/clean?source_type=database`,
        { method: "POST" },
      );
      notifyUser("语义清洗已启动，可在「建模与质量 → 五层结果 → 属性层」查看", "success");
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "语义清洗失败",
        "error",
      );
    } finally {
      setDbSchemaSyncing(false);
      setSettingsMenuOpen(false);
    }
  }

  async function reindexApiSourceEntries() {
    if (!apiSource) return;
    setSettingsActionLoading(true);
    notifyUser("正在为已有条目重新索引…", "info");
    try {
      const res = await api<{ ok?: boolean; queued?: number; skipped?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/api-sources/${apiSource.id}/reindex-entries`,
        { method: "POST" },
      );
      const msg = res.message
        || `已排队 ${res.queued ?? 0} 个条目重新索引${(res.skipped ?? 0) > 0 ? `（跳过 ${res.skipped}）` : ""}`;
      notifyUser(msg, "success");
      await refreshIndexingSnapshot();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "重新索引失败",
        "error",
      );
    } finally {
      setSettingsActionLoading(false);
      setSettingsMenuOpen(false);
    }
  }

  const gitSelectedDoc = selectedGitEntry
    ? sourceDocs.find((d) => d.knowledge_entry_id === selectedGitEntry.id) ?? null
    : null;

  const sourceDocsWorkerFp = useMemo(
    () => documentWorkerActiveFingerprint(sourceDocs),
    [sourceDocs],
  );
  const sourceTasksActive = useTaskActivityFlag("", sourceDocsWorkerFp);
  const gitSelectedDocRef = useRef(gitSelectedDoc);
  gitSelectedDocRef.current = gitSelectedDoc;

  useBackgroundTaskPolling({
    tasksActive: sourceTasksActive,
    onTick: refreshIndexingSnapshot,
    onTasksCompleted: () => {
      const doc = gitSelectedDocRef.current;
      if (doc) void loadAllChunks([doc]);
    },
  });

  // 默认选中第一个 Git 文件
  useEffect(() => {
    if (sourceType !== "git" || sourceEntries.length === 0) return;
    if (selectedGitPath) return;
    const first = sourceEntries.find((e) => e.source_meta?.ref);
    if (first?.source_meta?.ref) {
      setSelectedGitPath(first.source_meta.ref);
      setSelectedGitEntry(first);
    }
  }, [sourceType, sourceEntries, selectedGitPath]);

  // 加载分块：Git 仅加载选中文件；其他源加载全部
  useEffect(() => {
    if (sourceType === "git") {
      if (gitSelectedDoc) void loadAllChunks([gitSelectedDoc]);
      else setDocChunks({});
      return;
    }
    loadAllChunks(sourceDocs);
  }, [documents, sourceType, apiSource, gitSelectedDoc?.id, sourceDocs.length]);

  // Source config
  const gitSource = sourceType === "git" ? gitSources.find((s) => s.id === sourceId) : null;
  const gitIndexingEnabled = !!gitSource?.enable_document_indexing;

  // Compute title and subtitle
  let sourceTitle: string;
  let sourceSubtitle: string;
  let statusChip: { text: string; className: string } | null = null;

  if (sourceType === "git" && gitSource) {
    sourceTitle = gitSource.name;
    sourceSubtitle = `${gitSource.provider === "gitlab" ? "GitLab" : "GitHub"} · ${gitSource.owner}/${gitSource.repo}`;
    statusChip = gitSyncStatusChip(gitSource.last_sync_status);
  } else if (sourceType === "database") {
    sourceTitle = dbImport ? databaseImportDisplayTitle(dbImport) : "数据库导入";
    sourceSubtitle = dbImport ? databaseImportDisplaySubtitle(dbImport) : "";
  } else if (sourceType === "api") {
    if (apiSource) {
      const integrationLabel =
        apiSource.integration === "notion" ? "Notion" :
        apiSource.integration === "confluence" ? "Confluence" :
        apiSource.integration === "feishu" ? "飞书" : apiSource.integration;
      sourceTitle = apiSource.name;
      sourceSubtitle = `${integrationLabel} · ${apiSource.object_id}`;
      statusChip = gitSyncStatusChip(apiSource.last_sync_status);
    } else {
      const entry = entries.find((e) => e.id === sourceId);
      const sourceEntries = entries.filter(isSourceEntry);
      const e = entry || sourceEntries[0];
      sourceTitle = e?.title || "API 导入";
      const metaKind = e?.source_meta?.kind || "";
      const integrationLabel =
        metaKind === "notion_api" ? "Notion" :
        metaKind === "confluence_api" ? "Confluence" :
        metaKind === "feishu_api" ? "飞书" : metaKind.replace("_api", "");
      sourceSubtitle = `${integrationLabel} · ${e?.source_meta?.ref || e?.source_meta?.label || "导入"}`;
      const doc = sourceDocs[0];
      if (doc) statusChip = docStatusChip(doc.status);
    }
  } else if (sourceType === "file" || sourceType === "manual") {
    const entry = entries.find((e) => e.id === sourceId);
    sourceTitle = entry?.title || (sourceType === "manual" ? "手动条目" : "文件");
    const label = entry?.source_meta?.label;
    sourceSubtitle = sourceType === "manual"
      ? "手动条目"
      : (label && label !== "上传文件") ? label : (entry?.source_meta?.ref || entry?.source_meta?.kind || "文件");
    const doc = sourceDocs[0];
    if (doc) statusChip = docStatusChip(doc.status);
  } else {
    sourceTitle = "未知源";
    sourceSubtitle = "";
  }

  // ═══════════════════════════════════════════════════
  // Render guards
  // ═══════════════════════════════════════════════════

  if (!Number.isFinite(kbId) || !Number.isFinite(sourceId)) {
    return <main className="app-page text-app-secondary">无效的参数</main>;
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
          { label: kb?.name || "…", href: `/knowledge-bases/${kbId}` },
          { label: sourceTitle },
        ]}
        title={sourceTitle}
        subtitle={sourceSubtitle}
        actions={
          <div className="app-toolbar flex-wrap">
            {statusChip && (
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${statusChip.className}`}
              >
                {statusChip.text}
              </span>
            )}
            <div className="relative" ref={settingsMenuRef}>
              <button
                className="app-button-secondary app-toolbar-action"
                type="button"
                onClick={() => setSettingsMenuOpen((v) => !v)}
              >
                设置
              </button>
              {settingsMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-50 min-w-[180px] rounded-lg border border-[var(--app-border)] bg-[var(--app-surface)] py-1 shadow-lg">
                  {sourceType === "git" && gitSource && (
                    <>
                      <button
                        className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                        type="button"
                        disabled={settingsActionLoading || gitSyncing}
                        onClick={() => void syncGitSource()}
                      >
                        {gitSyncing ? "同步中…" : "同步仓库"}
                      </button>
                      <button
                        className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                        type="button"
                        disabled={settingsActionLoading || gitSyncing || sourceEntries.length === 0 || !gitIndexingEnabled}
                        title={
                          !gitIndexingEnabled
                            ? "当前代码源未启用文档索引"
                            : sourceEntries.length === 0
                              ? "暂无已同步文件"
                              : "从已有文件条目正文生成分块，不重新拉取仓库"
                        }
                        onClick={() => void reindexGitSourceEntries()}
                      >
                        重新索引
                      </button>
                    </>
                  )}
                  {sourceType === "api" && apiSource && (
                    <>
                      <button
                        className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                        type="button"
                        disabled={settingsActionLoading}
                        onClick={() => void reimportApiSource()}
                      >
                        {settingsActionLoading ? "处理中…" : "重新导入"}
                      </button>
                      <button
                        className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                        type="button"
                        disabled={settingsActionLoading || sourceEntries.length === 0}
                        title={sourceEntries.length === 0 ? "暂无关联条目" : "从已有条目正文生成分块，不重新请求 Notion"}
                        onClick={() => void reindexApiSourceEntries()}
                      >
                        重新索引
                      </button>
                    </>
                  )}
                  {sourceType === "database" && dbImport && (
                    <button
                      className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                      type="button"
                      disabled={dbSchemaSyncing}
                      title="将已分析表结构与字段语义写入本体属性层"
                      onClick={() => void syncDatabaseSchema()}
                    >
                      {dbSchemaSyncing ? "清洗中…" : "语义清洗"}
                    </button>
                  )}
                  {(() => {
                    if (sourceType === "git") return null;
                    const docForIndex = sourceType === "git" ? gitSelectedDoc : primaryDoc;
                    if (!docForIndex) return null;
                    return (
                      <>
                        {canRetryDocumentIndex(docForIndex) && (
                          <button
                            className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)]"
                            type="button"
                            onClick={() => {
                              setSettingsMenuOpen(false);
                              void retryDocumentIndex(docForIndex.id);
                            }}
                          >
                            {docForIndex.status === "pending" ? "开始索引" : "重试索引"}
                          </button>
                        )}
                        {canManualDocumentIndex(docForIndex) && (
                          <button
                            className="block w-full px-4 py-2 text-left text-sm hover:bg-[var(--app-bg-hover)]"
                            type="button"
                            onClick={() => {
                              setSettingsMenuOpen(false);
                              void manualDocumentIndex(docForIndex.id);
                            }}
                          >
                            手动索引
                          </button>
                        )}
                      </>
                    );
                  })()}
                  <div className="my-1 border-t border-[var(--app-border)]" role="separator" />
                  <button
                    className="block w-full px-4 py-2 text-left text-sm text-[var(--app-text-danger)] hover:bg-[var(--app-bg-hover)]"
                    type="button"
                    onClick={() => { setSettingsMenuOpen(false); confirmDeleteSource(); }}
                  >
                    删除
                  </button>
                </div>
              )}
            </div>
          </div>
        }
      />

      <Toast message={message} tone={messageTone} duration={toastDurationMs} onClose={dismissToast} />

      {initialLoading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {kb && (
        <>
          {/* ── Source config info ── */}
          {sourceType === "api" && apiSource && (
            <div className="app-card p-4 mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-app-muted">
              <span>
                类型：{apiSource.integration === "notion" ? "Notion" : apiSource.integration === "confluence" ? "Confluence" : apiSource.integration === "feishu" ? "飞书" : apiSource.integration}
              </span>
              <span>对象 ID：{apiSource.object_id || "（未配置，将使用已导入条目的 ref）"}</span>
              <span>关联条目：{sourceEntries.length}</span>
              {apiSource.last_sync_at && (
                <span>上次导入：{new Date(apiSource.last_sync_at).toLocaleString()}</span>
              )}
              {apiSource.last_error && (
                <span className="app-text-danger">错误：{apiSource.last_error}</span>
              )}
            </div>
          )}

          {sourceType === "git" && gitSource && (
            <div className="app-card p-4 mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-app-muted">
              <span>分支：{gitSource.uses_default_branch || !gitSource.branch ? "默认分支" : gitSource.branch}</span>
              {gitSource.path_prefix && <span>路径：{gitSource.path_prefix}</span>}
              <span>限制：{gitSource.max_files} 文件 / {gitSource.max_file_kb} KB</span>
              <span>文档索引：{gitIndexingEnabled ? "已启用" : "未启用（仅解析）"}</span>
              {gitSource.cron_expression && <span>定时：{gitSource.cron_expression}</span>}
              {gitSource.last_sync_at && <span>上次同步：{new Date(gitSource.last_sync_at).toLocaleString()}</span>}
              {gitSource.last_error && (
                <span className="app-text-danger">错误：{gitSource.last_error}</span>
              )}
            </div>
          )}

          {/* ── Database: table list ── */}
          {sourceType === "database" && (
            <section className="mt-6">
              <h2 className="app-section-title mb-3">数据表</h2>
              {dbDetailLoading && <p className="text-sm text-app-muted">加载中…</p>}
              {!dbDetailLoading && dbTables.length === 0 && (
                <p className="text-sm text-app-muted">此数据库导入暂无表数据，请先在数据源中分析表。</p>
              )}
              {!dbDetailLoading && dbTables.length > 0 && (
                <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
                  <table className="app-table">
                    <thead>
                      <tr>
                        <th className="px-3 py-2.5">表名</th>
                        <th className="px-3 py-2.5">数据库</th>
                        <th className="w-28 px-3 py-2.5">状态</th>
                        <th className="px-3 py-2.5">表描述</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dbTables.map((t) => (
                        <tr key={`tbl-${t.id}`} className="hover:bg-app-hover">
                          <td className="px-3 py-2.5">
                            <Link
                              href={`/table/${t.id}`}
                              className={`text-sm font-medium ${linkAccent}`}
                            >
                              {t.table_name}
                            </Link>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-app-muted">{t.database_name}</td>
                          <td className="px-3 py-2.5">
                            <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${
                              t.status === "done" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                              t.status === "analyzing" ? "bg-amber-50 text-amber-700 border-amber-200" :
                              t.status === "error" ? "bg-red-50 text-red-700 border-red-200" :
                              "bg-gray-50 text-gray-600 border-gray-200"
                            }`}>
                              {t.status === "done" ? "已分析" :
                               t.status === "analyzing" ? "分析中" :
                               t.status === "error" ? "失败" : "待分析"}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-app-muted max-w-xs truncate">
                            {t.ai_summary || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {/* ── Git: 文件树 + 分块预览 ── */}
          {sourceType === "git" && gitSource && (
            <section className="mt-6">
              <h2 className="app-section-title mb-3">
                仓库文件 ({sourceEntries.length})
              </h2>
              <div className="flex flex-col lg:flex-row overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)] h-[min(52rem,calc(100vh-8rem))] max-h-[min(52rem,calc(100vh-8rem))]">
                <aside className="w-full lg:w-72 xl:w-80 shrink-0 border-b lg:border-b-0 lg:border-r border-app-border flex flex-col max-h-[32rem] lg:max-h-none h-full min-h-0">
                  <GitSourceFileTree
                    entries={sourceEntries}
                    documents={sourceDocs}
                    selectedPath={selectedGitPath}
                    onSelectFile={(entry, path) => {
                      setSelectedGitPath(path);
                      setSelectedGitEntry(entry);
                    }}
                    className="flex-1 min-h-0"
                  />
                </aside>
                <div className="flex-1 min-w-0 flex flex-col h-full min-h-0 overflow-hidden">
                  {!selectedGitEntry ? (
                    <p className="text-sm text-app-muted p-6">在左侧选择文件以查看内容与分块。</p>
                  ) : (
                    <div className="flex flex-col min-h-0 flex-1 p-4 gap-3 overflow-hidden">
                      <div className="flex flex-wrap items-center gap-2 shrink-0">
                        <h3 className="text-sm font-semibold text-app-primary font-mono truncate">
                          {selectedGitPath}
                        </h3>
                        {gitSelectedDoc && (
                          <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${docStatusChip(gitSelectedDoc.status).className}`}>
                            {docStatusChip(gitSelectedDoc.status).text}
                          </span>
                        )}
                        {selectedGitEntry.source_url && (
                          <a
                            href={selectedGitEntry.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs app-link ml-auto shrink-0"
                          >
                            在 {gitSource.provider === "gitlab" ? "GitLab" : "GitHub"} 中查看
                          </a>
                        )}
                      </div>
                      {!gitSelectedDoc && (
                        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 shrink-0">
                          {gitIndexingEnabled
                            ? "文件已同步，尚未生成文档分块。请打开「设置 → 重新索引」。"
                            : "文件已同步，当前代码源处于“仅解析”模式，未启用文档索引。"}
                        </p>
                      )}
                      {gitSelectedDoc && chunksLoading && (
                        <p className="text-sm text-app-muted shrink-0">加载分块中…</p>
                      )}
                      {gitSelectedDoc && !chunksLoading && (docChunks[gitSelectedDoc.id] ?? []).length === 0 && (
                        <CodeEditorView
                          layout="fill"
                          className="flex-1 min-h-0"
                          code={selectedGitEntry.body || ""}
                          filePath={selectedGitPath || undefined}
                        />
                      )}
                      {gitSelectedDoc && !chunksLoading && (docChunks[gitSelectedDoc.id] ?? []).length > 0 && (
                        <div className="flex flex-col flex-1 min-h-0 gap-3 overflow-hidden">
                          <p className="text-xs text-app-muted shrink-0">
                            {gitSelectedDoc.char_count != null
                              ? `${gitSelectedDoc.char_count.toLocaleString()} 字符 · ${(docChunks[gitSelectedDoc.id] ?? []).length} 个分块`
                              : `${(docChunks[gitSelectedDoc.id] ?? []).length} 个分块`}
                          </p>
                          <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
                            {(docChunks[gitSelectedDoc.id] ?? []).map((c) => (
                              <CodeEditorView
                                key={c.id}
                                layout="fixed"
                                code={c.content}
                                filePath={selectedGitPath || undefined}
                                subtitle={
                                  c.quality_score != null
                                    ? `块 #${c.chunk_index + 1} · 质量 ${c.quality_score.toFixed(2)}`
                                    : `块 #${c.chunk_index + 1}`
                                }
                              />
                            ))}
                          </div>
                        </div>
                      )}
                      {!gitSelectedDoc && (
                        <CodeEditorView
                          layout="fill"
                          className="flex-1 min-h-0"
                          code={selectedGitEntry.body || ""}
                          filePath={selectedGitPath || undefined}
                        />
                      )}
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* ── 其他源：文档分块列表 ── */}
          {sourceType !== "database" && sourceType !== "git" && (
            <section className="mt-6">
              <h2 className="app-section-title mb-3">文档分块 ({sourceDocs.length})</h2>
              {chunksLoading && <p className="text-sm text-app-muted">加载分块中…</p>}
              {!chunksLoading && sourceDocs.length === 0 && sourceEntries.length === 0 && (
                <p className="text-sm text-app-muted">此源暂无文档与条目。可在「设置 → 重新导入」从 Notion 拉取。</p>
              )}
              {!chunksLoading && sourceDocs.length === 0 && sourceEntries.length > 0 && (
                <div className="space-y-4 mb-6">
                  <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    条目正文已保存，但尚未生成文档分块（可能导入时流水线未执行）。
                    请打开「设置 → 重新索引」，或「重新导入」从 API 拉取最新内容。
                  </p>
                  {sourceEntries.map((entry) => (
                    <div key={entry.id} className="rounded-lg border border-app-border bg-app-hover p-3">
                      <p className="text-sm font-semibold text-app-primary mb-1">{entry.title}</p>
                      <p className="text-xs text-app-muted mb-2">
                        条目 #{entry.id} · {(entry.body || "").length.toLocaleString()} 字符
                        {entry.source_meta?.ref ? ` · ref ${entry.source_meta.ref}` : ""}
                      </p>
                      <pre className="whitespace-pre-wrap break-words text-xs text-app-secondary max-h-48 overflow-auto">
                        {(entry.body || "").slice(0, 4000)}
                        {(entry.body || "").length > 4000 ? "\n…（已截断预览）" : ""}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
              {!chunksLoading && sourceDocs.map((doc) => (
                <div key={`doc-${doc.id}`} className="mb-6">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-sm font-semibold text-app-primary">{doc.title}</h3>
                    <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${docStatusChip(doc.status).className}`}>
                      {docStatusChip(doc.status).text}
                    </span>
                    {doc.char_count != null && (
                      <span className="text-xs text-app-muted">{doc.char_count.toLocaleString()} 字符</span>
                    )}
                  </div>
                  {(docChunks[doc.id] ?? []).length === 0 ? (
                    <p className="text-xs text-app-muted pl-2 border-l-2 border-app-border">暂无分块数据</p>
                  ) : (
                    <div className="space-y-2">
                      {(docChunks[doc.id] ?? []).map((c) => (
                        <div key={c.id} className="rounded-lg border border-app-border bg-app-hover p-3">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-xs text-app-muted">块 #{c.chunk_index + 1}</span>
                            {c.quality_score != null && (
                              <span className={`text-[11px] font-medium ${
                                c.quality_score >= 0.7 ? "app-text-success" : c.quality_score >= 0.4 ? "text-amber-600" : "app-text-danger"
                              }`}>
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
              ))}
            </section>
          )}
        </>
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
    </main>
  );
}
