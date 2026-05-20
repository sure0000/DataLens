"use client";

import type { PipelineStats } from "./types";

interface DetailStatsPanelProps {
  stats: PipelineStats | null;
  loading?: boolean;
}

export default function DetailStatsPanel({ stats, loading }: DetailStatsPanelProps) {
  if (loading) {
    return (
      <aside className="w-72 shrink-0 hidden lg:block">
        <div className="app-card p-4 space-y-4 animate-pulse">
          <div className="h-4 bg-app-hover rounded w-20" />
          <div className="space-y-2">
            <div className="h-3 bg-app-hover rounded w-full" />
            <div className="h-3 bg-app-hover rounded w-3/4" />
            <div className="h-3 bg-app-hover rounded w-1/2" />
          </div>
        </div>
      </aside>
    );
  }

  if (!stats) {
    return (
      <aside className="w-72 shrink-0 hidden lg:block">
        <div className="app-card p-4">
          <p className="text-sm text-app-muted">暂无统计信息</p>
        </div>
      </aside>
    );
  }

  const totalDocs = stats.total_documents;
  const indexed = stats.indexed_documents;
  const syncPercent = totalDocs > 0 ? Math.round((indexed / totalDocs) * 100) : 0;

  return (
    <aside className="w-72 shrink-0 hidden lg:block">
      <div className="app-card p-4 space-y-4">
        {/* 文档同步进度 */}
        <div>
          <h3 className="text-sm font-semibold text-app-primary mb-2 flex items-center gap-1.5">
            <svg className="h-4 w-4 text-app-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            同步统计
          </h3>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between text-app-secondary">
              <span>总文件</span>
              <span className="font-medium text-app-primary">{totalDocs}</span>
            </div>
            <div className="flex justify-between text-app-secondary">
              <span>已处理</span>
              <span className="font-medium app-text-success">{indexed} ({syncPercent}%)</span>
            </div>
            <div className="flex justify-between text-app-secondary">
              <span>待处理</span>
              <span className="font-medium text-app-muted">{totalDocs - indexed}</span>
            </div>
          </div>
          {/* 进度条 */}
          <div className="mt-2 h-1.5 w-full rounded-full bg-app-hover overflow-hidden">
            <div
              className="h-full rounded-full app-progress-fill-success transition-all duration-500"
              style={{ width: `${syncPercent}%` }}
            />
          </div>
        </div>

        <div className="border-t border-app-border" />

        {/* 清洗状态 */}
        <div>
          <h3 className="text-sm font-semibold text-app-primary mb-2 flex items-center gap-1.5">
            <svg className="h-4 w-4 text-app-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 11 12 14 22 4" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
            清洗状态
          </h3>
          <div className="space-y-1.5 text-xs">
            <StatusRow
              label="术语提取"
              done={stats.terms_by_status?.["approved"] ?? 0}
              total={stats.term_count}
            />
            <StatusRow
              label="指标口径"
              done={stats.metrics_by_status?.["approved"] ?? 0}
              total={stats.metric_count}
            />
            {stats.lineage_stats && (stats.lineage_stats.done + stats.lineage_stats.processing + stats.lineage_stats.pending) > 0 && (
              <StatusRow
                label="数据血缘"
                done={stats.lineage_stats.done}
                total={
                  stats.lineage_stats.done + stats.lineage_stats.processing + stats.lineage_stats.pending
                }
              />
            )}
          </div>
        </div>

        {/* 最近清洗 */}
        {stats.last_pipeline_run && (
          <>
            <div className="border-t border-app-border" />
            <div>
              <h3 className="text-sm font-semibold text-app-primary mb-2 flex items-center gap-1.5">
                <svg className="h-4 w-4 text-app-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                最近清洗
              </h3>
              <div className="space-y-1 text-xs text-app-secondary">
                <p>
                  状态:{" "}
                  <span
                    className={
                      stats.last_pipeline_run.status === "completed"
                        ? "app-text-success font-medium"
                        : stats.last_pipeline_run.status === "failed"
                        ? "app-text-danger font-medium"
                        : "app-text-info font-medium"
                    }
                  >
                    {stats.last_pipeline_run.status === "completed" ? "✓ 完成" : stats.last_pipeline_run.status === "failed" ? "✗ 失败" : "◐ 运行中"}
                  </span>
                </p>
                {stats.last_pipeline_run.started_at && (
                  <p>开始: {new Date(stats.last_pipeline_run.started_at).toLocaleString()}</p>
                )}
                {stats.last_pipeline_run.completed_at && (
                  <p>完成: {new Date(stats.last_pipeline_run.completed_at).toLocaleString()}</p>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

function StatusRow({ label, done, total }: { label: string; done: number; total: number }) {
  const status: "done" | "progress" | "waiting" =
    total > 0 && done >= total ? "done" : total > 0 ? "progress" : "waiting";

  return (
    <div className="flex items-center justify-between">
      <span className="text-app-secondary">{label}</span>
      <span
        className={`font-medium ${
          status === "done" ? "app-text-success" : status === "progress" ? "app-text-info" : "text-app-muted"
        }`}
      >
        {status === "done" ? `✓ ${done}条` : status === "progress" ? `◐ ${done}/${total}` : "○ —"}
      </span>
    </div>
  );
}
