"use client";

import { useState } from "react";
import { api } from "../../lib/api";

export type CopilotValidateResult = {
  ok: boolean;
  question: string;
  routing_trace: {
    concepts: { iri: string; label: string; type?: string }[];
    tables: { iri: string; name?: string; platform_id?: string }[];
    expanded_tables: { iri: string }[];
    candidate_table_ids?: number[];
    strategy?: string;
  };
  quarantine_total: number;
  matched_quarantine: {
    item_idx: number;
    reason: string;
    reason_label: string;
    subject?: string;
    object?: string;
  }[];
  fix_suggestions: {
    item_idx: number;
    reason_label: string;
    recommended_template?: string;
    recommended_params?: Record<string, number>;
    routing_table_ids?: number[];
  }[];
  auto_applied?: { ok: boolean; item_idx: number; action?: string; error?: string }[];
};

type Props = {
  kbId: number;
  subjectIri?: string | null;
  entityName?: string;
  tableId?: number;
  onApplied?: () => void;
  compact?: boolean;
};

export default function CopilotValidatePanel({
  kbId,
  subjectIri,
  entityName,
  tableId,
  onApplied,
  compact = false,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState<CopilotValidateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runValidation(autoApply: boolean) {
    if (autoApply) setApplying(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await api<CopilotValidateResult>(
        `/api/ontology/knowledge-bases/${kbId}/copilot-validate`,
        {
          method: "POST",
          body: JSON.stringify({
            subject: subjectIri || undefined,
            entity_name: entityName || undefined,
            table_id: tableId,
            auto_apply: autoApply,
          }),
        },
      );
      setResult(res);
      if (autoApply && (res.auto_applied?.length ?? 0) > 0) {
        onApplied?.();
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Copilot 验证失败");
      setResult(null);
    } finally {
      setLoading(false);
      setApplying(false);
    }
  }

  return (
    <div className={compact ? "space-y-2" : "rounded-lg border border-app-border bg-app-hover/40 p-3 space-y-3"}>
      {!compact && (
        <div>
          <p className="text-xs font-medium text-app-primary">Copilot 验证</p>
          <p className="mt-0.5 text-[11px] text-app-muted">
            通过本体路由检查 Copilot 能否解析该实体/表，并匹配隔离区待修复项。
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`app-button-secondary text-xs ${loading ? "is-loading" : ""}`}
          disabled={loading || applying}
          onClick={() => void runValidation(false)}
        >
          {compact ? "Copilot 验证" : "运行验证"}
        </button>
        {result && result.matched_quarantine.length > 0 ? (
          <button
            type="button"
            className={`app-button text-xs ${applying ? "is-loading" : ""}`}
            disabled={loading || applying}
            onClick={() => void runValidation(true)}
          >
            自动修复隔离项
          </button>
        ) : null}
      </div>
      {error ? <p className="text-xs text-red-600 dark:text-red-400">{error}</p> : null}
      {result ? (
        <div className="space-y-2 text-xs text-app-secondary">
          <p>
            路由命中 {result.routing_trace.concepts.length} 个概念、
            {result.routing_trace.tables.length} 张表
            {result.routing_trace.candidate_table_ids?.length
              ? `（候选 ID: ${result.routing_trace.candidate_table_ids.join(", ")}）`
              : ""}
          </p>
          {result.matched_quarantine.length === 0 ? (
            <p className="text-app-muted">
              隔离区共 {result.quarantine_total} 条，无与当前实体/表匹配的待修复项。
            </p>
          ) : (
            <ul className="space-y-1.5">
              {result.fix_suggestions.map((s) => (
                <li key={s.item_idx} className="rounded border border-app-border px-2 py-1.5">
                  <span className="font-medium text-app-primary">#{s.item_idx}</span> {s.reason_label}
                  {s.recommended_template ? (
                    <span className="ml-1 text-app-muted">
                      → 建议 {s.recommended_template}
                      {s.recommended_params?.table_id
                        ? ` (表 ${s.recommended_params.table_id})`
                        : ""}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {result.auto_applied && result.auto_applied.length > 0 ? (
            <p className="text-emerald-700 dark:text-emerald-400">
              已处理 {result.auto_applied.filter((a) => a.ok).length} 条隔离项
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
