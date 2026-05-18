"use client";

import { useEffect } from "react";
import type { Entry } from "./types";

interface EntryViewModalProps {
  entry: Entry | null;
  onClose: () => void;
}

export default function EntryViewModal({ entry, onClose }: EntryViewModalProps) {
  useEffect(() => {
    if (!entry) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [entry, onClose]);

  if (!entry) return null;

  return (
    <div className="app-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="app-card flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden p-5"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 shrink-0 flex items-start justify-between gap-2">
          <h2 className="app-section-title pr-6">{entry.title}</h2>
          <button className="app-control-button shrink-0" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          <pre className="app-text-secondary-strong whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">
            {entry.body || "（空正文）"}
          </pre>
        </div>
      </div>
    </div>
  );
}
