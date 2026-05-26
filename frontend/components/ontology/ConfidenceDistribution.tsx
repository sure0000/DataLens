"use client";

import { useMemo } from "react";

interface ConfidenceBucket {
  range: string;
  min: number;
  max: number;
  count: number;
  label: string;
}

interface ConfidenceDistributionProps {
  items: Array<{ confidence?: number; name?: string; label?: string }>;
  title?: string;
}

function buildBuckets(
  items: Array<{ confidence?: number }>,
): ConfidenceBucket[] {
  const ranges: { min: number; max: number; label: string }[] = [
    { min: 90, max: 101, label: "90-100" },
    { min: 75, max: 90, label: "75-89" },
    { min: 50, max: 75, label: "50-74" },
    { min: 25, max: 50, label: "25-49" },
    { min: 0, max: 25, label: "0-24" },
  ];

  return ranges.map((r) => {
    const count = items.filter(
      (item) =>
        (item.confidence ?? 0) >= r.min &&
        (item.confidence ?? 0) < r.max,
    ).length;
    return { ...r, range: r.label, count };
  });
}

const BUCKET_COLORS = [
  "bg-emerald-500",
  "bg-emerald-400",
  "bg-amber-400",
  "bg-orange-400",
  "bg-red-400",
];

export default function ConfidenceDistribution({
  items,
  title,
}: ConfidenceDistributionProps) {
  const buckets = useMemo(() => buildBuckets(items), [items]);
  const maxCount = Math.max(...buckets.map((b) => b.count), 1);

  const total = items.length;
  const highConfidence = items.filter((i) => (i.confidence ?? 0) >= 75).length;
  const highRate = total > 0 ? Math.round((highConfidence / total) * 100) : 0;

  if (total === 0) {
    return (
      <p className="text-sm text-app-muted px-3 py-4">
        暂无置信度数据可供分析。
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {title && (
        <h4 className="text-sm font-medium text-app-primary">{title}</h4>
      )}

      {/* Summary */}
      <div className="flex items-center gap-4 text-sm">
        <span className="text-app-muted">
          总计 <strong className="text-app-primary">{total}</strong> 条
        </span>
        <span className="text-app-muted">
          高置信 (&ge;75%)：{" "}
          <strong
            className={
              highRate >= 80
                ? "text-emerald-600 dark:text-emerald-400"
                : highRate >= 50
                  ? "text-amber-600"
                  : "text-red-500"
            }
          >
            {highRate}%
          </strong>
        </span>
      </div>

      {/* Bar chart */}
      <div className="space-y-1.5">
        {buckets.map((bucket, i) => (
          <div key={bucket.range} className="flex items-center gap-2">
            <span className="w-14 text-right text-[11px] text-app-muted shrink-0">
              {bucket.range}
            </span>
            <div className="flex-1 h-5 bg-app-surface-subtle rounded-md overflow-hidden relative">
              <div
                className={`h-full rounded-md transition-all ${BUCKET_COLORS[i]} ${bucket.count === 0 ? "opacity-0" : "opacity-80"}`}
                style={{
                  width: `${Math.max((bucket.count / maxCount) * 100, bucket.count > 0 ? 2 : 0)}%`,
                }}
              />
            </div>
            <span className="w-8 text-right text-xs font-medium text-app-primary shrink-0">
              {bucket.count}
            </span>
          </div>
        ))}
      </div>

      {/* Low confidence items */}
      {(() => {
        const lowItems = items.filter((i) => (i.confidence ?? 0) < 50);
        if (lowItems.length === 0) return null;

        return (
          <details className="mt-3">
            <summary className="text-xs text-app-muted cursor-pointer hover:text-app-primary">
              低置信条目（&lt;50%）：{lowItems.length} 条
            </summary>
            <ul className="mt-2 space-y-0.5 max-h-48 overflow-y-auto">
              {lowItems.map((item, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between text-[11px] px-2 py-1 rounded hover:bg-app-surface-hover"
                >
                  <span className="text-app-primary truncate">
                    {item.name || item.label || `条目 #${i + 1}`}
                  </span>
                  <span className="shrink-0 ml-3 text-red-500 font-medium">
                    {item.confidence ?? "—"}%
                  </span>
                </li>
              ))}
            </ul>
          </details>
        );
      })()}
    </div>
  );
}
