"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Database,
  GitBranch,
  Layers,
  Network,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import PageHeader from "../PageHeader";
import Toast from "../Toast";
import LineageGraph from "../knowledge-bases/LineageGraph";
import type { LineageData } from "../knowledge-bases/types";
import type { PipelineStats } from "../knowledge-bases/types";
import { useToast } from "../../hooks/useToast";
import { api, ApiError, formatApiError } from "../../lib/api";
import {
  GraphEdge,
  GraphNode,
  KnowledgeBaseOption,
  ONTOLOGY_KB_STORAGE_KEY,
  KbRdfView,
  OntologyMetric,
  OntologyStoreInfo,
  OntologyTab,
  OntologyTerm,
  RELATION_TYPE_LABELS,
  SyncResult,
  TERM_TYPE_LABELS,
} from "../../lib/ontologyTypes";
import OntologyStatusBadge from "./OntologyStatusBadge";

const TABS: { id: OntologyTab; label: string; icon: typeof BookOpen }[] = [
  { id: "overview", label: "概览", icon: Layers },
  { id: "terms", label: "业务术语", icon: BookOpen },
  { id: "metrics", label: "指标口径", icon: Sparkles },
  { id: "relations", label: "关系与血缘", icon: GitBranch },
  { id: "rdf", label: "RDF 数据", icon: Network },
  { id: "store", label: "存储与同步", icon: Database },
];

function confidenceClass(v: number): string {
  if (v >= 80) return "app-text-success";
  if (v >= 50) return "text-amber-600";
  return "app-text-danger";
}

