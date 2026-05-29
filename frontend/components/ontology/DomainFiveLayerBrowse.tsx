"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Icon } from "../AppIcons";
import Toast from "../Toast";
import ConceptHierarchyPanel from "../knowledge-bases/ConceptHierarchyPanel";
import { useToast } from "../../hooks/useToast";
import { api, ApiError, formatApiError } from "../../lib/api";
import {
  SEMANTIC_ASSET_LAYERS,
  normalizeModelingLayerKey,
  ontologyUrl,
  parseKbFilterFromSearchParams,
  type SemanticAssetLayer,
} from "../../lib/ontologyRoutes";
import {
  DomainLayerItem,
  DomainOntologyLayerDetail,
  DomainOntologyLayersSummary,
  OntologyEntityOrigin,
  OntologyProvenance,
} from "../../lib/ontologyTypes";
import { shortenIri } from "../../lib/shortenIri";
import OntologyStatusBadge from "./OntologyStatusBadge";

const LAYER_ICONS: Record<string, string> = {
  vocabulary: "📖",
  rule: "📐",
  "entity-concept": "🏷️",
  relation: "🔗",
  attribute: "📋",
  dimension: "📊",
};

const RULE_PAGE_SIZE = 10;
const DEFAULT_PAGE_SIZE = 20;

type EntitySubView = "concept" | "dimension";
type ConceptViewMode = "list" | "tree";

type ColumnDef = {
  key: string;
  label: string;
  render?: (row: DomainLayerItem) => string;
  wrap?: boolean;
};

const ORIGIN_COLUMNS: ColumnDef[] = [
  {
    key: "origin_kb",
    label: "来源知识库",
    render: (r) => r.origin?.knowledge_base_name || "—",
  },
  {
    key: "origin_source",
    label: "导入来源",
    render: (r) => r.origin?.source_label || "—",
    wrap: true,
  },
];

const LAYER_COLUMNS: Record<string, ColumnDef[]> = {
  vocabulary: [
    { key: "label", label: "名称" },
    { key: "definition", label: "定义", wrap: true },
    { key: "status", label: "状态" },
    { key: "s", label: "IRI", render: (r) => shortenIri(r.s ?? "") },
    ...ORIGIN_COLUMNS,
  ],
  rule: [
    { key: "label", label: "名称" },
    { key: "ruleExpression", label: "口径/表达式", wrap: true },
    { key: "formula", label: "公式", wrap: true },
    { key: "status", label: "状态" },
    ...ORIGIN_COLUMNS,
  ],
  "entity-concept": [
    { key: "label", label: "名称" },
    { key: "entityType", label: "实体类型", render: (r) => shortenIri(r.entityType ?? "") },
    { key: "neighbors", label: "层级邻居", wrap: true, render: (r) => r.neighbors || "—" },
    { key: "s", label: "IRI", render: (r) => shortenIri(r.s ?? "") },
    ...ORIGIN_COLUMNS,
  ],
  dimension: [
    { key: "label", label: "名称" },
    { key: "definition", label: "定义", wrap: true },
    { key: "dimType", label: "维度类型" },
    { key: "status", label: "状态" },
    ...ORIGIN_COLUMNS,
  ],
  relation: [
    { key: "s", label: "主体", render: (r) => shortenIri(r.s ?? "") },
    { key: "p", label: "谓词", render: (r) => shortenIri(r.p ?? "") },
    { key: "o", label: "客体", render: (r) => shortenIri(r.o ?? "") },
    ...ORIGIN_COLUMNS,
  ],
  attribute: [
    { key: "s", label: "主体", render: (r) => shortenIri(r.s ?? "") },
    { key: "p", label: "属性", render: (r) => shortenIri(r.p ?? "") },
    { key: "o", label: "值" },
    ...ORIGIN_COLUMNS,
  ],
};

function cellValue(row: DomainLayerItem, col: ColumnDef): string {
  if (col.render) return col.render(row);
  const v = row[col.key];
  return v?.trim() ? v : "—";
}

