"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "../AppIcons";
import SearchField from "../SearchField";
import OntologyProvenanceModal, { type ProvenanceColumnDef, type ProvenanceRow } from "../ontology/OntologyProvenanceModal";
import { api, ApiError, formatApiError } from "../../lib/api";
import type { OntologyProvenance } from "../../lib/ontologyTypes";
import {
  ATTRIBUTE_PREDICATE_LABELS,
  ENTITY_TYPE_LABELS,
  PREDICATE_LABELS,
} from "../../lib/ontologyTypes";
import { humanPredicateLabel, labelForIri, shortenIri } from "../../lib/shortenIri";
import type { OntologyLayerDetail } from "./types";

const DEFAULT_PAGE_SIZE = 20;
const RULE_PAGE_SIZE = 10;

const LAYER_COLUMNS: Record<string, ProvenanceColumnDef[]> = {
  vocabulary: [
    { key: "label", label: "名称" },
    { key: "synonyms", label: "同义词", render: (r) => {
      const list = Array.isArray(r.synonyms) ? r.synonyms.filter((s: unknown) => typeof s === "string" && s.trim()) : [];
      return list.length > 0 ? list.join("、") : "—";
    }},
    { key: "definition", label: "定义", wrap: true },
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
    { key: "definition", label: "说明", wrap: true },
    { key: "entityType", label: "实体类型", render: (r) => labelForIri(r.entityType ?? "", ENTITY_TYPE_LABELS) },
    { key: "neighbors", label: "层级邻居", wrap: true, render: (r) => {
      const raw = r.neighbors;
      if (!raw || raw === "—") return "—";
      return raw.split(" | ").map((n) => shortenIri(n.trim())).join(" · ");
    }},
    { key: "s", label: "IRI", render: (r) => shortenIri(r.s ?? "") },
  ],
  dimension: [
    { key: "label", label: "名称" },
    { key: "definition", label: "定义" },
    { key: "dimType", label: "维度类型", render: (r) => humanPredicateLabel(r.dimType ?? "") },
    { key: "status", label: "状态" },
  ],
  relation: [
    { key: "s", label: "主体", render: (r) => shortenIri(r.s ?? "") },
    { key: "p", label: "谓词", render: (r) => labelForIri(r.p ?? "", PREDICATE_LABELS) },
    { key: "o", label: "客体", render: (r) => shortenIri(r.o ?? "") },
  ],
  attribute: [
    { key: "subjectLabel", label: "名称", render: (r) => r.subjectLabel || "—" },
    { key: "s", label: "主体", render: (r) => shortenIri(r.s ?? "") },
    { key: "p", label: "属性", render: (r) => labelForIri(r.p ?? "", ATTRIBUTE_PREDICATE_LABELS) },
    { key: "o", label: "值" },
  ],
};

function cellValue(row: ProvenanceRow, col: ProvenanceColumnDef): string {
  if (col.render) return col.render(row);
  const v = row[col.key];
  return v?.trim() ? v : "—";
}

function rowKey(row: ProvenanceRow, index: number): string {
  return `${row.origin?.knowledge_base_id ?? 0}-${row.s ?? row.p ?? ""}-${row.o ?? ""}-${index}`;
}

interface OntologyLayerDetailPanelProps {
  kbId: number;
  layerKey: string;
  layerLabel?: string;
  layerDescription?: string;
  expectedTotal?: number;
  /** 属性层：存在数据源入图条数时默认仅展示物理表/列 */
  physicalAttributeTotal?: number;
}

