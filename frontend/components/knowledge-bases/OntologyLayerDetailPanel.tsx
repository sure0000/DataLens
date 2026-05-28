"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "../AppIcons";
import { api, ApiError, formatApiError } from "../../lib/api";
import { shortenIri } from "../../lib/shortenIri";
import type { OntologyLayerDetail } from "./types";

const DEFAULT_PAGE_SIZE = 20;
const RULE_PAGE_SIZE = 10;

type ColumnDef = {
  key: string;
  label: string;
  render?: (row: Record<string, string>) => string;
  wrap?: boolean;
};

const LAYER_COLUMNS: Record<string, ColumnDef[]> = {
  vocabulary: [
    { key: "label", label: "名称" },
    { key: "definition", label: "定义" },
    { key: "status", label: "状态" },
    { key: "s", label: "IRI", render: (r) => shortenIri(r.s ?? "") },
  ],
  rule: [
    { key: "label", label: "名称" },
    { key: "ruleExpression", label: "口径/表达式", wrap: true },
    { key: "formula", label: "公式", wrap: true },
    { key: "status", label: "状态" },
  ],
  "entity-concept": [
    { key: "label", label: "名称" },
    { key: "entityType", label: "实体类型", render: (r) => shortenIri(r.entityType ?? "") },
    { key: "neighbors", label: "层级邻居", wrap: true, render: (r) => r.neighbors || "—" },
    { key: "s", label: "IRI", render: (r) => shortenIri(r.s ?? "") },
  ],
  dimension: [
    { key: "label", label: "名称" },
    { key: "definition", label: "定义" },
    { key: "dimType", label: "维度类型" },
    { key: "status", label: "状态" },
  ],
  relation: [
    { key: "s", label: "主体", render: (r) => shortenIri(r.s ?? "") },
    { key: "p", label: "谓词", render: (r) => shortenIri(r.p ?? "") },
    { key: "o", label: "客体", render: (r) => shortenIri(r.o ?? "") },
  ],
  attribute: [
    { key: "s", label: "主体", render: (r) => shortenIri(r.s ?? "") },
    { key: "p", label: "属性", render: (r) => shortenIri(r.p ?? "") },
    { key: "o", label: "值" },
  ],
};

function cellValue(row: Record<string, string>, col: ColumnDef): string {
  if (col.render) return col.render(row);
  const v = row[col.key];
  return v?.trim() ? v : "—";
}

interface OntologyLayerDetailPanelProps {
  kbId: number;
  layerKey: string;
  layerLabel?: string;
  layerDescription?: string;
  expectedTotal?: number;
}

export default function OntologyLayerDetailPanel({
  kbId,
  layerKey,
  layerLabel,
  layerDescription,
  expectedTotal,
}: OntologyLayerDetailPanelProps) {
  const [data, setData] = useState<OntologyLayerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const pageSize = layerKey === "rule" ? RULE_PAGE_SIZE : DEFAULT_PAGE_SIZE;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api<OntologyLayerDetail>(
        `/api/ontology/knowledge-bases/${kbId}/modeling/layers/${encodeURIComponent(layerKey)}?limit=${pageSize}&offset=${offset}`,
      );
      setData(res);
    } catch (e: unknown) {
      setData(null);
      setError(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [kbId, layerKey, offset, pageSize]);

  useEffect(() => {
    setOffset(0);
    setSearch("");
  }, [layerKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = LAYER_COLUMNS[layerKey] ?? LAYER_COLUMNS.vocabulary;

  const filteredItems = useMemo(() => {
    const items = data?.items ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((row) =>
      Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(q)),
    );
  }, [data?.items, search]);

  const total = data?.total ?? expectedTotal ?? 0;
  const pageStart = offset + 1;
  const pageEnd = offset + (data?.items?.length ?? 0);
  const canPrev = offset > 0;
  const canNext = Boolean(data?.has_more);

  return (
    <div className="app-card overflow-hidden">
      <div className="space-y-3 border-b border-app-border px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-app-primary">{layerLabel ?? data?.label ?? layerKey}</h3>
            {(layerDescription ?? data?.description) && (
              <p className="text-xs text-app-muted">{layerDescription ?? data?.description}</p>
            )}
          </div>
          <span className="inline-flex items-center rounded-full border border-app-border bg-app-surfaceMuted px-2.5 py-1 text-xs tabular-nums text-app-muted">
            共 {total} 条
            {total > 0 && data && <span className="ml-1">· 第 {pageStart}–{pageEnd} 条</span>}
          </span>
        </div>

        <div className="relative max-w-md">
          <Icon
            name="search"
            className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-app-muted"
          />
          <input
            type="search"
            className="app-input w-full pl-8 text-sm"
            placeholder="在当前页筛选…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
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
                  {filteredItems.length === 0 ? (
                    <tr>
                      <td colSpan={columns.length} className="px-3 py-6 text-center text-app-muted">
                        当前页无匹配结果
                      </td>
                    </tr>
                  ) : (
                    filteredItems.map((row, i) => (
                      <tr key={`${row.s ?? i}-${i}`} className="border-b border-app-border last:border-0 hover:bg-app-hover">
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
                            {cellValue(row, col)}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-app-border pt-3">
              <p className="text-[11px] text-app-muted">
                {search.trim()
                  ? `当前页筛选后 ${filteredItems.length} 条（服务端分页，翻页后需重新筛选）`
                  : "翻页加载更多记录"}
              </p>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="app-control-button inline-flex items-center gap-1 text-xs"
                  disabled={!canPrev || loading}
                  onClick={() => setOffset((o) => Math.max(0, o - pageSize))}
                >
                  <Icon name="chevronLeft" className="h-3.5 w-3.5" />
                  上一页
                </button>
                <button
                  type="button"
                  className="app-control-button inline-flex items-center gap-1 text-xs"
                  disabled={!canNext || loading}
                  onClick={() => setOffset((o) => o + pageSize)}
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
