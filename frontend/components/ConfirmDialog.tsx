"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  confirmName?: string;
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
  confirmName,
  danger = false,
  loading = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [nameInput, setNameInput] = useState("");

  useEffect(() => {
    if (!open) return;
    setNameInput("");
    const prev = document.activeElement as HTMLElement | null;
    setTimeout(() => {
      if (confirmName && inputRef.current) {
        inputRef.current.focus();
      } else {
        cancelRef.current?.focus();
      }
    }, 0);
    return () => {
      prev?.focus();
    };
  }, [open, confirmName]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const surface = (
    <div className="app-modal-backdrop app-modal-backdrop--front" role="presentation" onClick={onCancel}>
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
        {confirmName ? (
          <div className="mt-4">
            <input
              ref={inputRef}
              className="app-input w-full"
              placeholder={`输入「${confirmName}」以确认`}
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && nameInput.trim() === confirmName && !loading) {
                  onConfirm();
                }
              }}
            />
          </div>
        ) : null}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button ref={cancelRef} className="app-dialog-btn app-dialog-btn-secondary w-full sm:w-auto" onClick={onCancel} disabled={loading}>
            {cancelText}
          </button>
          <button
            className={`app-dialog-btn ${danger ? "app-dialog-btn-danger" : "app-dialog-btn-primary"} w-full sm:w-auto`}
            onClick={onConfirm}
            disabled={loading || (!!confirmName && nameInput.trim() !== confirmName)}
          >
            {loading ? "处理中..." : confirmText}
          </button>
        </div>
      </div>
    </div>
  );

  return typeof document !== "undefined" ? createPortal(surface, document.body) : null;
}
