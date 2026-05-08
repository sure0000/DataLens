import type { PipelineTraceStep } from "../lib/chatSessions";

type Props = {
  steps: PipelineTraceStep[];
  /** 加载中紧凑排版 */
  compact?: boolean;
};

export default function CopilotExecutionTrace({ steps, compact }: Props) {
  if (!steps.length) return null;
  return (
    <div
      className={`rounded-xl border border-app-border bg-app-chip/60 ${
        compact ? "px-2.5 py-2" : "px-3 py-2.5"
      }`}
    >
      <p className={`font-semibold text-app-secondary ${compact ? "mb-1.5 text-[11px]" : "mb-2 text-xs"}`}>
        执行过程：从问题到回答
      </p>
      <ol className={`space-y-2 ${compact ? "space-y-1.5" : ""}`}>
        {steps.map((s, i) => (
          <li key={`${s.id}-${i}`} className="flex gap-2">
            <span
              className={`mt-0.5 flex shrink-0 items-center justify-center rounded-full bg-app-activeBg font-bold text-app-chipText ${
                compact ? "h-4 min-w-[1rem] px-1 text-[9px]" : "h-5 min-w-[1.25rem] px-1 text-[10px]"
              }`}
            >
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={`font-medium text-app-primary ${compact ? "text-[11px] leading-snug" : "text-xs"}`}>
                {s.label}
              </p>
              {s.detail ? (
                <pre
                  className={`mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-app-subtle bg-white/90 font-mono text-app-secondary ${
                    compact ? "p-1.5 text-[10px] leading-relaxed" : "p-2 text-[11px] leading-relaxed"
                  }`}
                >
                  {s.detail}
                </pre>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
