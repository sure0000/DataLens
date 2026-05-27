"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useEscapeKey } from "../../hooks/useEscapeKey";

export type SemanticCleanResumeOptions = {
  can_resume: boolean;
  resume_from_run_id?: number;
  failed_at_step?: string | null;
  failed_at_step_label?: string | null;
  cached_steps?: string[];
  cached_step_labels?: string[];
  failure_reason?: string | null;
  completed_at?: string | null;
};

type SemanticCleanChoiceDialogProps = {
  open: boolean;
  sourceLabel: string;
  options: SemanticCleanResumeOptions | null;
  loading?: boolean;
  onResume: () => void;
  onRestart: () => void;
  onCancel: () => void;
};

export default function SemanticCleanChoiceDialog({
  open,
  sourceLabel,
  options,
  loading = false,
  onResume,
  onRestart,
  onCancel,
}: SemanticCleanChoiceDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => cancelRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  useEscapeKey(onCancel, open);

  if (!open || !options?.can_resume) return null;

  const cached = options.cached_step_labels?.length
    ? options.cached_step_labels.join("、")
    : null;
  const failedLabel = options.failed_at_step_label || options.failed_at_step || "未知步骤";

  const surface = (
    <div className="app-modal-backdrop app-modal-backdrop--front" role="presentation" onClick={onCancel}>
      <div
        className="app-modal-surface app-chatgpt-dialog w-full max-w-[440px] rounded-2xl p-5 sm:p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="semantic-clean-choice-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="semantic-clean-choice-title" className="text-[16px] font-semibold text-[var(--app-text-primary)]">
          语义清洗：续跑还是重新跑？
        </h3>
        <p className="mt-2 text-[14px] leading-6 text-[var(--app-text-secondary)]">
          「{sourceLabel}」有一次未完成的抽取（run #{options.resume_from_run_id}）。
          {cached ? (
            <>
              已完成并可复用：<span className="text-app-primary">{cached}</span>。
            </>
          ) : (
            <span className="block">上次运行未保存分步缓存，续跑时可能仍需重做部分 LLM 抽取。</span>
          )}
          {options.failure_reason ? (
            <span className="mt-1 block text-[13px] text-amber-700">{options.failure_reason}</span>
          ) : (
            <span className="mt-1 block">失败位置：{failedLabel}</span>
          )}
        </p>
        <ul className="mt-3 space-y-1.5 text-[13px] text-app-muted list-disc pl-4">
          <li>
            <strong className="font-medium text-app-secondary">续跑</strong>：跳过已缓存步骤，从失败处继续（省 LLM 调用）
          </li>
          <li>
            <strong className="font-medium text-app-secondary">重新跑</strong>：忽略上次进度，完整重跑 8 步抽取
          </li>
        </ul>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            className="app-dialog-btn app-dialog-btn-secondary w-full sm:w-auto"
            onClick={onCancel}
            disabled={loading}
          >
            取消
          </button>
          <button
            type="button"
            className="app-dialog-btn app-dialog-btn-secondary w-full sm:w-auto"
            onClick={onRestart}
            disabled={loading}
          >
            {loading ? "启动中…" : "重新跑"}
          </button>
          <button
            type="button"
            className="app-dialog-btn app-dialog-btn-primary w-full sm:w-auto"
            onClick={onResume}
            disabled={loading}
          >
            {loading ? "启动中…" : "续跑"}
          </button>
        </div>
      </div>
    </div>
  );

  return typeof document !== "undefined" ? createPortal(surface, document.body) : null;
}
