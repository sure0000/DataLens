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

/** 规范化物理库类型名，用于判断是否与 semantic_type 重复 */
function squashPhysicalType(s: string): string {
  return (s || "")
    .toLowerCase()
    .replace(/\(\s*\d+\s*(?:,\s*\d+\s*)?\)/g, "")
    .replace(/\s+without\s+time\s+zone\b/gi, "")
    .replace(/\s+with\s+time\s+zone\b/gi, "")
    .replace(/\s+/g, " ")
    .replace(/character varying/gi, "varchar")
    .replace(/\binteger\b/gi, "int")
    .replace(/\bint4\b/gi, "int")
    .replace(/\bint8\b/gi, "bigint")
    .replace(/\bint2\b/gi, "smallint")
    .trim();
}

/** LLM 有时把物理类型误写入 type 字段，与左侧 data_type 标签重复（语义四类不算重复） */
function isRedundantSemanticTypeLabel(semantic: string, dataType: string): boolean {
  const semLower = (semantic || "").trim().toLowerCase();
  if (new Set(["metric", "dimension", "time", "id"]).has(semLower)) return false;
  const a = squashPhysicalType(semantic);
  const b = squashPhysicalType(dataType);
  return !!a && !!b && a === b;
}

/** 去掉描述开头对物理类型的重复表述（左侧已有 data_type 标签） */
function trimDuplicateTypePreamble(desc: string, physicalType: string): string {
  const d = (desc || "").trim();
  const pt = (physicalType || "").trim();
  if (!d || !pt) return desc;
  const esc = pt.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let next = d
    .replace(new RegExp(`^${esc}\\s*[，,。.；;：:]?\\s*`), "")
    .replace(new RegExp(`^(数据)?类型[是为]?[:：]?\\s*${esc}\\s*[，,。.；;：]?\\s*`, "i"), "")
    .replace(
      new RegExp(`^(该字段|本字段|此字段)?(的)?(数据)?类型[是为]?[:：]?\\s*${esc}\\s*[，,。.；;：]?\\s*`, "i"),
      ""
    )
    .trim();
  return next || desc;
}

export default function ColumnCard({ col, isLast = false }: { col: Column; isLast?: boolean }) {
  const quality = col.quality_metrics || {};
  const riskLevel = quality.risk_level || "low";
  const risk = RISK_STYLE[riskLevel];
  const showSemanticBadge = !!(col.semantic_type && !isRedundantSemanticTypeLabel(col.semantic_type, col.data_type));
  const typeStyle = SEMANTIC_TYPE_STYLE[col.semantic_type] ?? "bg-app-hover text-app-ink";
  const displayDesc = trimDuplicateTypePreamble(col.semantic_desc || "", col.data_type || "");
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
            {showSemanticBadge && (
              <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${typeStyle}`}>
                {col.semantic_type}
              </span>
            )}
          </div>
        </div>

        {/* Right: description + metrics */}
        <div className="min-w-0 flex-1">
          {displayDesc ? (
            <p className="break-words text-sm leading-6 text-app-ink">{displayDesc}</p>
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
