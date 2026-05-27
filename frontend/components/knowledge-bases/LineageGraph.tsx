"use client";

import { PipelineStatusBadge, PipelineStepIcon } from "../icons";
import type { LineageData } from "./types";

interface LineageGraphProps {
  data: LineageData | null;
}

const LAYER_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  ODS: { bg: "#dbeafe", border: "#93c5fd", text: "#1d4ed8" },
  DWD: { bg: "#dcfce7", border: "#86efac", text: "#15803d" },
  DWS: { bg: "#fef9c3", border: "#fde047", text: "#a16207" },
  ADS: { bg: "#fee2e2", border: "#fca5a5", text: "#dc2626" },
};

const FALLBACK_COLOR = { bg: "#f3f4f6", border: "#d1d5db", text: "#6b7280" };

export default function LineageGraph({ data }: LineageGraphProps) {
  const sourceLabel = data?.source === "rdf" ? "RDF 关系图" : "代码库";
  if (!data || (data.layers.length === 0 && data.edges.length === 0)) {
    return (
      <section className="mt-4 app-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">🔗</span>
          <h2 className="app-section-title">数据血缘</h2>
          <span className="text-xs text-app-muted">— {sourceLabel}</span>
        </div>
        <p className="text-sm text-app-muted">
          暂未解析到数据血缘关系。添加 Git 代码源并同步后，系统将自动分析表间依赖。
        </p>
      </section>
    );
  }

  const totalEdges = data.stats.done + data.stats.processing + data.stats.pending;

  return (
    <section className="mt-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">🔗</span>
        <h2 className="app-section-title">数据血缘</h2>
        <span className="text-xs text-app-muted">— 来自 {sourceLabel}</span>
      </div>

      <div className="app-card p-4 overflow-x-auto">
        {data.layers.length === 0 && data.edges.length > 0 ? (
          <div className="space-y-2">
            {data.edges.slice(0, 40).map((edge, idx) => (
              <div key={`${edge.source ?? edge.source_table}-${edge.target ?? edge.target_table}-${idx}`} className="rounded-lg border border-app-border px-3 py-2 text-xs text-app-secondary">
                <span className="font-mono break-all">{edge.source ?? edge.source_table}</span>
                <span className="mx-2 text-app-muted">→</span>
                <span className="font-mono break-all">{edge.target ?? edge.target_table}</span>
              </div>
            ))}
            {data.edges.length > 40 ? (
              <p className="text-[11px] text-app-muted">仅展示前 40 条，更多请使用专家视图 SPARQL。</p>
            ) : null}
          </div>
        ) : (
          <>
        {/* 分层节点 */}
        <div className="flex items-start gap-4 min-w-max">
          {data.layers.map((layer, li) => (
            <div key={layer.name} className="flex items-start gap-4">
              <div className="flex flex-col gap-1.5 min-w-[140px]">
                <span className="text-xs font-semibold text-app-muted text-center py-1">
                  {layer.name}
                </span>
                {layer.nodes.map((node) => {
                  const colors = LAYER_COLORS[layer.name] || FALLBACK_COLOR;
                  const isDone = node.status === "done";
                  const isProcessing = node.status === "processing";
                  return (
                    <div
                      key={node.id}
                      className="rounded-lg border px-3 py-2 text-xs font-mono text-center"
                      style={{
                        backgroundColor: isDone ? colors.bg : isProcessing ? `${colors.bg}80` : "#f9fafb",
                        borderColor: colors.border,
                        color: colors.text,
                        opacity: node.status === "pending" ? 0.6 : 1,
                      }}
                      title={node.name}
                    >
                      <span className="truncate block max-w-[120px]">{node.name}</span>
                      {isProcessing && (
                        <span className="text-[10px] text-amber-600">处理中</span>
                      )}
                    </div>
                  );
                })}
              </div>
              {li < data.layers.length - 1 && (
                <svg className="h-4 w-8 shrink-0 mt-8 text-app-muted" viewBox="0 0 32 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M0 8 L16 8" />
                  <polyline points="10 4 16 8 10 12" />
                </svg>
              )}
            </div>
          ))}
        </div>
          </>
        )}

        {/* 统计 */}
        <div className="flex items-center gap-4 mt-4 pt-3 border-t border-app-border">
          <span className="text-xs text-app-muted">
            共 {totalEdges} 条边
          </span>
          <span className="text-xs app-text-success inline-flex items-center gap-1">
            <PipelineStatusBadge status="done" suffix={`${data.stats.done} 条`} iconClassName="h-3 w-3" />
          </span>
          {data.stats.processing > 0 && (
            <span className="text-xs text-amber-600 inline-flex items-center gap-1">
              <PipelineStepIcon status="running" className="h-3 w-3" />
              处理中 {data.stats.processing} 条
            </span>
          )}
          {data.stats.pending > 0 && (
            <span className="text-xs text-app-muted inline-flex items-center gap-1">
              <PipelineStepIcon status="pending" className="h-3 w-3" />
              待处理 {data.stats.pending} 条
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
