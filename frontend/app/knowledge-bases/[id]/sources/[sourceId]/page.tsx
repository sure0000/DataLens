"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ConfirmDialog from "../../../../../components/ConfirmDialog";
import PageHeader from "../../../../../components/PageHeader";
import Toast from "../../../../../components/Toast";
import { api } from "../../../../../lib/api";

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
  const [loading, setLoading] = useState(false);

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

  async function loadDocuments() {
    try {
      const res = await api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`);
      setDocuments(res.documents ?? []);
    } catch { setDocuments([]); }
  }

  async function loadDatabaseDetail() {
    setDbDetailLoading(true);
    try {
      const res = await api<{ import: DatabaseImport; tables: DatabaseTableNode[] }>(
        `/api/knowledge-bases/${kbId}/database-imports/${sourceId}`
      );
      setDbImport(res.import);
      setDbTables(res.tables ?? []);
    } catch {
      setDbImport(null);
      setDbTables([]);
    } finally { setDbDetailLoading(false); }
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
      setApiSources([...(kbApiRes.api_sources ?? []), ...(globalApiRes.api_sources ?? [])]);
      loadDocuments();
      if (sourceType === "database") {
        loadDatabaseDetail();
      }
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
        } else if (sourceType === "database") {
          await api(`/api/knowledge-bases/${kbId}/database-imports/${sourceId}`, { method: "DELETE" });
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

  async function loadAllChunks(docs: DocRow[]) {
    if (docs.length === 0) { setDocChunks({}); return; }
    setChunksLoading(true);
    const map: Record<number, ChunkRow[]> = {};
    for (const doc of docs) {
      try {
        const res = await api<{ chunks: ChunkRow[] }>(`/api/knowledge-bases/${kbId}/documents/${doc.id}/chunks`);
        map[doc.id] = res.chunks ?? [];
      } catch { map[doc.id] = []; }
    }
    setDocChunks(map);
    setChunksLoading(false);
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
      if (apiSource) return apiKind ? meta.kind === apiKind : false;
      return e.id === sourceId;
    }
    if (sourceType === "file" || sourceType === "manual") {
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
      if (apiSource) return apiKind ? meta.kind === apiKind : false;
      return d.knowledge_entry_id === sourceId || d.id === sourceId;
    }
    if (sourceType === "file" || sourceType === "manual") {
      return d.knowledge_entry_id === sourceId || d.id === sourceId;
    }
    return false;
  }

  // Filtered data
  const sourceDocs = documents.filter(isSourceDoc);

  // Auto-load chunks for all source documents
  useEffect(() => {
    loadAllChunks(sourceDocs);
  }, [documents, sourceType, apiSource]);

  // Source config
  const gitSource = sourceType === "git" ? gitSources.find((s) => s.id === sourceId) : null;

  // Compute title and subtitle
  let sourceTitle: string;
  let sourceSubtitle: string;
  let statusChip: { text: string; className: string } | null = null;

  if (sourceType === "git" && gitSource) {
    sourceTitle = gitSource.name;
    sourceSubtitle = `${gitSource.provider === "gitlab" ? "GitLab" : "GitHub"} · ${gitSource.owner}/${gitSource.repo}`;
    statusChip = gitSyncStatusChip(gitSource.last_sync_status);
  } else if (sourceType === "database") {
    sourceTitle = dbImport?.datasource_name || "数据库导入";
    sourceSubtitle = dbImport ? `${dbImport.database_names.length} 个数据库：${dbImport.database_names.join(", ")}` : "";
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
                        <th className="px-3 py-2.5">AI 分析摘要</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dbTables.map((t) => (
                        <tr key={`tbl-${t.id}`} className="hover:bg-app-hover">
                          <td className="px-3 py-2.5">
                            <Link
                              href={`/datasources/${dbImport?.datasource_id}/tables/${t.table_name}`}
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

          {/* ── Documents / Chunks ── */}
          {sourceType !== "database" && (
            <section className="mt-6">
              <h2 className="app-section-title mb-3">文档分块 ({sourceDocs.length})</h2>
              {chunksLoading && <p className="text-sm text-app-muted">加载分块中…</p>}
              {!chunksLoading && sourceDocs.length === 0 && (
                <p className="text-sm text-app-muted">此源暂无文档。</p>
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
