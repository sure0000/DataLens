"use client";

import { memo } from "react";
import { compactCopilotTraceSteps, type PipelineTraceStep } from "../../lib/chatSessions";

const LIVE_STEP_IDS = new Set(["ontology_match", "sql_decision", "reasoning_1", "reasoning_4", "reasoning_7", "live_intent", "live_prep"]);

type Props = {
  steps: PipelineTraceStep[];
};

function previewDetail(detail: string | undefined, max = 120): string {
  const t = (detail || "").trim();
  if (!t) return "";
  const firstLine = t.split(/\n/).find((l) => l.trim()) || t;
  return firstLine.length > max ? `${firstLine.slice(0, max)}…` : firstLine;
}

const CopilotLiveTrace = memo(function CopilotLiveTrace({ steps }: Props) {
  const visible = compactCopilotTraceSteps(steps).filter((s) => LIVE_STEP_IDS.has(s.id) || s.id.startsWith("live_"));
  if (!visible.length) return null;

  return (
    <div className="mb-2 rounded-md border border-app-border/80 bg-app-hover/40 px-2.5 py-2" aria-live="polite">
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-app-secondary">推理进度</p>
      <ol className="m-0 list-none space-y-1 p-0">
        {visible.map((s, idx) => {
          const isLast = idx === visible.length - 1;
          const preview = previewDetail(s.detail);
          return (
            <li key={`${s.id}-${idx}`} className="flex items-start gap-2 text-xs">
              <span
                className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${isLast ? "bg-app-primary motion-safe:animate-pulse" : "bg-app-muted"}`}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <span className="font-medium text-app-primary">{s.label}</span>
                {preview ? <p className="mt-0.5 line-clamp-2 text-app-muted">{preview}</p> : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
});

export default CopilotLiveTrace;
