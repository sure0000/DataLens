"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "../AppIcons";
import { PipelineStepIcon, QualityStatIcon } from "../icons";
import { api, ApiError } from "../../lib/api";
import { shortenIri } from "../../lib/shortenIri";

export interface QuarantineFixTemplate {
  id: string;
  label: string;
  description: string;
  requires?: Record<string, string>;
}

export interface QuarantineItem {
  item_idx: number;
  q: string;
  reason: string;
  reason_label?: string;
  raw?: string;
  subject?: string;
  predicate?: string;
  object?: string;
  object_is_uri?: boolean;
  fix_templates?: QuarantineFixTemplate[];
}

export type QuarantineListResponse = {
  ok: boolean;
  kb_id: number;
  items: QuarantineItem[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
};

const PAGE_SIZE = 20;

interface QuarantineListProps {
  kbId: number;
  onResolve?: () => void;
  onTotalChange?: (total: number) => void;
}

export default function QuarantineList({ kbId, onResolve, onTotalChange }: QuarantineListProps) {
  const [items, setItems] = useState<QuarantineItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyIdx, setBusyIdx] = useState<number | null>(null);
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());
  const [templateParams, setTemplateParams] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api<QuarantineListResponse>(
        `/api/ontology/knowledge-bases/${kbId}/quarantine?limit=${PAGE_SIZE}&offset=${offset}`,
      );
      setItems(res.items ?? []);
      const t = res.total ?? 0;
      setTotal(t);
      setHasMore(Boolean(res.has_more));
      onTotalChange?.(t);
    } catch {
      setItems([]);
      setTotal(0);
      setHasMore(false);
      onTotalChange?.(0);
    } finally {
      setLoading(false);
    }
  }, [kbId, offset, onTotalChange]);

  useEffect(() => {
    setOffset(0);
  }, [kbId]);

  useEffect(() => {
    void load();
  }, [load]);

  const pageIndex = Math.floor(offset / PAGE_SIZE);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = offset + items.length;

  async function handleResolve(itemIdx: number, approve: boolean) {
    setBusyIdx(itemIdx);
    try {
      await api(
        `/api/ontology/knowledge-bases/${kbId}/quarantine/${itemIdx}/resolve?approve=${approve}`,
        { method: "POST" },
      );
      if (items.length === 1 && offset > 0) {
        setOffset((o) => Math.max(0, o - PAGE_SIZE));
      } else {
        await load();
      }
      onResolve?.();
    } catch {
      /* parent may toast */
    } finally {
      setBusyIdx(null);
    }
  }

  async function handleApplyFix(itemIdx: number, templateId: string, requires?: Record<string, string>) {
    setBusyIdx(itemIdx);
    const params: Record<string, unknown> = {};
    if (requires) {
      for (const key of Object.keys(requires)) {
        const val = templateParams[`${itemIdx}-${key}`];
        if (val) params[key] = Number.isNaN(Number(val)) ? val : Number(val);
      }
    }
    try {
      await api(`/api/ontology/knowledge-bases/${kbId}/quarantine/${itemIdx}/apply-fix`, {
        method: "POST",
        body: JSON.stringify({ template_id: templateId, params }),
      });
      if (items.length === 1 && offset > 0) {
        setOffset((o) => Math.max(0, o - PAGE_SIZE));
      } else {
        await load();
      }
      onResolve?.();
    } catch (e: unknown) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : "修复失败";
      console.error(msg);
    } finally {
      setBusyIdx(null);
    }
  }

  if (loading && items.length === 0) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="app-card p-4 animate-pulse">
            <div className="h-4 w-3/4 bg-app-skeleton-1 rounded mb-2" />
            <div className="h-3 w-1/2 bg-app-skeleton-1 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (total === 0) {
    return (
      <div className="app-card p-6 text-center">
        <PipelineStepIcon status="ok" className="h-8 w-8 mx-auto mb-2" />
        <p className="text-sm font-medium text-app-primary">隔离区为空</p>
        <p className="text-xs text-app-muted mt-1">所有三元组均已通过校验并写入生产图。</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <QualityStatIcon tone="warning" className="h-4 w-4" />
          <span className="text-sm font-medium text-app-primary">共 {total} 条隔离断言</span>
        </div>
        {total > PAGE_SIZE && (
          <span className="text-[11px] text-app-muted tabular-nums">
            第 {pageStart}–{pageEnd} 条 · 第 {pageIndex + 1}/{pageCount} 页
          </span>
        )}
      </div>

      {items.map((item) => {
        const idx = item.item_idx;
        const expanded = expandedItems.has(idx);
        const busy = busyIdx === idx;

        return (
          <div key={idx} className="app-card border border-red-500/20 bg-red-500/5 overflow-hidden">
            <button
              type="button"
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-red-500/5"
              onClick={() =>
                setExpandedItems((prev) => {
                  const next = new Set(prev);
                  if (next.has(idx)) next.delete(idx);
                  else next.add(idx);
                  return next;
                })
              }
            >
              {expanded ? (
                <Icon name="chevronDown" className="h-4 w-4 shrink-0 text-app-muted" />
              ) : (
                <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-app-muted" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-app-primary truncate">
                  {item.subject ? shortenIri(item.subject) : item.raw ? shortenIri(item.raw) : `断言 #${idx}`}
                </p>
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">
                  {item.reason_label || item.reason}
                </p>
              </div>
              <div className="flex gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="app-button text-xs py-1 px-2"
                  disabled={busy}
                  onClick={() => handleResolve(idx, true)}
                >
                  <PipelineStepIcon status="ok" className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  className="app-button-secondary text-xs py-1 px-2"
                  disabled={busy}
                  onClick={() => handleResolve(idx, false)}
                >
                  <PipelineStepIcon status="fail" className="h-3.5 w-3.5" />
                </button>
              </div>
            </button>

            {expanded && (
              <div className="border-t border-red-500/20 px-4 py-3 space-y-3">
                {item.predicate && <DetailRow label="谓词" value={shortenIri(item.predicate)} />}
                {item.object && <DetailRow label="客体" value={shortenIri(item.object)} />}

                {(item.fix_templates?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-xs font-medium text-app-primary mb-2 flex items-center gap-1">
                      <Icon name="wrench" className="h-3.5 w-3.5" />
                      修复模板
                    </p>
                    <div className="space-y-2">
                      {item.fix_templates!.map((tpl) => (
                        <div
                          key={tpl.id}
                          className="rounded-lg border border-app-border p-2 bg-app-surface"
                        >
                          <p className="text-xs font-medium text-app-primary">{tpl.label}</p>
                          <p className="text-[11px] text-app-muted mt-0.5">{tpl.description}</p>
                          {tpl.requires &&
                            Object.entries(tpl.requires).map(([key]) => (
                              <input
                                key={key}
                                className="app-input mt-2 w-full text-xs"
                                placeholder={key}
                                value={templateParams[`${idx}-${key}`] ?? ""}
                                onChange={(e) =>
                                  setTemplateParams((p) => ({
                                    ...p,
                                    [`${idx}-${key}`]: e.target.value,
                                  }))
                                }
                              />
                            ))}
                          <button
                            type="button"
                            className={`app-button-secondary mt-2 text-xs w-full ${busy ? "is-loading" : ""}`}
                            disabled={busy}
                            onClick={() => handleApplyFix(idx, tpl.id, tpl.requires)}
                          >
                            应用模板
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between gap-2 pt-2">
          <p className="text-[11px] text-app-muted">每页 {PAGE_SIZE} 条</p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="app-control-button inline-flex items-center gap-1 text-xs"
              disabled={offset <= 0 || loading}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              <Icon name="chevronLeft" className="h-3.5 w-3.5" />
              上一页
            </button>
            <button
              type="button"
              className="app-control-button inline-flex items-center gap-1 text-xs"
              disabled={!hasMore || loading}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              下一页
              <Icon name="chevronRight" className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-[11px]">
      <span className="shrink-0 font-medium text-app-muted w-16">{label}</span>
      <code className="text-app-link break-all">{value}</code>
    </div>
  );
}
