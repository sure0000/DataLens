"use client";

import { STATUS_LABELS } from "../../lib/ontologyTypes";

export default function OntologyStatusBadge({ status }: { status: string }) {
  const meta = STATUS_LABELS[status] || { label: status, tone: "muted" as const };
  const cls =
    meta.tone === "success"
      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      : meta.tone === "warn"
        ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
        : meta.tone === "danger"
          ? "bg-red-500/10 text-red-600 dark:text-red-400"
          : "bg-app-hover text-app-muted";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {meta.label}
    </span>
  );
}