function rowKey(row: DomainLayerItem, index: number): string {
  return `${row.origin?.knowledge_base_id ?? 0}-${row.s ?? row.p ?? ""}-${row.o ?? ""}-${index}`;
}

type Props = {
  domainId: number;
};

export default function DomainFiveLayerBrowse({ domainId }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const kbFilter = parseKbFilterFromSearchParams(searchParams);
  const { toast, notify, dismiss } = useToast();

  const [summary, setSummary] = useState<DomainOntologyLayersSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [selectedLayer, setSelectedLayer] = useState<SemanticAssetLayer>("entity-concept");
  const [entitySubView, setEntitySubView] = useState<EntitySubView>("concept");
  const [conceptViewMode, setConceptViewMode] = useState<ConceptViewMode>("list");
  const [detail, setDetail] = useState<DomainOntologyLayerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [selectedRow, setSelectedRow] = useState<DomainLayerItem | null>(null);
  const [provenance, setProvenance] = useState<OntologyProvenance | null>(null);
  const [hierarchyKbId, setHierarchyKbId] = useState<number | null>(null);

  const kbQuery = kbFilter != null ? `&kb=${kbFilter}` : "";
  const pageSize = selectedLayer === "rule" ? RULE_PAGE_SIZE : DEFAULT_PAGE_SIZE;

  const activeDetailKey = useMemo(() => {
    if (selectedLayer === "entity-concept" && entitySubView === "dimension") {
      return "dimension";
    }
    return selectedLayer;
  }, [selectedLayer, entitySubView]);

  const replaceUrl = useCallback(
    (next: {
      layer?: SemanticAssetLayer;
      entitySub?: EntitySubView;
      conceptView?: ConceptViewMode;
    }) => {
      router.replace(
        ontologyUrl({
          kbId: kbFilter ?? undefined,
          layer: next.layer ?? selectedLayer,
          entitySub: (next.entitySub ?? entitySubView) === "concept" ? undefined : next.entitySub ?? entitySubView,
          conceptView:
            (next.conceptView ?? conceptViewMode) === "list" ? undefined : next.conceptView ?? conceptViewMode,
        }),
        { scroll: false },
      );
    },
    [router, kbFilter, selectedLayer, entitySubView, conceptViewMode],
  );

  useEffect(() => {
    const layerParam = normalizeModelingLayerKey(searchParams.get("layer"));
    const entityParam = searchParams.get("entity");
    const viewParam = searchParams.get("view");
    if (layerParam === "dimension") {
      setSelectedLayer("entity-concept");
      setEntitySubView("dimension");
    } else if (layerParam && SEMANTIC_ASSET_LAYERS.includes(layerParam as SemanticAssetLayer)) {
      setSelectedLayer(layerParam as SemanticAssetLayer);
      setEntitySubView(entityParam === "dimension" ? "dimension" : "concept");
    }
    if (viewParam === "tree") {
      setConceptViewMode("tree");
    } else {
      setConceptViewMode("list");
    }
  }, [searchParams]);

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res = await api<DomainOntologyLayersSummary>(
        `/api/business-domains/${domainId}/ontology/layers${kbFilter != null ? `?kb=${kbFilter}` : ""}`,
      );
      setSummary(res);
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载五层摘要失败", "error");
    } finally {
      setSummaryLoading(false);
    }
  }, [domainId, kbFilter, notify]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    if (hierarchyKbId != null) return;
    let cancelled = false;
    api<{ knowledge_bases?: { knowledge_base_id: number }[] }>(
      `/api/business-domains/${domainId}/ontology/overview`,
    )
      .then((overview) => {
        if (cancelled) return;
        const first = overview.knowledge_bases?.[0]?.knowledge_base_id;
        if (first) setHierarchyKbId(first);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [domainId, hierarchyKbId]);

  const loadDetail = useCallback(async () => {
    if (selectedLayer === "entity-concept" && conceptViewMode === "tree") {
      return;
    }
    setDetailLoading(true);
    setDetailError(null);
    try {
      const res = await api<DomainOntologyLayerDetail>(
        `/api/business-domains/${domainId}/ontology/layers/${encodeURIComponent(activeDetailKey)}?limit=${pageSize}&offset=${offset}${kbQuery}`,
      );
      setDetail(res);
    } catch (e: unknown) {
      setDetail(null);
      setDetailError(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载层明细失败");
    } finally {
      setDetailLoading(false);
    }
  }, [domainId, activeDetailKey, offset, pageSize, kbQuery, selectedLayer, conceptViewMode]);

  useEffect(() => {
    setOffset(0);
    setSearch("");
    setSelectedRow(null);
    setProvenance(null);
  }, [activeDetailKey, kbFilter]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    const subject = selectedRow?.s;
    const kbId = selectedRow?.origin?.knowledge_base_id;
    if (!subject || !kbId) {
      setProvenance(null);
      return;
    }
    let cancelled = false;
    api<OntologyProvenance>(
      `/api/ontology/knowledge-bases/${kbId}/provenance?subject=${encodeURIComponent(subject)}`,
    )
      .then((res) => {
        if (!cancelled) setProvenance(res);
      })
      .catch(() => {
        if (!cancelled) setProvenance(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRow]);

  const layers = summary?.layers ?? {};
  const dimensionTotal = layers.dimension?.total ?? 0;
  const activeMeta = layers[activeDetailKey];
  const columns = LAYER_COLUMNS[activeDetailKey] ?? LAYER_COLUMNS.vocabulary;

  const filteredItems = useMemo(() => {
    const items = detail?.items ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((row) =>
      Object.values(row).some((v) => {
        if (typeof v === "object") return false;
        return String(v ?? "").toLowerCase().includes(q);
      }) ||
      (row.origin?.knowledge_base_name || "").toLowerCase().includes(q) ||
      (row.origin?.source_label || "").toLowerCase().includes(q),
    );
  }, [detail?.items, search]);

  const total = detail?.total ?? activeMeta?.total ?? 0;
  const pageStart = offset + 1;
  const pageEnd = offset + (detail?.items?.length ?? 0);
  const canPrev = offset > 0;
  const canNext = Boolean(detail?.has_more);

  const selectLayer = (layer: SemanticAssetLayer) => {
    setSelectedLayer(layer);
    setEntitySubView("concept");
    setConceptViewMode("list");
    replaceUrl({ layer, entitySub: "concept", conceptView: "list" });
  };

  const allEmpty =
    !summaryLoading &&
    summary &&
    SEMANTIC_ASSET_LAYERS.every((key) => (layers[key]?.total ?? 0) === 0) &&
    dimensionTotal === 0;

  if (allEmpty) {
    return (
      <div className="app-card flex flex-1 flex-col items-center justify-center p-10 text-center">
        <Icon name="layers" className="h-10 w-10 text-app-muted" aria-hidden />
        <p className="mt-3 text-sm text-app-secondary">当前业务域尚无已入图的五层语义资产。</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <Toast message={toast.message} tone={toast.tone} duration={toast.durationMs} onClose={dismiss} />

      <div className="flex flex-wrap gap-2">
        {SEMANTIC_ASSET_LAYERS.map((key) => {
          const meta = layers[key];
          const count = meta?.total ?? 0;
          const active = selectedLayer === key && entitySubView === "concept";
          return (
            <button
              key={key}
              type="button"
              onClick={() => selectLayer(key)}
              className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition-colors ${
                active
                  ? "border-app-activeBorder bg-app-activeBg font-medium text-app-primary"
                  : "border-app-border text-app-secondary hover:bg-app-hover"
              }`}
            >
              <span aria-hidden>{LAYER_ICONS[key]}</span>
              <span>{meta?.label ?? key}</span>
              <span className="rounded-full bg-app-surfaceMuted px-2 py-0.5 text-xs tabular-nums">{count}</span>
              {key === "entity-concept" && dimensionTotal > 0 ? (
                <span className="rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-700">
                  +{dimensionTotal}维
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {selectedLayer === "entity-concept" ? (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={`rounded-lg px-3 py-1.5 text-xs ${
              entitySubView === "concept" ? "bg-app-activeBg font-medium text-app-primary" : "text-app-secondary hover:bg-app-hover"
            }`}
            onClick={() => {
              setEntitySubView("concept");
              replaceUrl({ entitySub: "concept" });
            }}
          >
            概念 ({layers["entity-concept"]?.total ?? 0})
          </button>
          {dimensionTotal > 0 ? (
            <button
              type="button"
              className={`rounded-lg px-3 py-1.5 text-xs ${
                entitySubView === "dimension"
                  ? "bg-app-activeBg font-medium text-app-primary"
                  : "text-app-secondary hover:bg-app-hover"
              }`}
              onClick={() => {
                setEntitySubView("dimension");
                replaceUrl({ entitySub: "dimension" });
              }}
            >
              维度 ({dimensionTotal})
            </button>
          ) : null}
          {entitySubView === "concept" ? (
            <>
              <span className="text-app-muted">|</span>
              <button
                type="button"
                className={`rounded-lg px-3 py-1.5 text-xs ${
                  conceptViewMode === "list"
                    ? "bg-app-activeBg font-medium text-app-primary"
                    : "text-app-secondary hover:bg-app-hover"
                }`}
                onClick={() => {
                  setConceptViewMode("list");
                  replaceUrl({ conceptView: "list" });
                }}
              >
                列表
              </button>
              <button
                type="button"
                className={`rounded-lg px-3 py-1.5 text-xs ${
                  conceptViewMode === "tree"
                    ? "bg-app-activeBg font-medium text-app-primary"
                    : "text-app-secondary hover:bg-app-hover"
                }`}
                onClick={() => {
                  setConceptViewMode("tree");
                  replaceUrl({ conceptView: "tree" });
                }}
              >
                树形
              </button>
            </>
          ) : null}
        </div>
      ) : null}

      <div className={`flex min-h-0 flex-1 gap-4 ${selectedRow ? "lg:flex-row" : ""}`}>
        <div className="min-h-0 min-w-0 flex-1">
          {selectedLayer === "entity-concept" && conceptViewMode === "tree" && entitySubView === "concept" ? (
            <div className="app-card p-4">
              <p className="mb-3 text-xs text-app-muted">概念层级为只读浏览。</p>
              {hierarchyKbId ? (
                <div className="space-y-3">
                  {summary && summary.knowledge_base_count > 1 ? (
                    <label className="text-xs text-app-muted">
                      选择知识库：
                      <HierarchyKbSelect domainId={domainId} value={hierarchyKbId} onChange={setHierarchyKbId} />
                    </label>
                  ) : null}
                  <ConceptHierarchyPanel kbId={hierarchyKbId} />
                </div>
              ) : (
                <p className="text-sm text-app-muted">暂无知识库</p>
              )}
            </div>
          ) : (
            <LayerDetailTable
              layerLabel={activeMeta?.label ?? detail?.label ?? activeDetailKey}
              layerDescription={activeMeta?.description ?? detail?.description}
              loading={summaryLoading || detailLoading}
              error={detailError}
              total={total}
              pageStart={pageStart}
              pageEnd={pageEnd}
              canPrev={canPrev}
              canNext={canNext}
              search={search}
              onSearchChange={setSearch}
              onPrev={() => setOffset((o) => Math.max(0, o - pageSize))}
              onNext={() => setOffset((o) => o + pageSize)}
              columns={columns}
              items={filteredItems}
              selectedRow={selectedRow}
              onSelectRow={setSelectedRow}
            />
          )}
        </div>

        {selectedRow ? (
          <aside className="w-full shrink-0 lg:w-80">
            <ProvenancePanel row={selectedRow} provenance={provenance} onClose={() => setSelectedRow(null)} />
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function HierarchyKbSelect({
  domainId,
  value,
  onChange,
}: {
  domainId: number;
  value: number;
  onChange: (id: number) => void;
}) {
  const [options, setOptions] = useState<{ id: number; name: string }[]>([]);
  useEffect(() => {
    let cancelled = false;
    api<{ knowledge_bases: { knowledge_base_id: number; knowledge_base_name: string }[] }>(
      `/api/business-domains/${domainId}/ontology/overview`,
    )
      .then((res) => {
        if (cancelled) return;
        setOptions(
          (res.knowledge_bases || []).map((kb) => ({
            id: kb.knowledge_base_id,
            name: kb.knowledge_base_name,
          })),
        );
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [domainId]);

  return (
    <select className="app-input ml-2 w-auto" value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {options.map((opt) => (
        <option key={opt.id} value={opt.id}>
          {opt.name}
        </option>
      ))}
    </select>
  );
}

function LayerDetailTable({
  layerLabel,
  layerDescription,
  loading,
  error,
  total,
  pageStart,
  pageEnd,
  canPrev,
  canNext,
  search,
  onSearchChange,
  onPrev,
  onNext,
  columns,
  items,
  selectedRow,
  onSelectRow,
  pageSize,
}: {
  layerLabel: string;
  layerDescription?: string;
  loading: boolean;
  error: string | null;
  total: number;
  pageStart: number;
  pageEnd: number;
  canPrev: boolean;
  canNext: boolean;
  search: string;
  onSearchChange: (v: string) => void;
  onPrev: () => void;
  onNext: () => void;
  columns: ColumnDef[];
  items: DomainLayerItem[];
  selectedRow: DomainLayerItem | null;
  onSelectRow: (row: DomainLayerItem | null) => void;
}) {
  return (
    <div className="app-card overflow-hidden">
      <div className="space-y-3 border-b border-app-border px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-app-primary">{layerLabel}</h3>
            {layerDescription ? <p className="text-xs text-app-muted">{layerDescription}</p> : null}
          </div>
          <span className="inline-flex items-center rounded-full border border-app-border bg-app-surfaceMuted px-2.5 py-1 text-xs tabular-nums text-app-muted">
            共 {total} 条
            {total > 0 && <span className="ml-1">· 第 {pageStart}–{pageEnd} 条</span>}
          </span>
        </div>
        <div className="relative max-w-md">
          <Icon name="search" className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-app-muted" />
          <input
            type="search"
            className="app-input w-full pl-8 text-sm"
            placeholder="在当前页筛选…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            disabled={loading || total === 0}
          />
        </div>
      </div>

      <div className="space-y-3 px-4 py-4 sm:px-5">
        {loading && <p className="rounded-lg app-alert app-alert-info px-3 py-2 text-sm">加载明细…</p>}
        {error && !loading && <p className="rounded-lg app-alert app-alert-error px-3 py-2 text-sm">{error}</p>}
        {!loading && !error && total === 0 && (
          <p className="rounded-lg app-alert app-alert-info px-3 py-2 text-sm">本层暂无数据。</p>
        )}
        {!loading && !error && total > 0 && (
          <>
            <div className="overflow-x-auto rounded-lg border border-app-border">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-app-border bg-app-surfaceMuted">
                    {columns.map((col) => (
                      <th key={col.key} className="px-3 py-2 font-medium text-app-secondary">
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr>
                      <td colSpan={columns.length} className="px-3 py-6 text-center text-app-muted">
                        当前页无匹配结果
                      </td>
                    </tr>
                  ) : (
                    items.map((row, i) => {
                      const active =
                        selectedRow === row ||
                        (selectedRow?.s === row.s &&
                          selectedRow?.origin?.knowledge_base_id === row.origin?.knowledge_base_id);
                      return (
                        <tr
                          key={rowKey(row, i)}
                          className={`cursor-pointer border-b border-app-border last:border-0 hover:bg-app-hover ${
                            active ? "bg-app-activeBg" : ""
                          }`}
                          onClick={() => onSelectRow(active ? null : row)}
                        >
                          {columns.map((col) => (
                            <td
                              key={col.key}
                              className={`px-3 py-2 text-app-primary ${
                                col.wrap
                                  ? "max-w-[420px] whitespace-pre-wrap break-words align-top"
                                  : "max-w-[240px] truncate"
                              }`}
                              title={cellValue(row, col)}
                            >
                              {col.key === "status" && row.status ? (
                                <OntologyStatusBadge status={row.status} />
                              ) : (
                                cellValue(row, col)
                              )}
                            </td>
                          ))}
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-app-border pt-3">
              <p className="text-[11px] text-app-muted">
                {search.trim()
                  ? `当前页筛选后 ${items.length} 条（服务端分页，翻页后需重新筛选）`
                  : "点击行查看溯源；翻页加载更多记录"}
              </p>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="app-control-button inline-flex items-center gap-1 text-xs"
                  disabled={!canPrev || loading}
                  onClick={onPrev}
                >
                  <Icon name="chevronLeft" className="h-3.5 w-3.5" />
                  上一页
                </button>
                <button
                  type="button"
                  className="app-control-button inline-flex items-center gap-1 text-xs"
                  disabled={!canNext || loading}
                  onClick={onNext}
                >
                  下一页
                  <Icon name="chevronRight" className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ProvenancePanel({
  row,
  provenance,
  onClose,
}: {
  row: DomainLayerItem;
  provenance: OntologyProvenance | null;
  onClose: () => void;
}) {
  const origin = row.origin;
  const title = row.label || shortenIri(row.s ?? "记录");

  return (
    <div className="app-card flex h-full max-h-[calc(100vh-12rem)] flex-col p-4 lg:sticky lg:top-4">
      <div className="flex items-start justify-between gap-2 border-b border-app-border pb-3">
        <div className="min-w-0">
          <p className="text-xs text-app-muted">溯源</p>
          <h3 className="text-base font-semibold text-app-primary break-words">{title}</h3>
          {row.status ? (
            <div className="mt-2">
              <OntologyStatusBadge status={row.status} />
            </div>
          ) : null}
        </div>
        <button type="button" className="app-control-button shrink-0" onClick={onClose}>
          关闭
        </button>
      </div>
      <div className="mt-4 flex-1 space-y-4 overflow-y-auto text-sm">
        {origin ? (
          <OriginBlock origin={origin} />
        ) : (
          <p className="text-xs text-app-muted">暂无来源信息</p>
        )}
        {row.s ? (
          <div>
            <p className="text-xs font-medium text-app-muted">IRI</p>
            <p className="mt-1 break-all font-mono text-xs text-app-secondary">{row.s}</p>
          </div>
        ) : null}
        {provenance?.has_provenance ? (
          <div>
            <p className="text-xs font-medium text-app-muted mb-2">溯源链</p>
            {provenance.documents?.map((d) => (
              <p key={d.id} className="text-xs text-app-secondary">
                文档：{d.title}
              </p>
            ))}
            {provenance.evidence_packages?.map((p) => (
              <p key={p.display_id} className="text-xs text-app-secondary">
                证据包 {p.display_id}：{p.title}
              </p>
            ))}
            {provenance.chunks?.map((c) => (
              <p key={c.iri} className="text-xs text-app-secondary">
                分块 {shortenIri(c.iri)}
                {c.content_preview
                  ? `：${c.content_preview.slice(0, 120)}${c.content_preview.length > 120 ? "…" : ""}`
                  : ""}
              </p>
            ))}
          </div>
        ) : row.s && origin?.knowledge_base_id ? (
          <p className="text-xs text-app-muted">加载溯源链…</p>
        ) : null}
      </div>
    </div>
  );
}

function OriginBlock({ origin }: { origin: OntologyEntityOrigin }) {
  return (
    <div className="rounded-lg border border-app-border/60 px-3 py-2 text-xs">
      <p className="text-app-muted">来源知识库</p>
      <p className="font-medium text-app-primary">{origin.knowledge_base_name}</p>
      {origin.source_label ? (
        <>
          <p className="mt-2 text-app-muted">导入来源</p>
          <p className="text-app-secondary">{origin.source_label}</p>
        </>
      ) : null}
      {origin.source_type ? (
        <>
          <p className="mt-2 text-app-muted">来源类型</p>
          <p className="text-app-secondary">{origin.source_type}</p>
        </>
      ) : null}
      {origin.evidence_package_display_id ? (
        <>
          <p className="mt-2 text-app-muted">证据包</p>
          <p className="text-app-secondary">{origin.evidence_package_display_id}</p>
        </>
      ) : null}
    </div>
  );
}
