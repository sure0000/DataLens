"use client";

import type { MetricDef } from "./types";

interface MetricListProps {
  metrics: MetricDef[];
  loading?: boolean;
}

export default function MetricList({ metrics, loading }: MetricListProps) {
  if (loading) {
    return (
      <div className="app-card p-4 space-y-3">
        <h3 className="app-section-title">📏 指标口径</h3>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 bg-app-hover rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (metrics.length === 0) {
    return (
      <div className="app-card p-4">
        <h3 className="app-section-title mb-2">📏 指标口径</h3>
        <p className="text-sm text-app-muted">暂无指标。运行清洗流水线后，AI 将自动从文档中提取指标口径定义。</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
      <table className="app-table">
        <thead>
          <tr>
            <th className="px-3 py-2.5 text-left">指标名</th>
            <th className="px-3 py-2.5 text-left">计算公式</th>
            <th className="px-3 py-2.5 text-left">统计口径</th>
            <th className="w-28 px-3 py-2.5 text-left">关联术语</th>
            <th className="w-20 px-3 py-2.5 text-right">置信度</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.id} className="hover:bg-app-hover transition-colors">
              <td className="px-3 py-2.5">
                <p className="text-sm font-medium text-app-primary">{m.name}</p>
              </td>
              <td className="px-3 py-2.5">
                <code className="text-xs font-mono text-app-secondary line-clamp-2 block">
                  {m.formula}
                </code>
              </td>
              <td className="px-3 py-2.5">
                {m.caliber ? (
                  <p className="text-xs text-app-secondary line-clamp-2">{m.caliber}</p>
                ) : (
                  <span className="text-xs text-app-muted">—</span>
                )}
              </td>
              <td className="px-3 py-2.5">
                {m.related_terms?.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {m.related_terms.map((t) => (
                      <span
                        key={t}
                        className="app-metric-tag text-[10px] px-1 py-0.5 rounded"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-app-muted">—</span>
                )}
              </td>
              <td className="px-3 py-2.5 text-right">
                <span
                  className={`text-xs font-medium ${
                    m.confidence >= 80
                      ? "app-text-success"
                      : m.confidence >= 50
                      ? "text-amber-600"
                      : "app-text-danger"
                  }`}
                >
                  {Math.round(m.confidence)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
