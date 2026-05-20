"use client";

import { useEffect } from "react";
import { toastToneClass } from "../lib/themeClasses";

type ToastProps = {
  message: string;
  tone?: "success" | "error" | "info";
  duration?: number;
  onClose: () => void;
};

export default function Toast({ message, tone = "success", duration = 4000, onClose }: ToastProps) {
  useEffect(() => {
    if (!message) return;
    if (duration <= 0) return;
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [message, duration, onClose]);

  if (!message) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[150]" role="status" aria-live="polite">
      <div className={`app-surface-panel pointer-events-auto flex max-w-lg items-start gap-3 rounded-xl px-3 py-2 text-sm backdrop-blur ${toastToneClass(tone)}`}>
        <p className="max-h-[min(70vh,28rem)] flex-1 overflow-y-auto break-words whitespace-pre-wrap">{message}</p>
        <button className="app-control-button !min-h-0 !px-1.5 !py-0.5" onClick={onClose} aria-label="关闭提示">
          关闭
        </button>
      </div>
    </div>
  );
}