export default function OntologyWorkspace({
  fixedKbId,
  embedded = false,
}: {
  fixedKbId?: number;
  embedded?: boolean;
} = {}) {
  const { toast, notify, dismiss } = useToast();
  const [kbs, setKbs] = useState<KnowledgeBaseOption[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<number | null>(fixedKbId ?? null);
  const [tab, setTab] = useState<OntologyTab>("overview");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [kbListLoading, setKbListLoading] = useState(true);

  const [terms, setTerms] = useState<OntologyTerm[]>([]);
  const [metrics, setMetrics] = useState<OntologyMetric[]>([]);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [lineage, setLineage] = useState<LineageData | null>(null);
  const [pipelineStats, setPipelineStats] = useState<PipelineStats | null>(null);
  const [store, setStore] = useState<OntologyStoreInfo>({});
  const [globalStore, setGlobalStore] = useState<OntologyStoreInfo>({});
  const [rdfView, setRdfView] = useState<KbRdfView | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedTerm, setSelectedTerm] = useState<OntologyTerm | null>(null);
  const [selectedMetric, setSelectedMetric] = useState<OntologyMetric | null>(null);

  const selectedKb = useMemo(
    () => kbs.find((k) => k.id === selectedKbId) ?? null,
    [kbs, selectedKbId],
  );

  const loadKbList = useCallback(async () => {
    setKbListLoading(true);
    try {
      const res = await api<{ knowledge_bases: KnowledgeBaseOption[] }>("/api/knowledge-bases");
      let list = res.knowledge_bases || [];
      if (fixedKbId && !list.some((k) => k.id === fixedKbId)) {
        try {
          const one = await api<{ knowledge_base: KnowledgeBaseOption }>(`/api/knowledge-bases/${fixedKbId}`);
          if (one.knowledge_base) list = [one.knowledge_base, ...list];
        } catch {
          /* 知识库可能已删除 */
        }
      }
      setKbs(list);
      if (fixedKbId) {
        setSelectedKbId(fixedKbId);
      } else if (list.length) {
        const saved =
          typeof window !== "undefined" ? localStorage.getItem(ONTOLOGY_KB_STORAGE_KEY) : null;
        const savedId = saved ? Number(saved) : NaN;
        const valid = list.some((k) => k.id === savedId);
        setSelectedKbId(valid ? savedId : list[0].id);
      }
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载知识库失败", "error");
    } finally {
      setKbListLoading(false);
    }
  }, [fixedKbId, notify]);

  const loadWorkspace = useCallback(async () => {
    if (!selectedKbId) return;
    setLoading(true);
    setSelectedTerm(null);
    setSelectedMetric(null);
    try {
      const [termsRes, metricsRes, graphRes, statsRes, lineageRes, healthRes, rdfRes] = await Promise.all([
        api<{ terms: OntologyTerm[] }>(`/api/ontology/knowledge-bases/${selectedKbId}/terms`),
        api<{ metrics: OntologyMetric[] }>(`/api/ontology/knowledge-bases/${selectedKbId}/metrics`),
        api<{ nodes: GraphNode[]; edges: GraphEdge[]; store: OntologyStoreInfo }>(
          `/api/ontology/knowledge-bases/${selectedKbId}/graph`,
        ),
        api<PipelineStats>(`/api/knowledge-bases/${selectedKbId}/pipeline-stats`),
        api<LineageData>(`/api/knowledge-bases/${selectedKbId}/lineage`).catch(() => null),
        api<{ ok: boolean } & OntologyStoreInfo>("/api/ontology/health"),
        api<{ ok: boolean } & KbRdfView>(`/api/ontology/knowledge-bases/${selectedKbId}/rdf-view`),
      ]);
      setTerms(termsRes.terms || []);
      setMetrics(metricsRes.metrics || []);
      setGraphNodes(graphRes.nodes || []);
      setGraphEdges(graphRes.edges || []);
      setStore(graphRes.store || {});
      setPipelineStats(statsRes);
      setLineage(lineageRes);
      setGlobalStore(healthRes);
      setRdfView(rdfRes);
      localStorage.setItem(ONTOLOGY_KB_STORAGE_KEY, String(selectedKbId));
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载本体数据失败", "error");
    } finally {
      setLoading(false);
    }
  }, [selectedKbId, notify]);

  useEffect(() => {
    loadKbList();
  }, [loadKbList]);

  useEffect(() => {
    if (selectedKbId) loadWorkspace();
  }, [selectedKbId, loadWorkspace]);

  const handleSelectKb = (id: number) => {
    setSelectedKbId(id);
    setSearch("");
    setStatusFilter("all");
  };

  const handleSync = async () => {
    if (!selectedKbId) return;
    setSyncing(true);
    try {
      const res = await api<SyncResult>(
        `/api/ontology/knowledge-bases/${selectedKbId}/sync-from-legacy`,
        { method: "POST" },
      );
      const written = res.written ?? 0;
      const candidates = res.candidates;
      const quarantined = res.quarantined ?? 0;
      const blocked = res.shacl_blocked;
      if (blocked) {
        notify("SHACL 校验未通过，三元组未写入 RDF 存储。请查看存储与同步页。", "error", 8000);
      } else {
        notify(
          `已写入 RDF：${written} 条${candidates && candidates !== written ? `（候选 ${candidates}）` : ""}${quarantined > 0 ? `，隔离 ${quarantined} 条` : ""}`,
          "success",
          6000,
        );
      }
      await loadWorkspace();
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "同步失败", "error");
    } finally {
      setSyncing(false);
    }
  };

  const filteredTerms = useMemo(() => {
    const q = search.trim().toLowerCase();
    return terms.filter((t) => {
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.definition.toLowerCase().includes(q) ||
        (t.related_fields || []).some((f) => f.toLowerCase().includes(q))
      );
    });
  }, [terms, search, statusFilter]);

  const filteredMetrics = useMemo(() => {
    const q = search.trim().toLowerCase();
    return metrics.filter((m) => {
      if (statusFilter !== "all" && m.status !== statusFilter) return false;
      if (!q) return true;
      return (
        m.name.toLowerCase().includes(q) ||
        m.formula.toLowerCase().includes(q) ||
        (m.caliber || "").toLowerCase().includes(q) ||
        (m.bound_table_refs || []).some((r) => r.toLowerCase().includes(q))
      );
    });
  }, [metrics, search, statusFilter]);

  const termStatusCounts = pipelineStats?.terms_by_status ?? {};
  const metricStatusCounts = pipelineStats?.metrics_by_status ?? {};

  const showEntityPanel = selectedTerm || selectedMetric;

  return (
    <main className={embedded ? "flex min-h-0 flex-col" : "app-page flex min-h-0 flex-col"}>
      {!embedded && (
      <PageHeader
        title="本体建模"
        subtitle="文档导入 Pipeline 的最后一步：将术语、指标与表结构写入 Fuseki RDF。"
        actionsBelowSubtitle
        actions={
          <div className="app-toolbar flex-wrap">
            <button
              type="button"
              className={`app-button app-toolbar-action ${syncing ? "is-loading" : ""}`}
              disabled={!selectedKbId || syncing || loading}
              onClick={handleSync}
            >
              <RefreshCw className="mr-1.5 inline h-4 w-4" aria-hidden />
              {syncing ? "同步中…" : "同步到 RDF"}
            </button>
            <button
              type="button"
              className="app-button-secondary app-toolbar-action"
              disabled={!selectedKbId || loading}
              onClick={() => loadWorkspace()}
            >
              刷新
            </button>
            {selectedKbId ? (
              <Link href={`/knowledge-bases/${selectedKbId}`} className="app-button-secondary app-toolbar-action no-underline">
                打开知识库
              </Link>
            ) : null}
          </div>
        }
      />
      )}

      {embedded && (
        <div className="mb-3 flex justify-end gap-2">
          <button type="button" className={`app-button text-sm ${syncing ? "is-loading" : ""}`} disabled={!selectedKbId || syncing || loading} onClick={handleSync}>
            {syncing ? "同步中…" : "同步到 RDF"}
          </button>
          <button type="button" className="app-button-secondary text-sm" disabled={!selectedKbId || loading} onClick={() => loadWorkspace()}>刷新</button>
        </div>
      )}

      <Toast message={toast.message} tone={toast.tone} duration={toast.durationMs} onClose={dismiss} />

      <div className={`flex min-h-0 flex-1 flex-col gap-4 ${embedded ? "" : "mt-4 lg:flex-row"}`}>
        {!embedded && (
        <>
        {/* 知识库侧栏 */}
        <aside className="w-full shrink-0 lg:w-56 xl:w-64">
          <div className="app-card p-3">
            <h2 className="app-section-title text-sm">知识库</h2>
            {kbListLoading ? (
              <div className="mt-3 space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 animate-pulse rounded-lg bg-app-hover" />
                ))}
              </div>
            ) : kbs.length === 0 ? (
              <p className="mt-3 text-xs text-app-muted">
                暂无知识库。
                <Link href="/knowledge-bases" className="app-link ml-1">
                  去创建
                </Link>
              </p>
            ) : (
              <ul className="mt-2 max-h-[min(420px,50vh)] space-y-1 overflow-y-auto">
                {kbs.map((kb) => {
                  const active = kb.id === selectedKbId;
                  return (
                    <li key={kb.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectKb(kb.id)}
                        className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
                          active
                            ? "border-app-activeBorder bg-app-activeBg"
                            : "border-transparent hover:border-app-border hover:bg-app-hover"
                        }`}
                      >
                        <p className="text-sm font-medium text-app-primary line-clamp-2">{kb.name}</p>
                        {kb.description ? (
                          <p className="mt-0.5 text-[11px] text-app-muted line-clamp-2">{kb.description}</p>
                        ) : null}
                        <p className="mt-1 text-[10px] text-app-muted">ID {kb.id}</p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>
        </>
        )}

        {/* 主工作区 */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {!selectedKb ? (
            <div className="app-card flex flex-1 flex-col items-center justify-center p-10 text-center">
              <Layers className="h-10 w-10 text-app-muted" aria-hidden />
              <p className="mt-3 text-sm text-app-secondary">
                {kbListLoading || loading
                  ? "正在加载本体数据…"
                  : embedded
                    ? "无法加载该知识库的本体数据。"
                    : "请从左侧选择一个知识库，开始浏览本体数据。"}
              </p>
            </div>
          ) : (
            <>
              {/* 统计卡片 */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard label="业务术语" value={terms.length} sub={`待审核 ${termStatusCounts.pending_review ?? 0}`} />
                <StatCard label="指标口径" value={metrics.length} sub={`待审核 ${metricStatusCounts.pending_review ?? 0}`} />
                <StatCard
                  label="语义关系"
                  value={graphEdges.length}
                  sub={`血缘 ${lineage?.stats?.done ?? 0} 条`}
                />
                <StatCard
                  label="RDF 生产图"
                  value={rdfView?.production.triple_count ?? 0}
                  sub={`术语 ${rdfView?.production.term_count ?? 0} · 指标 ${rdfView?.production.metric_count ?? 0} · 表 ${rdfView?.production.physical_table_count ?? 0}`}
                />
              </div>

              {/* 标签页 */}
              <div className="mt-4 flex flex-wrap items-center gap-2 border-b border-app-border pb-2">
                {TABS.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => {
                      setTab(id);
                      setSearch("");
                      setSelectedTerm(null);
                      setSelectedMetric(null);
                    }}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                      tab === id
                        ? "bg-app-activeBg font-medium text-app-primary"
                        : "text-app-secondary hover:bg-app-hover"
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden />
                    {label}
                  </button>
                ))}
              </div>

              {/* 搜索与筛选（术语/指标页） */}
              {(tab === "terms" || tab === "metrics") && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <div className="relative min-w-[200px] flex-1">
                    <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-app-muted" />
                    <input
                      className="app-input w-full pl-9"
                      placeholder={tab === "terms" ? "搜索术语名称、定义、字段…" : "搜索指标名称、公式、表…"}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <select
                    className="app-input w-auto min-w-[120px]"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <option value="all">全部状态</option>
                    <option value="approved">已发布</option>
                    <option value="pending_review">待审核</option>
                    <option value="draft">草稿</option>
                  </select>
                  <span className="text-xs text-app-muted">
                    {tab === "terms"
                      ? `显示 ${filteredTerms.length} / ${terms.length}`
                      : `显示 ${filteredMetrics.length} / ${metrics.length}`}
                  </span>
                </div>
              )}

              <div className="mt-3 min-h-0 flex-1">
                {loading ? (
                  <div className="app-card p-8 text-center text-sm text-app-muted">加载中…</div>
                ) : tab === "overview" ? (
                  <OverviewTab
                    kb={selectedKb}
                    pipelineStats={pipelineStats}
                    terms={terms}
                    metrics={metrics}
                    graphEdges={graphEdges}
                    onOpenTerms={() => setTab("terms")}
                    onOpenMetrics={() => setTab("metrics")}
                  />
                ) : tab === "terms" ? (
                  <EntityTable
                    emptyHint="运行知识库「语义清洗流水线」后，AI 会从文档中提取业务术语。"
                    rows={filteredTerms.map((t) => ({
                      key: t.id,
                      name: t.name,
                      badge: TERM_TYPE_LABELS[t.type] || t.type,
                      summary: t.definition,
                      confidence: t.confidence,
                      status: t.status,
                      onSelect: () => setSelectedTerm(t),
                      active: selectedTerm?.id === t.id,
                    }))}
                  />
                ) : tab === "metrics" ? (
                  <EntityTable
                    emptyHint="流水线完成后，指标口径将显示在此处。"
                    rows={filteredMetrics.map((m) => ({
                      key: m.id,
                      name: m.name,
                      badge: null,
                      summary: m.formula,
                      confidence: m.confidence,
                      status: m.status,
                      onSelect: () => setSelectedMetric(m),
                      active: selectedMetric?.id === m.id,
                    }))}
                  />
                ) : tab === "relations" ? (
                  <RelationsTab edges={graphEdges} lineage={lineage} />
                ) : tab === "rdf" ? (
                  <RdfDataTab rdfView={rdfView} pgTermCount={terms.length} pgMetricCount={metrics.length} />
                ) : (
                  <StoreTab
                    store={store}
                    globalStore={globalStore}
                    rdfView={rdfView}
                    kbId={selectedKb.id}
                    onSync={handleSync}
                    syncing={syncing}
                  />
                )}
              </div>
            </>
          )}
        </div>

        {/* 详情侧栏 */}
        {showEntityPanel ? (
          <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-sm border-l border-app-border bg-app-card shadow-xl lg:relative lg:z-auto lg:w-72 lg:shrink-0 lg:shadow-none">
            <EntityDetailPanel
              term={selectedTerm}
              metric={selectedMetric}
              onClose={() => {
                setSelectedTerm(null);
                setSelectedMetric(null);
              }}
            />
          </aside>
        ) : null}
      </div>
    </main>
  );
}

function StatCard({ label, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <div className="app-card px-4 py-3">
      <p className="text-xs text-app-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-app-primary">{value}</p>
      {sub ? <p className="mt-0.5 text-[11px] text-app-muted">{sub}</p> : null}
    </div>
  );
}

function OverviewTab({
  kb,
  pipelineStats,
  terms,
  metrics,
  graphEdges,
  onOpenTerms,
  onOpenMetrics,
}: {
  kb: KnowledgeBaseOption;
  pipelineStats: PipelineStats | null;
  terms: OntologyTerm[];
  metrics: OntologyMetric[];
  graphEdges: GraphEdge[];
  onOpenTerms: () => void;
  onOpenMetrics: () => void;
}) {
  const run = pipelineStats?.last_pipeline_run;
  const runStatus = run?.status;
  const statusLabel =
    runStatus === "completed" ? "已完成" : runStatus === "running" ? "运行中" : runStatus === "failed" ? "失败" : "未运行";

  const topTerms = [...terms].sort((a, b) => b.confidence - a.confidence).slice(0, 5);
  const topMetrics = [...metrics].sort((a, b) => b.confidence - a.confidence).slice(0, 5);

  return (
    <div className="space-y-4">
      <div className="app-card p-4">
        <h3 className="app-section-title">当前知识库</h3>
        <p className="mt-1 text-sm font-medium text-app-primary">{kb.name}</p>
        {kb.description ? <p className="mt-1 text-xs text-app-secondary">{kb.description}</p> : null}
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-app-muted">
          <span>文档 {pipelineStats?.indexed_documents ?? 0} / {pipelineStats?.total_documents ?? 0} 已索引</span>
          <span>
            流水线 {statusLabel}
            {run?.completed_at ? ` · ${new Date(run.completed_at).toLocaleString()}` : ""}
          </span>
        </div>
        {runStatus === "failed" && (
          <p className="mt-2 text-xs text-amber-600">
            上次流水线未完全成功，可在知识库详情中重新运行「语义清洗」后再同步到 RDF。
          </p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <PreviewList title="高频术语（按置信度）" items={topTerms.map((t) => ({ label: t.name, sub: t.definition, confidence: t.confidence }))} onMore={onOpenTerms} empty="暂无术语" />
        <PreviewList title="指标口径（按置信度）" items={topMetrics.map((m) => ({ label: m.name, sub: m.formula, confidence: m.confidence }))} onMore={onOpenMetrics} empty="暂无指标" />
      </div>

      {graphEdges.length > 0 && (
        <div className="app-card p-4">
          <h3 className="app-section-title">最近语义关系</h3>
          <ul className="mt-2 space-y-2">
            {graphEdges.slice(0, 8).map((e) => (
              <li key={e.id} className="rounded-lg border border-app-border/60 px-3 py-2 text-xs">
                <span className="font-medium text-app-muted">{RELATION_TYPE_LABELS[e.type] || e.type}</span>
                <p className="mt-1 font-mono text-app-secondary truncate">
                  {e.source} → {e.target}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PreviewList({
  title,
  items,
  onMore,
  empty,
}: {
  title: string;
  items: { label: string; sub: string; confidence: number }[];
  onMore: () => void;
  empty: string;
}) {
  return (
    <div className="app-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="app-section-title">{title}</h3>
        <button type="button" className="app-link text-xs" onClick={onMore}>
          查看全部
        </button>
      </div>
      {items.length === 0 ? (
        <p className="mt-3 text-xs text-app-muted">{empty}</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {items.map((item, i) => (
            <li key={i} className="rounded-lg border border-app-border/50 px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-app-primary">{item.label}</p>
                <span className={`text-[11px] font-medium shrink-0 ${confidenceClass(item.confidence)}`}>
                  {Math.round(item.confidence)}%
                </span>
              </div>
              <p className="mt-0.5 text-xs text-app-muted line-clamp-2">{item.sub}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EntityTable({
  rows,
  emptyHint,
}: {
  rows: {
    key: number;
    name: string;
    badge: string | null;
    summary: string;
    confidence: number;
    status: string;
    onSelect: () => void;
    active: boolean;
  }[];
  emptyHint: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="app-card p-8 text-center">
        <p className="text-sm text-app-muted">没有匹配的结果。</p>
        <p className="mt-2 text-xs text-app-muted">{emptyHint}</p>
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
      <table className="app-table">
        <thead>
          <tr>
            <th className="px-3 py-2.5 text-left">名称</th>
            <th className="px-3 py-2.5 text-left">摘要</th>
            <th className="w-20 px-3 py-2.5 text-right">置信度</th>
            <th className="w-24 px-3 py-2.5 text-left">状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.key}
              className={`cursor-pointer transition-colors ${r.active ? "bg-app-activeBg" : "hover:bg-app-hover"}`}
              onClick={r.onSelect}
            >
              <td className="px-3 py-2.5">
                <p className="text-sm font-medium text-app-primary">{r.name}</p>
                {r.badge ? <span className="text-[11px] text-app-muted">{r.badge}</span> : null}
              </td>
              <td className="px-3 py-2.5">
                <p className="text-xs text-app-secondary line-clamp-2">{r.summary || "—"}</p>
              </td>
              <td className={`px-3 py-2.5 text-right text-xs font-medium ${confidenceClass(r.confidence)}`}>
                {Math.round(r.confidence)}%
              </td>
              <td className="px-3 py-2.5">
                <OntologyStatusBadge status={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RdfDataTab({
  rdfView,
  pgTermCount,
  pgMetricCount,
}: {
  rdfView: KbRdfView | null;
  pgTermCount: number;
  pgMetricCount: number;
}) {
  if (!rdfView) {
    return <div className="app-card p-8 text-sm text-app-muted">加载 RDF 视图失败</div>;
  }
  const prod = rdfView.production;
  const q = rdfView.quarantine;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-app-secondary">
        <p>
          <strong className="text-app-primary">术语 / 指标</strong> 标签页数据来自 PostgreSQL（可编辑源）。
          <strong className="text-app-primary ml-1">本页</strong> 展示已写入 RDF 生产图 <code className="text-xs">graph/kb/…</code> 的三元组，供 Copilot 路由与 SPARQL 使用。
        </p>
        {(prod.term_count < pgTermCount || prod.metric_count < pgMetricCount) && (
          <p className="mt-2 text-amber-700 dark:text-amber-400">
            RDF 中术语/指标少于数据库记录时，请点击「同步到 RDF」；若 SHACL 未通过则不会写入。
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="RDF 术语" value={prod.term_count} />
        <StatCard label="RDF 指标" value={prod.metric_count} />
        <StatCard label="物理表" value={prod.physical_table_count} />
      </div>

      {q.assertion_count > 0 && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm">
          <p className="font-medium text-red-600 dark:text-red-400">
            隔离区 {q.assertion_count} 条断言（未进入生产图）
          </p>
          <p className="mt-1 text-app-muted text-xs">
            多为历史同步时谓词校验失败；修复后重新「同步到 RDF」可写入生产图。
          </p>
        </div>
      )}

      <RdfEntitySection title="RDF 业务术语" items={prod.terms.map((t) => ({ label: t.label, sub: t.definition, status: t.status }))} empty="生产图中暂无术语，请先同步。" />
      <RdfEntitySection title="RDF 指标口径" items={prod.metrics.map((m) => ({ label: m.label, sub: m.formula, status: m.status }))} empty="生产图中暂无指标，请先同步。" />

      <section>
        <h3 className="app-section-title mb-2">物理表（仅存在于 RDF）</h3>
        {prod.physical_tables.length === 0 ? (
          <div className="app-card p-6 text-sm text-app-muted">暂无物理表三元组。请先将数据表关联到本知识库并运行表分析同步。</div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {prod.physical_tables.map((t) => (
              <div key={t.iri} className="app-card p-4">
                <p className="text-sm font-medium text-app-primary">表 ID {t.platform_id || "—"}</p>
                <p className="mt-1 text-xs text-app-muted line-clamp-4">{t.summary || "（无业务摘要）"}</p>
                <p className="mt-2 font-mono text-[10px] text-app-muted break-all">{t.iri}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RdfEntitySection({
  title,
  items,
  empty,
}: {
  title: string;
  items: { label: string; sub?: string; status?: string }[];
  empty: string;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return items;
    return items.filter(
      (i) => i.label.toLowerCase().includes(s) || (i.sub || "").toLowerCase().includes(s),
    );
  }, [items, q]);

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="app-section-title">{title}</h3>
        <input
          className="app-input w-48 text-xs"
          placeholder="筛选…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      {items.length === 0 ? (
        <div className="app-card p-6 text-sm text-app-muted">{empty}</div>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-y-auto rounded-xl border border-app-border bg-app-card p-2">
          {filtered.map((item, idx) => (
            <li key={idx} className="rounded-lg px-3 py-2 hover:bg-app-hover">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-app-primary">{item.label}</span>
                {item.status ? <OntologyStatusBadge status={item.status} /> : null}
              </div>
              {item.sub ? <p className="mt-0.5 text-xs text-app-muted line-clamp-2">{item.sub}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RelationsTab({ edges, lineage }: { edges: GraphEdge[]; lineage: LineageData | null }) {
  return (
    <div className="space-y-6">
      <section>
        <h3 className="app-section-title mb-2">语义关系</h3>
        {edges.length === 0 ? (
          <div className="app-card p-6 text-sm text-app-muted">
            暂无显式语义边。运行语义关系同步或流水线后，术语与表、指标之间的映射会出现在此处。
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {edges.map((e) => (
              <div key={e.id} className="app-card px-4 py-3">
                <span className="text-xs font-medium text-app-muted">
                  {RELATION_TYPE_LABELS[e.type] || e.type}
                </span>
                <p className="mt-2 font-mono text-xs text-app-primary break-all">{e.source}</p>
                <p className="text-center text-app-muted text-[10px] py-0.5">↓</p>
                <p className="font-mono text-xs text-app-secondary break-all">{e.target}</p>
              </div>
            ))}
          </div>
        )}
      </section>
      <LineageGraph data={lineage} />
    </div>
  );
}

function StoreTab({
  store,
  globalStore,
  rdfView,
  kbId,
  onSync,
  syncing,
}: {
  store: OntologyStoreInfo;
  globalStore: OntologyStoreInfo;
  rdfView: KbRdfView | null;
  kbId: number;
  onSync: () => void;
  syncing: boolean;
}) {
  const backend = store.storage_backend || globalStore.storage_backend || "local_file";
  const path = store.local_store_path || globalStore.local_store_path;
  const prod = rdfView?.production;

  return (
    <div className="space-y-4">
      <div className="app-card p-4">
        <h3 className="app-section-title">存储状态</h3>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-app-muted">后端</dt>
            <dd className="mt-0.5 text-app-primary">{backend === "fuseki" ? "Apache Fuseki" : "本地 Trig 文件"}</dd>
          </div>
          <div>
            <dt className="text-xs text-app-muted">TBox 已加载</dt>
            <dd className="mt-0.5 text-app-primary">{(globalStore.tbox_loaded ?? store.tbox_loaded) ? "是" : "否"}</dd>
          </div>
          <div>
            <dt className="text-xs text-app-muted">全局三元组（所有图）</dt>
            <dd className="mt-0.5 font-mono text-app-primary">{globalStore.triple_count ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-app-muted">本库生产图三元组</dt>
            <dd className="mt-0.5 font-mono text-app-primary">{prod?.triple_count ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-app-muted">本库隔离区</dt>
            <dd className="mt-0.5 font-mono text-app-primary">{rdfView?.quarantine.assertion_count ?? 0} 条</dd>
          </div>
        </dl>
        {path ? (
          <p className="mt-3 break-all text-xs text-app-muted">
            路径：<code className="text-[11px]">{path}</code>
          </p>
        ) : null}
        <p className="mt-2 break-all text-xs text-app-muted font-mono">
          Graph IRI: https://datalens.local/graph/kb/{kbId}
        </p>
      </div>

      <div className="app-card p-4">
        <h3 className="app-section-title">同步说明</h3>
        <p className="mt-2 text-sm text-app-secondary leading-relaxed">
          「同步到 RDF」会将 PostgreSQL 中的术语、指标、血缘与语义关系写入 OWL 三元组存储。不符合 TBox 的断言会进入隔离区，可在后续版本中人工审批。
        </p>
        <button
          type="button"
          className={`app-button mt-4 ${syncing ? "is-loading" : ""}`}
          disabled={syncing}
          onClick={onSync}
        >
          {syncing ? "同步中…" : "立即同步当前知识库"}
        </button>
      </div>
    </div>
  );
}

function EntityDetailPanel({
  term,
  metric,
  onClose,
}: {
  term: OntologyTerm | null;
  metric: OntologyMetric | null;
  onClose: () => void;
}) {
  const entity = term || metric;
  if (!entity) return null;
  const isTerm = !!term;

  return (
    <div className="flex h-full flex-col p-4">
      <div className="flex items-start justify-between gap-2 border-b border-app-border pb-3">
        <div className="min-w-0">
          <p className="text-xs text-app-muted">{isTerm ? "业务术语" : "指标口径"}</p>
          <h3 className="text-lg font-semibold text-app-primary break-words">{entity.name}</h3>
          <div className="mt-2">
            <OntologyStatusBadge status={entity.status} />
          </div>
        </div>
        <button type="button" className="app-control-button shrink-0" onClick={onClose}>
          关闭
        </button>
      </div>
      <div className="mt-4 flex-1 overflow-y-auto space-y-4 text-sm">
        {isTerm && term ? (
          <>
            <Field label="类型" value={TERM_TYPE_LABELS[term.type] || term.type} />
            <Field label="定义" value={term.definition} multiline />
            {term.related_fields?.length ? (
              <div>
                <p className="text-xs font-medium text-app-muted mb-1">关联字段</p>
                <div className="flex flex-wrap gap-1">
                  {term.related_fields.map((f) => (
                    <code key={f} className="rounded bg-app-hover px-1.5 py-0.5 text-[11px] font-mono">
                      {f}
                    </code>
                  ))}
                </div>
              </div>
            ) : null}
            {term.concept_id ? <Field label="概念 ID" value={term.concept_id} mono /> : null}
          </>
        ) : metric ? (
          <>
            <Field label="公式" value={metric.formula} multiline />
            {metric.caliber ? <Field label="口径说明" value={metric.caliber} multiline /> : null}
            {metric.bound_table_refs?.length ? (
              <div>
                <p className="text-xs font-medium text-app-muted mb-1">绑定表</p>
                <ul className="space-y-1">
                  {metric.bound_table_refs.map((r) => (
                    <li key={r} className="font-mono text-xs text-app-secondary">
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {metric.concept_id ? <Field label="概念 ID" value={metric.concept_id} mono /> : null}
          </>
        ) : null}
        <Field label="置信度" value={`${Math.round(entity.confidence)}%`} />
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  multiline,
  mono,
}: {
  label: string;
  value: string;
  multiline?: boolean;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-app-muted">{label}</p>
      <p
        className={`mt-1 text-app-primary ${multiline ? "whitespace-pre-wrap leading-relaxed" : ""} ${mono ? "font-mono text-xs break-all" : ""}`}
      >
        {value || "—"}
      </p>
    </div>
  );
}