export default function OntologyLayerDetailPanel({
  kbId,
  layerKey,
  layerLabel,
  layerDescription,
  expectedTotal,
  physicalAttributeTotal = 0,
}: OntologyLayerDetailPanelProps) {
  const [data, setData] = useState<OntologyLayerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [physicalOnly, setPhysicalOnly] = useState(
    () => layerKey === "attribute" && physicalAttributeTotal > 0,
  );
  const [selectedRow, setSelectedRow] = useState<ProvenanceRow | null>(null);
  const [provenance, setProvenance] = useState<OntologyProvenance | null>(null);
  const pageSize = layerKey === "rule" ? RULE_PAGE_SIZE : DEFAULT_PAGE_SIZE;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: String(pageSize),
        offset: String(offset),
      });
      if (layerKey === "attribute" && physicalOnly) {
        params.set("physical_only", "true");
      }
      if (debouncedSearch.trim()) {
        params.set("q", debouncedSearch.trim());
      }
      const res = await api<OntologyLayerDetail>(
        `/api/ontology/knowledge-bases/${kbId}/modeling/layers/${encodeURIComponent(layerKey)}?${params.toString()}`,
      );
      setData(res);
    } catch (e: unknown) {
      setData(null);
      setError(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [kbId, layerKey, offset, pageSize, physicalOnly, debouncedSearch]);

  useEffect(() => {
    setOffset(0);
    setSearch("");
    setDebouncedSearch("");
    setSelectedRow(null);
    setProvenance(null);
    setPhysicalOnly(layerKey === "attribute" && physicalAttributeTotal > 0);
  }, [layerKey, physicalAttributeTotal]);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedSearch, physicalOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const subject = selectedRow?.s;
    const originKbId = selectedRow?.origin?.knowledge_base_id ?? kbId;
    if (!subject || !originKbId) {
      setProvenance(null);
      return;
    }
    let cancelled = false;
    api<OntologyProvenance>(
      `/api/ontology/knowledge-bases/${originKbId}/provenance?subject=${encodeURIComponent(subject)}`,
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
  }, [selectedRow, kbId]);

  const columns = LAYER_COLUMNS[layerKey] ?? LAYER_COLUMNS.vocabulary;

  const tableItems = (data?.items ?? []) as ProvenanceRow[];

  const total = data?.total ?? expectedTotal ?? 0;
  const unfilteredTotal = data?.unfiltered_total;
  const pageStart = offset + 1;
  const pageEnd = offset + (data?.items?.length ?? 0);
  const canPrev = offset > 0;
  const canNext = Boolean(data?.has_more);

  return (
    <>
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
              {unfilteredTotal != null && unfilteredTotal !== total && (
                <span className="ml-1">/ 全层 {unfilteredTotal}</span>
              )}
              {total > 0 && data && <span className="ml-1">· 第 {pageStart}–{pageEnd} 条</span>}
            </span>
          </div>

          {layerKey === "attribute" && physicalAttributeTotal > 0 && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-app-secondary">
              <input
                type="checkbox"
                className="rounded border-app-border"
                checked={physicalOnly}
                onChange={(e) => setPhysicalOnly(e.target.checked)}
              />
              仅数据源表结构（{physicalAttributeTotal} 条，power 等库表语义）
            </label>
          )}

          <SearchField
            className="max-w-md"
            placeholder={
              layerKey === "attribute"
                ? "搜索表名、字段名或属性值（全库）…"
                : "搜索名称或 IRI（全库）…"
            }
            value={search}
            onChange={setSearch}
            disabled={loading}
          />
        </div>

        <div className="space-y-3 px-4 py-4 sm:px-5">
          {loading && <p className="rounded-lg app-alert app-alert-info px-3 py-2 text-sm">加载明细…</p>}

          {error && !loading && <p className="rounded-lg app-alert app-alert-error px-3 py-2 text-sm">{error}</p>}

          {!loading && !error && total === 0 && (
            <p className="rounded-lg app-alert app-alert-info px-3 py-2 text-sm">
              {layerKey === "attribute" && physicalOnly && physicalAttributeTotal > 0 && debouncedSearch
                ? "无匹配的数据源表结构记录，请调整关键词或取消「仅数据源表结构」。"
                : layerKey === "attribute" && physicalOnly
                  ? "本层暂无数据源表结构记录；可取消勾选「仅数据源表结构」查看文档/Git 抽取属性。"
                  : "本层暂无数据。"}
            </p>
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
                    {tableItems.length === 0 ? (
                      <tr>
                        <td colSpan={columns.length} className="px-3 py-6 text-center text-app-muted">
                          无匹配结果
                        </td>
                      </tr>
                    ) : (
                      tableItems.map((row, i) => {
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
                            onClick={() => setSelectedRow(row)}
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
                                {cellValue(row, col)}
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
                  {debouncedSearch.trim()
                    ? `已按关键词筛选，共 ${total} 条`
                    : "点击行查看详情与溯源；数据源表结构默认优先展示"}
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

      {selectedRow ? (
        <OntologyProvenanceModal
          row={selectedRow}
          provenance={provenance}
          columns={columns}
          onClose={() => setSelectedRow(null)}
        />
      ) : null}
    </>
  );
}
