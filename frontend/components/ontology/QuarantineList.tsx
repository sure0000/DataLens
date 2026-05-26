"use client";

import { useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronRight, Wrench, X } from "lucide-react";
import { api, ApiError } from "../../lib/api";

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

interface QuarantineListProps {
  kbId: number;
  items: QuarantineItem[];
  onResolve?: () => void;
  loading?: boolean;
}

export default function QuarantineList({ kbId, items, onResolve, loading }: QuarantineListProps) {
  const [busyIdx, setBusyIdx] = useState<number | null>(null);
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());
  const [templateParams, setTemplateParams] = useState<Record<string, string>>({});

  if (loading) {
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

  if (items.length === 0) {
    return (
      <div className="app-card p-6 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-emerald-500" />
        <p className="text-sm font-medium text-app-primary">隔离区为空</p>
        <p className="text-xs text-app-muted mt-1">所有三元组均已通过校验并写入生产图。</p>
      </div>
    );
  }

  async function handleResolve(itemIdx: number, approve: boolean) {
    setBusyIdx(itemIdx);
    try {
      await api(
        `/api/ontology/knowledge-bases/${kbId}/quarantine/${itemIdx}/resolve?approve=${approve}`,
        { method: "POST" },
      );
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
      onResolve?.();
    } catch (e: unknown) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : "修复失败";
      console.error(msg);
    } finally {
      setBusyIdx(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="h-4 w-4 text-amber-500" />
        <span className="text-sm font-medium text-app-primary">{items.length} 条隔离断言</span>
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
                <ChevronDown className="h-4 w-4 shrink-0 text-app-muted" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-app-muted" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-app-primary truncate">
                  {item.subject || item.raw || `断言 #${idx}`}
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
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  className="app-button-secondary text-xs py-1 px-2"
                  disabled={busy}
                  onClick={() => handleResolve(idx, false)}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </button>

            {expanded && (
              <div className="border-t border-red-500/20 px-4 py-3 space-y-3">
                {item.predicate && (
                  <DetailRow label="Predicate" value={item.predicate} />
                )}
                {item.object && <DetailRow label="Object" value={item.object} />}

                {(item.fix_templates?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-xs font-medium text-app-primary mb-2 flex items-center gap-1">
                      <Wrench className="h-3.5 w-3.5" />
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
