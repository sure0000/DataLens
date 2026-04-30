"use client";

import { useEffect, useRef } from "react";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  danger = false,
  loading = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    setTimeout(() => cancelRef.current?.focus(), 0);
    return () => {
      prev?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[#111827]/35 p-4 backdrop-blur-[2px]"
      role="presentation"
      onClick={onCancel}
    >
      <div
        className="app-modal-surface app-chatgpt-dialog w-full max-w-[420px] rounded-2xl p-5 sm:p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-dialog-title" className="text-[16px] font-semibold text-[var(--app-text-primary)]">
          {title}
        </h3>
        {description ? <p className="mt-2 text-[14px] leading-6 text-[var(--app-text-secondary)]">{description}</p> : null}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button ref={cancelRef} className="app-dialog-btn app-dialog-btn-secondary w-full sm:w-auto" onClick={onCancel} disabled={loading}>
            {cancelText}
          </button>
          <button className={`app-dialog-btn ${danger ? "app-dialog-btn-danger" : "app-dialog-btn-primary"} w-full sm:w-auto`} onClick={onConfirm} disabled={loading}>
            {loading ? "处理中..." : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
