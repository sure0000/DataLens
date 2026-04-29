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

export default function ColumnCard({ col }: { col: Column }) {
  const quality = col.quality_metrics || {};
  const riskLevel = quality.risk_level || "low";
  const riskClass =
    riskLevel === "high"
      ? "border border-rose-300/60 bg-rose-50 text-rose-700"
      : riskLevel === "medium"
        ? "border border-amber-300/60 bg-amber-50 text-amber-700"
        : "border border-emerald-300/60 bg-emerald-50 text-emerald-700";
  const ratio = (value?: number) => `${((value || 0) * 100).toFixed(2)}%`;

  return (
    <div className="app-card p-4">
      <div className="flex flex-wrap gap-2">
        <h4 className="break-all font-semibold text-[#111827]">{col.column_name}</h4>
        <span className="rounded bg-[#f3f4f6] px-2 text-xs text-[#4b5563]">{col.data_type}</span>
        <span className="rounded bg-[#eef2ff] px-2 text-xs text-[#4338ca]">{col.semantic_type}</span>
        <span className={`rounded px-2 text-xs ${riskClass}`}>质量风险: {riskLevel}</span>
      </div>
      <p className="mt-2 break-words text-sm text-[#374151]">{col.semantic_desc}</p>
      <p className="mt-2 text-xs text-[#6b7280]">
        null率: {col.null_ratio ?? 0} | distinct: {col.distinct_count ?? 0} | 可用:
        {col.is_usable ? "是" : "否"}
      </p>
      <div className="mt-2 grid gap-1 text-xs text-[#6b7280] md:grid-cols-2">
        <span>完整性评分: {ratio(quality.completeness_score)}</span>
        <span>唯一性评分: {ratio(quality.uniqueness_score)}</span>
        <span>重复率: {ratio(quality.duplicate_ratio)}</span>
        <span>头部集中度: {ratio(quality.top1_ratio)}</span>
        {typeof quality.type_valid_ratio === "number" && <span>类型合法率: {ratio(quality.type_valid_ratio)}</span>}
        {typeof quality.format_issue_ratio === "number" && <span>格式异常率: {ratio(quality.format_issue_ratio)}</span>}
        {typeof quality.future_time_ratio === "number" && <span>未来时间占比: {ratio(quality.future_time_ratio)}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {(col.top_values ?? []).slice(0, 5).map((t, i) => (
          <span key={i} className="rounded border border-[#e5e7eb] bg-[#f9fafb] px-2 py-1 text-[#374151]">
            {String(t.value)} ({t.count})
          </span>
        ))}
      </div>
    </div>
  );
}
