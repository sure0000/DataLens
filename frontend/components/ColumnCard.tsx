type Column = {
  column_name: string;
  data_type: string;
  semantic_type: string;
  semantic_desc: string;
  null_ratio: number;
  distinct_count: number;
  top_values: { value: string; count: number }[];
  is_usable: boolean;
  quality_metrics?: {
    duplicate_ratio?: number;
    top1_ratio?: number;
    type_valid_ratio?: number;
    format_issue_ratio?: number;
    future_time_ratio?: number;
    completeness_score?: number;
    uniqueness_score?: number;
    risk_level?: "low" | "medium" | "high";
  };
};

const SEMANTIC_TYPE_STYLE: Record<string, string> = {
  metric: "bg-[#dbeafe] text-[#1d4ed8]",
  dimension: "bg-[#dcfce7] text-[#15803d]",
  time: "bg-[#fef9c3] text-[#854d0e]",
  id: "bg-app-hover text-app-ink",
};

const RISK_STYLE = {
  high: { dot: "bg-rose-500", text: "text-rose-600" },
  medium: { dot: "bg-amber-400", text: "text-amber-600" },
  low: { dot: "bg-emerald-400", text: "text-emerald-600" },
};

export default function ColumnCard({ col, isLast = false }: { col: Column; isLast?: boolean }) {
  const quality = col.quality_metrics || {};
  const riskLevel = quality.risk_level || "low";
  const risk = RISK_STYLE[riskLevel];
  const typeStyle = SEMANTIC_TYPE_STYLE[col.semantic_type] ?? "bg-app-hover text-app-ink";
  const ratio = (value?: number) => `${((value || 0) * 100).toFixed(1)}%`;

  const metrics: { label: string; value: string }[] = [
    { label: "完整性", value: ratio(quality.completeness_score) },
    { label: "重复率", value: ratio(quality.duplicate_ratio) },
    { label: "集中度", value: ratio(quality.top1_ratio) },
  ];
  if (typeof quality.uniqueness_score === "number") {
    metrics.push({ label: "唯一性", value: ratio(quality.uniqueness_score) });
  }

  return (
    <div className={`px-4 py-3.5 ${isLast ? "" : "border-b border-app-subtle"}`}>
      {/* Row: name + badges | description */}
      <div className="flex flex-wrap items-start gap-x-4 gap-y-1 sm:flex-nowrap">
        {/* Left: name + type badges */}
        <div className="flex min-w-[160px] max-w-[220px] shrink-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="break-all font-mono text-sm font-semibold text-app-primary">
              {col.column_name}
            </span>
            {!col.is_usable && (
              <span className="rounded bg-[#fee2e2] px-1.5 py-0.5 text-[10px] font-medium text-[#991b1b]">
                不可用
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            <span className="rounded bg-app-hover px-1.5 py-0.5 font-mono text-[11px] text-app-secondary">
              {col.data_type}
            </span>
            {col.semantic_type && (
              <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${typeStyle}`}>
                {col.semantic_type}
              </span>
            )}
          </div>
        </div>

        {/* Right: description + metrics */}
        <div className="min-w-0 flex-1">
          {col.semantic_desc ? (
            <p className="break-words text-sm leading-6 text-app-ink">{col.semantic_desc}</p>
          ) : (
            <p className="text-sm text-app-muted">暂无语义描述</p>
          )}

          {/* Metrics row */}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            {/* Risk indicator */}
            <span className={`flex items-center gap-1 text-xs ${risk.text}`}>
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${risk.dot}`} />
              质量{riskLevel === "high" ? "高风险" : riskLevel === "medium" ? "中风险" : "良好"}
            </span>

            {/* Numeric metrics */}
            {metrics.map((m) => (
              <span key={m.label} className="text-xs text-app-muted">
                {m.label}
                <span className="ml-1 text-app-secondary">{m.value}</span>
              </span>
            ))}

            {/* null / distinct */}
            <span className="text-xs text-app-muted">
              null率
              <span className="ml-1 text-app-secondary">
                {((col.null_ratio ?? 0) * 100).toFixed(1)}%
              </span>
            </span>
            <span className="text-xs text-app-muted">
              distinct
              <span className="ml-1 text-app-secondary">{col.distinct_count ?? 0}</span>
            </span>
          </div>

          {/* Top values */}
          {(col.top_values ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(col.top_values ?? []).slice(0, 6).map((t, i) => (
                <span
                  key={i}
                  className="rounded border border-app-border bg-app-hover px-2 py-0.5 font-mono text-[11px] text-app-secondary"
                >
                  {String(t.value)}
                  <span className="ml-1 text-app-muted">×{t.count}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
