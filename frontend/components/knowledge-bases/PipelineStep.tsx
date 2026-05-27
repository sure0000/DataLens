"use client";

import { PipelineStepIcon, PipelineStatusBadge, pipelineCardStatusToIcon } from "../icons";
import { badgeExclusive, pipelineBadgeClass, pipelineStepClass } from "../../lib/themeClasses";

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
  const stepClass = pipelineStepClass(status);
  const badgeClass = pipelineBadgeClass(status);

  return (
    <div className={`app-card flex flex-col gap-2.5 p-4 min-w-[180px] max-w-[220px] ${stepClass}`}>
      <div className="flex items-center gap-2">
        <PipelineStepIcon status={pipelineCardStatusToIcon(status)} className="h-5 w-5" />

        <span className="text-sm font-semibold text-app-primary truncate">{label}</span>
        {isExclusive && (
          <span className={`shrink-0 rounded-full px-1.5 py-0 text-[10px] font-medium ${badgeExclusive}`}>
            专属
          </span>
        )}
      </div>

      <p className="text-xs text-app-muted leading-relaxed">{description}</p>

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

      <span className={badgeClass}>
        <PipelineStatusBadge status={status} />
      </span>
    </div>
  );
}
