"use client";

/** 单个流水线步骤卡片 — 匹配 V2 设计规范 */
export interface PipelineStepData {
  id: string;
  label: string;
  description: string;
  status: "done" | "progress" | "waiting" | "skipped";
  isExclusive: boolean;
  totalCount?: number;
  doneCount?: number;
}

interface PipelineStepProps {
  step: PipelineStepData;
}

export default function PipelineStep({ step }: PipelineStepProps) {
  const { status, label, description, totalCount, doneCount, isExclusive } = step;

  const bgClass =
    status === "done"
      ? "bg-emerald-50 border-emerald-200"
      : status === "progress"
      ? "bg-blue-50 border-blue-200"
      : status === "skipped"
      ? "bg-app-hover border-app-border opacity-60"
      : "bg-app-hover border-app-border";

  return (
    <div className={`app-card flex flex-col gap-2.5 p-4 min-w-[180px] max-w-[220px] ${bgClass}`}>
      {/* 状态图标 + 标签 */}
      <div className="flex items-center gap-2">
        {status === "done" && (
          <svg
            className="h-5 w-5 shrink-0 text-emerald-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        )}
        {status === "progress" && (
          <svg
            className="h-5 w-5 shrink-0 animate-spin text-blue-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 12a9 9 0 11-6.219-8.56" />
          </svg>
        )}
        {status === "waiting" && (
          <svg
            className="h-5 w-5 shrink-0 text-app-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
          </svg>
        )}
        {status === "skipped" && (
          <svg
            className="h-5 w-5 shrink-0 text-app-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        )}

        <span className="text-sm font-semibold text-app-primary truncate">{label}</span>
        {isExclusive && (
          <span className="shrink-0 rounded-full bg-indigo-100 px-1.5 py-0 text-[10px] font-medium text-indigo-600">
            专属
          </span>
        )}
      </div>

      {/* 状态描述 */}
      <p className="text-xs text-app-muted leading-relaxed">{description}</p>

      {/* 计数 */}
      {totalCount != null && (
        <p className="text-xs text-app-secondary">
          {totalCount > 0
            ? status === "done"
              ? `已完成 ${doneCount ?? totalCount} 条`
              : status === "progress"
              ? `进行中 ${doneCount ?? 0}/${totalCount}`
              : `${totalCount} 条待处理`
            : status === "done"
            ? "无结果"
            : null}
        </p>
      )}

      {/* 状态标签 */}
      <span
        className={`inline-flex items-center self-start rounded-full border px-2 py-0.5 text-[11px] font-medium ${
          status === "done"
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : status === "progress"
            ? "border-blue-200 bg-blue-50 text-blue-700"
            : status === "skipped"
            ? "border-app-border bg-white text-app-muted"
            : "border-app-border bg-white text-app-muted"
        }`}
      >
        {status === "done" ? "✓ 完成" : status === "progress" ? "◐ 进行中" : status === "skipped" ? "— 跳过" : "○ 待开始"}
      </span>
    </div>
  );
}
