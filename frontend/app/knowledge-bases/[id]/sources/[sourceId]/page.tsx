"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ConfirmDialog from "../../../../../components/ConfirmDialog";
import PageHeader from "../../../../../components/PageHeader";
import Toast from "../../../../../components/Toast";
import { api, ApiError, formatApiError } from "../../../../../lib/api";

import type {
  ApiSource,
  BusinessTerm,
  ChunkRow,
  DocRow,
  Entry,
  GitSource,
  KB,
  LineageData,
  MetricDef,
  PipelineStats,
} from "../../../../../components/knowledge-bases/types";

import {
  computeOutputCards,
  computePipelineSteps,
  docStatusChip,
  gitSyncStatusChip,
} from "../../../../../components/knowledge-bases/utils";

import CleanPipeline from "../../../../../components/knowledge-bases/CleanPipeline";
import LineageGraph from "../../../../../components/knowledge-bases/LineageGraph";
import MetricList from "../../../../../components/knowledge-bases/MetricList";
import SourceResultCards from "../../../../../components/knowledge-bases/SourceResultCards";
import TermList from "../../../../../components/knowledge-bases/TermList";

type TabId = "documents" | "terms" | "metrics";

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
  const [loading, setLoading] = useState(false);

  // ── V2 semantic data ──
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [terms, setTerms] = useState<BusinessTerm[]>([]);
  const [metrics, setMetrics] = useState<MetricDef[]>([]);
  const [lineage, setLineage] = useState<LineageData | null>(null);

  // ── Tabs ──
  const [activeTab, setActiveTab] = useState<TabId>("documents");

  // ── Chunk expansion ──
  const [expandedDocId, setExpandedDocId] = useState<number | null>(null);
  const [chunks, setChunks] = useState<ChunkRow[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);

  // ── Settings menu ──
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const settingsMenuRef = useRef<HTMLDivElement>(null);

  // ── Pipeline trigger ──
  const [pipelineRunning, setPipelineRunning] = useState(false);

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

  async function runSemanticPipeline() {
    setPipelineRunning(true);
    try {
      const res = await api<{ status: string; run_id?: number }>(`/api/knowledge-bases/${kbId}/semantic-pipeline/run`, { method: "POST" });
      if (res.status === "skipped") {
        notifyUser("语义提取已在运行中，请稍后刷新查看结果", "info");
      } else {
        notifyUser("语义提取完成，正在刷新数据…", "success");
      }
      await loadV2Data();
    } catch (e: unknown) {
      notifyUser(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "启动失败", "error");
    } finally { setPipelineRunning(false); }
  }

  // ═══════════════════════════════════════════════════
  // Data fetching
  // ═══════════════════════════════════════════════════

  async function loadDocuments() {
    try {
      const res = await api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`);
      setDocuments(res.documents ?? []);
    } catch { setDocuments([]); }
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
      const [res, gitRes, kbApiRes, globalApiRes] = await Promise.all([
        api<{ knowledge_base: KB; entries: Entry[] }>(`/api/knowledge-bases/${kbId}`),
        api<{ git_sources: GitSource[] }>(`/api/knowledge-bases/${kbId}/git-sources`).catch(() => ({ git_sources: [] })),
        api<{ api_sources: ApiSource[] }>(`/api/knowledge-bases/${kbId}/api-sources`).catch(() => ({ api_sources: [] })),
        api<{ api_sources: ApiSource[] }>(`/api/api-sources`).catch(() => ({ api_sources: [] })),
      ]);
      setKb(res.knowledge_base);
      setEntries(res.entries);
      setGitSources(gitRes.git_sources ?? []);
      // Merge KB-bound and global API sources so we can find the config for both
      const merged = [...(kbApiRes.api_sources ?? []), ...(globalApiRes.api_sources ?? [])];
      setApiSources(merged);
      loadDocuments();
      loadV2Data();
    } catch {
      setKb(null); setEntries([]); setGitSources([]);
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
        } else if (sourceType === "api") {
          if (apiSource) {
            await api(`/api/api-sources/${sourceId}`, { method: "DELETE" });
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

  async function loadChunks(docId: number) {
    setChunksLoading(true);
    setSelectedDocId(docId);
    setExpandedDocId(docId);
    try {
      const res = await api<{ chunks: ChunkRow[] }>(`/api/knowledge-bases/${kbId}/documents/${docId}/chunks`);
      setChunks(res.chunks ?? []);
    } catch { setChunks([]); } finally { setChunksLoading(false); }
  }

  // ═══════════════════════════════════════════════════
  // Filtering helpers
  // ═══════════════════════════════════════════════════

  const apiSource = sourceType === "api" ? apiSources.find((s) => s.id === sourceId) : null;
  const apiKind = apiSource ? `${apiSource.integration}_api` : null;

  function isSourceEntry(e: Entry): boolean {
    const meta = e.source_meta || {};
    if (sourceType === "git") {
      return meta.kind === "git_file" && String(meta.git_source_id) === String(sourceId);
    }
    if (sourceType === "api") {
      // If sourceId matches an API source config, filter by kind
      if (apiSource) return apiKind ? meta.kind === apiKind : false;
      // Otherwise sourceId is an entry ID (API-imported entry)
      return e.id === sourceId;
    }
    if (sourceType === "file") {
      return e.id === sourceId;
    }
    return false;
  }

  function isSourceDoc(d: DocRow): boolean {
    const meta = d.source_meta || {};
    if (sourceType === "git") {
      return meta.kind === "git_file" && String(meta.git_source_id) === String(sourceId);
    }
    if (sourceType === "api") {
      // If sourceId matches an API source config, filter by kind
      if (apiSource) return apiKind ? meta.kind === apiKind : false;
      // Otherwise sourceId is an entry ID
      return d.knowledge_entry_id === sourceId || d.id === sourceId;
    }
    if (sourceType === "file") {
      return d.knowledge_entry_id === sourceId || d.id === sourceId;
    }
    return false;
  }

  // Filtered data
  const sourceEntries = entries.filter(isSourceEntry);
  const sourceDocs = documents.filter(isSourceDoc);
  const sourceEntryIds = new Set(sourceEntries.map((e) => e.id));

  // Terms and metrics traced back to source entries via source_entry_id
  const sourceTerms = terms.filter((t) => t.source_entry_id != null && sourceEntryIds.has(t.source_entry_id));
  const sourceMetrics = metrics.filter((m) => m.source_entry_id != null && sourceEntryIds.has(m.source_entry_id));

  // Lineage filtered by git_source_id
  const sourceLineage: LineageData | null =
    sourceType === "git" && lineage
      ? {
          ...lineage,
          edges: lineage.edges.filter((e) => e.git_source_id === sourceId),
        }
      : null;

  // Source config
  const gitSource = sourceType === "git" ? gitSources.find((s) => s.id === sourceId) : null;

  // Build synthetic stats for this source
  const sourceStats: PipelineStats | null = stats
    ? {
        ...stats,
        total_documents: sourceDocs.length,
        indexed_documents: sourceDocs.filter((d) => d.status === "indexed").length,
        documents_by_status: sourceDocs.reduce(
          (acc, d) => {
            acc[d.status] = (acc[d.status] || 0) + 1;
            return acc;
          },
          {} as Record<string, number>,
        ),
        term_count: sourceTerms.length,
        metric_count: sourceMetrics.length,
        terms_by_status: sourceTerms.reduce(
          (acc, t) => {
            acc[t.status] = (acc[t.status] || 0) + 1;
            return acc;
          },
          {} as Record<string, number>,
        ),
        metrics_by_status: sourceMetrics.reduce(
          (acc, m) => {
            acc[m.status] = (acc[m.status] || 0) + 1;
            return acc;
          },
          {} as Record<string, number>,
        ),
        lineage_stats: sourceLineage
          ? sourceLineage.stats
          : { done: 0, processing: 0, pending: 0 },
      }
    : null;

  const hasGit = sourceType === "git";
  const pipelineSteps = computePipelineSteps(sourceStats, hasGit);
  const outputCards = computeOutputCards(sourceStats, sourceTerms, sourceMetrics);

  // Compute title and subtitle
  let sourceTitle: string;
  let sourceSubtitle: string;
  let statusChip: { text: string; className: string } | null = null;

  if (sourceType === "git" && gitSource) {
    sourceTitle = gitSource.name;
    sourceSubtitle = `${gitSource.provider === "gitlab" ? "GitLab" : "GitHub"} · ${gitSource.owner}/${gitSource.repo}`;
    statusChip = gitSyncStatusChip(gitSource.last_sync_status);
  } else if (sourceType === "api") {
    if (apiSource) {
      // KB-bound or global API source config found
      const integrationLabel =
        apiSource.integration === "notion" ? "Notion" :
        apiSource.integration === "confluence" ? "Confluence" :
        apiSource.integration === "feishu" ? "飞书" : apiSource.integration;
      sourceTitle = apiSource.name;
      sourceSubtitle = `${integrationLabel} · ${apiSource.object_id}`;
      statusChip = gitSyncStatusChip(apiSource.last_sync_status);
    } else {
      // API-imported entry: sourceId is the entry ID
      const entry = entries.find((e) => e.id === sourceId) || sourceEntries[0];
      sourceTitle = entry?.title || "API 导入";
      const metaKind = entry?.source_meta?.kind || "";
      const integrationLabel =
        metaKind === "notion_api" ? "Notion" :
        metaKind === "confluence_api" ? "Confluence" :
        metaKind === "feishu_api" ? "飞书" : metaKind.replace("_api", "");
      sourceSubtitle = `${integrationLabel} · ${entry?.source_meta?.ref || entry?.source_meta?.label || "导入"}`;
      const doc = sourceDocs[0];
      if (doc) statusChip = docStatusChip(doc.status);
    }
  } else if (sourceType === "file") {
    const entry = entries.find((e) => e.id === sourceId);
    sourceTitle = entry?.title || "文件";
    const label = entry?.source_meta?.label;
    sourceSubtitle = (label && label !== "上传文件") ? label : (entry?.source_meta?.ref || entry?.source_meta?.kind || "文件");
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
                <div className="absolute right-0 top-full mt-1 z-50 min-w-[140px] rounded-lg border border-[var(--app-border)] bg-[var(--app-surface)] py-1 shadow-lg">
                  {sourceDocs.some((d) => d.status === "indexed") && (
                    <button
                      className="block w-full px-4 py-2 text-left text-sm text-[var(--app-text-primary)] hover:bg-[var(--app-bg-hover)] disabled:opacity-50"
                      type="button"
                      disabled={pipelineRunning}
                      onClick={() => { setSettingsMenuOpen(false); runSemanticPipeline(); }}
                    >
                      {pipelineRunning ? "启动中…" : "运行语义提取"}
                    </button>
                  )}
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

      {loading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {!loading && kb && (
        <>
          {/* ── Source config info ── */}
          {sourceType === "git" && gitSource && (
            <div className="app-card p-4 mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-app-muted">
              <span>分支：{gitSource.uses_default_branch || !gitSource.branch ? "默认分支" : gitSource.branch}</span>
              {gitSource.path_prefix && <span>路径：{gitSource.path_prefix}</span>}
              <span>限制：{gitSource.max_files} 文件 / {gitSource.max_file_kb} KB</span>
              {gitSource.cron_expression && <span>定时：{gitSource.cron_expression}</span>}
              {gitSource.last_sync_at && <span>上次同步：{new Date(gitSource.last_sync_at).toLocaleString()}</span>}
              {gitSource.last_error && (
                <span className="text-rose-600">错误：{gitSource.last_error}</span>
              )}
            </div>
          )}

          {/* ── Pipeline visualization ── */}
          <div className="mt-4">
            <CleanPipeline steps={pipelineSteps} />
          </div>

          {/* ── Output cards ── */}
          {outputCards.length > 0 && (
            <div className="mt-4">
              <SourceResultCards cards={outputCards} onViewAll={(cardId) => setActiveTab(cardId as TabId)} />
            </div>
          )}

          {/* ── Lineage graph (Git only) ── */}
          {sourceType === "git" && sourceLineage && (
            <div className="mt-4">
              <LineageGraph data={sourceLineage} />
            </div>
          )}

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
              文档 ({sourceDocs.length})
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
              术语 ({sourceTerms.length})
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
              指标 ({sourceMetrics.length})
            </button>
          </div>

          {/* ── Tab content ── */}
          <div className="mt-4">
            {activeTab === "documents" && (
              <SourceDocumentsTab
                documents={sourceDocs}
                expandedDocId={expandedDocId}
                chunks={chunks}
                chunksLoading={chunksLoading}
                selectedDocId={selectedDocId}
                onLoadChunks={loadChunks}
                onCloseChunks={() => { setExpandedDocId(null); setChunks([]); }}
              />
            )}

            {activeTab === "terms" && (
              <TermList terms={sourceTerms} loading={loading} />
            )}

            {activeTab === "metrics" && (
              <MetricList metrics={sourceMetrics} loading={loading} />
            )}
          </div>
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

// ═══════════════════════════════════════════════════
// SourceDocumentsTab — documents list for a source
// ═══════════════════════════════════════════════════

function SourceDocumentsTab({
  documents,
  expandedDocId,
  chunks,
  chunksLoading,
  selectedDocId,
  onLoadChunks,
  onCloseChunks,
}: {
  documents: DocRow[];
  expandedDocId: number | null;
  chunks: ChunkRow[];
  chunksLoading: boolean;
  selectedDocId: number | null;
  onLoadChunks: (docId: number) => void;
  onCloseChunks: () => void;
}) {
  if (documents.length === 0) {
    return <p className="text-sm text-app-muted">此源暂无文档。</p>;
  }

  return (
    <>
      <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
        <table className="app-table">
          <thead>
            <tr>
              <th className="px-3 py-2.5">文档</th>
              <th className="w-28 px-3 py-2.5">状态</th>
              <th className="w-44 px-3 py-2.5">创建时间</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => {
              const chip = docStatusChip(doc.status);
              return (
                <tr key={`doc-${doc.id}`} className="hover:bg-app-hover">
                  <td className="px-3 py-2.5">
                    <button
                      className="text-left text-sm font-medium text-indigo-600 hover:text-indigo-800 truncate max-w-full"
                      type="button"
                      title={doc.title}
                      onClick={() => onLoadChunks(doc.id)}
                    >
                      {doc.title}
                    </button>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                      <span className="text-xs text-app-muted">
                        {doc.source_meta?.label || doc.source_type}
                      </span>
                      {doc.char_count != null && (
                        <span className="text-xs text-app-muted">
                          {doc.char_count.toLocaleString()} 字符
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${chip.className}`}>
                      {chip.text}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-app-muted whitespace-nowrap">
                    {new Date(doc.created_at).toLocaleString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Chunk viewer modal */}
      {expandedDocId != null && (
        <div className="app-modal-backdrop" role="presentation" onClick={onCloseChunks}>
          <div
            className="app-card max-h-[85vh] w-full max-w-2xl overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="app-section-title">分块详情</h2>
              <button className="app-control-button" type="button" onClick={onCloseChunks}>
                关闭
              </button>
            </div>
            <div className="space-y-3">
              {chunksLoading && selectedDocId === expandedDocId && (
                <p className="text-sm text-app-muted">加载中…</p>
              )}
              {!chunksLoading && chunks.length === 0 && (
                <p className="text-sm text-app-muted">该文档暂无分块数据。</p>
              )}
              {chunks.map((c) => (
                <div
                  key={c.id}
                  className="rounded-lg border border-app-border bg-app-hover p-3"
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs text-app-muted">
                      块 #{c.chunk_index + 1}
                    </span>
                    {c.quality_score != null && (
                      <span
                        className={`text-[11px] font-medium ${
                          c.quality_score >= 0.7
                            ? "text-emerald-600"
                            : c.quality_score >= 0.4
                            ? "text-amber-600"
                            : "text-rose-500"
                        }`}
                      >
                        质量 {c.quality_score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <pre className="whitespace-pre-wrap break-words text-xs text-app-secondary">
                    {c.content}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
