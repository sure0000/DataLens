"use client";

import type { BusinessTerm } from "./types";

interface TermListProps {
  terms: BusinessTerm[];
  loading?: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  metric: "💰 度量",
  enum: "📋 枚举",
  time: "📅 时间",
  dimension: "👤 维度",
  other: "🏷️ 其他",
};

export default function TermList({ terms, loading }: TermListProps) {
  if (loading) {
    return (
      <div className="app-card p-4 space-y-3">
        <h3 className="app-section-title">📑 业务术语</h3>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 bg-app-hover rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (terms.length === 0) {
    return (
      <div className="app-card p-4">
        <h3 className="app-section-title mb-2">📑 业务术语</h3>
        <p className="text-sm text-app-muted">暂无术语。运行清洗流水线后，AI 将自动从文档中提取业务术语。</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-app-border bg-white shadow-sm">
      <table className="app-table">
        <thead>
          <tr>
            <th className="px-3 py-2.5 text-left">术语</th>
            <th className="w-24 px-3 py-2.5 text-left">类型</th>
            <th className="px-3 py-2.5 text-left">定义</th>
            <th className="w-28 px-3 py-2.5 text-left">关联字段</th>
            <th className="w-20 px-3 py-2.5 text-right">置信度</th>
          </tr>
        </thead>
        <tbody>
          {terms.map((t) => (
            <tr key={t.id} className="hover:bg-app-hover transition-colors">
              <td className="px-3 py-2.5">
                <p className="text-sm font-medium text-app-primary">{t.name}</p>
              </td>
              <td className="px-3 py-2.5">
                <span className="text-xs text-app-secondary">
                  {TYPE_LABELS[t.type] || t.type}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <p className="text-xs text-app-secondary line-clamp-2">{t.definition}</p>
              </td>
              <td className="px-3 py-2.5">
                {t.related_fields?.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {t.related_fields.map((f) => (
                      <code
                        key={f}
                        className="text-[10px] font-mono bg-app-hover px-1 py-0.5 rounded"
                      >
                        {f}
                      </code>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-app-muted">—</span>
                )}
              </td>
              <td className="px-3 py-2.5 text-right">
                <span
                  className={`text-xs font-medium ${
                    t.confidence >= 80
                      ? "text-emerald-600"
                      : t.confidence >= 50
                      ? "text-amber-600"
                      : "text-rose-500"
                  }`}
                >
                  {Math.round(t.confidence)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
