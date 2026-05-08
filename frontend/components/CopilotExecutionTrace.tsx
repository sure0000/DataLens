import type { PipelineTraceStep } from "../lib/chatSessions";

type Props = {
  steps: PipelineTraceStep[];
  /** 更紧凑的行距与字号 */
  compact?: boolean;
  /** 区块标题 */
  title?: string;
  /**
   * plain：无额外外框，适合已在外层助手气泡/卡片内直接展示。
   * framed：独立浅底卡片，用于需要单独强调区块的场景。
   */
  variant?: "plain" | "framed";
};

export default function CopilotExecutionTrace({
  steps,
  compact,
  title = "推理过程",
  variant = "plain"
}: Props) {
  if (!steps.length) return null;

  const titleCls = compact
    ? "mb-2 text-xs font-semibold tracking-wide text-app-primary"
    : "mb-3 text-sm font-semibold text-app-primary";

  const stepTitleCls = compact ? "text-[12px] font-semibold leading-snug text-app-primary" : "text-[13px] font-semibold leading-snug text-app-primary";

  const detailCls = compact
    ? "mt-1 text-[11px] leading-relaxed text-app-secondary"
    : "mt-1.5 text-[12px] leading-relaxed text-app-secondary";

  const list = (
    <>
      <p className={titleCls}>{title}</p>
      <ol className={compact ? "space-y-2.5" : "space-y-3"}>
        {steps.map((s, i) => (
          <li key={`${s.id}-${i}`} className="flex gap-3">
            <span
              className={`mt-0.5 flex shrink-0 items-center justify-center rounded-full bg-emerald-600/15 font-bold text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-100 ${
                compact ? "h-5 min-w-[1.25rem] px-1 text-[10px]" : "h-6 min-w-[1.5rem] px-1 text-[11px]"
              }`}
            >
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={stepTitleCls}>{s.label}</p>
              {s.detail ? <p className={`${detailCls} whitespace-pre-wrap break-words`}>{s.detail}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </>
  );

  if (variant === "framed") {
    return (
      <div
        className={`rounded-xl border border-app-border bg-app-chip/50 ${
          compact ? "px-2.5 py-2" : "px-3 py-3"
        }`}
      >
        {list}
      </div>
    );
  }

  return <div className="min-w-0">{list}</div>;
}
