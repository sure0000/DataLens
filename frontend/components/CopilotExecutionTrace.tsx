import { AlertTriangle, Ban, Check, Code2, ListTree, PackageX, Sparkles, XCircle } from "lucide-react";
import { memo } from "react";
import type { ReactNode } from "react";
import type { PipelineTraceStep, TraceEntityLink } from "../lib/chatSessions";
import { splitTraceStepDetailIntoSubCheckpoints, type TraceSubCheckpoint } from "../lib/copilotTraceMarkdown";
import { parseTraceEntityLinks, renderTraceDetailWithLinks } from "../lib/traceEntityLinks";
import { renderReasoning3Row, tryParseReasoning3Line } from "../lib/traceReasoning3";
import {
  annotateSubCheckpointsWithStatus,
  traceCheckpointIconClass,
  traceCheckpointStatusLabel,
  traceCheckpointStripClass,
  type TraceCheckpointStatus
} from "../lib/copilotTraceStatus";
import SqlBlock from "./SqlBlock";

type Props = {
  steps: PipelineTraceStep[];
  compact?: boolean;
  title?: string;
  variant?: "plain" | "framed";
  streaming?: boolean;
};

function StatusGlyph({ status, className }: { status: TraceCheckpointStatus; className?: string }) {
  const tone = traceCheckpointIconClass(status);
  const c = `shrink-0 ${tone} ${className || ""}`;
  const stroke = 2.75;
  switch (status) {
    case "verified":
      return <Check className={c} strokeWidth={stroke} aria-hidden />;
    case "context_missing":
      return <PackageX className={c} strokeWidth={stroke} aria-hidden />;
    case "inferred_ok":
      return <Sparkles className={c} strokeWidth={stroke} aria-hidden />;
    case "inferred_review":
      return <AlertTriangle className={c} strokeWidth={stroke} aria-hidden />;
    case "skipped":
      return <Ban className={c} strokeWidth={stroke} aria-hidden />;
    case "issue":
      return <XCircle className={c} strokeWidth={stroke} aria-hidden />;
    default:
      return <Sparkles className={c} strokeWidth={stroke} aria-hidden />;
  }
}

type AnnotatedSub = TraceSubCheckpoint & { status: TraceCheckpointStatus };

function traceSqlCaptionShort(caption: string | null | undefined): string {
  const t = (caption || "").trim();
  if (!t) return "SQL";
  return t.replace(/^【\s*/, "").replace(/\s*】$/, "").trim() || "SQL";
}

function renderTraceStepBody(
  s: PipelineTraceStep,
  body: string,
  stepLinks: TraceEntityLink[],
  detailCls: string
): ReactNode {
  const trimmed = body.trim();
  const parsedR3 = s.id === "reasoning_3" ? tryParseReasoning3Line(trimmed) : null;
  const bodyCls = `${detailCls} whitespace-pre-wrap break-words`;
  const inner = parsedR3 ? renderReasoning3Row(trimmed, stepLinks) : renderTraceDetailWithLinks(trimmed, stepLinks);
  return parsedR3 ? <div className={bodyCls}>{inner}</div> : <p className={bodyCls}>{inner}</p>;
}

/** 「4. 查询逻辑以及 SQL」：逻辑与 SQL 分区展示，SQL 使用独立代码面板 */
function Reasoning4StepLayout({
  s,
  subs,
  stepLinks,
  streaming,
  isLastStage,
  detailCls,
  iconBox,
  idxCls
}: {
  s: PipelineTraceStep;
  subs: AnnotatedSub[];
  stepLinks: TraceEntityLink[];
  streaming: boolean;
  isLastStage: boolean;
  detailCls: string;
  iconBox: string;
  idxCls: string;
}) {
  const logicSubs = subs.filter((x) => !x.sql);
  const sqlSubs = subs.filter((x) => x.sql);

  return (
    <div className="space-y-3">
      {logicSubs.length > 0 ? (
        <div className="overflow-hidden rounded-lg border border-neutral-200/90 bg-[var(--app-card-bg)] shadow-sm dark:border-neutral-600 dark:bg-neutral-900/45">
          <div className="flex items-center gap-2 border-b border-neutral-200/85 bg-neutral-50/98 px-2.5 py-1.5 dark:border-neutral-700/90 dark:bg-neutral-800/55">
            <ListTree className="h-3.5 w-3.5 shrink-0 text-app-secondary" strokeWidth={2.25} aria-hidden />
            <span className="text-[11px] font-semibold uppercase tracking-wide text-app-secondary">查询逻辑</span>
          </div>
          <ol className="m-0 list-none divide-y divide-neutral-200/90 p-0 dark:divide-neutral-700/85">
            {logicSubs.map((sub, i) => {
              const globalIdx = subs.indexOf(sub);
              const isLive = streaming && isLastStage && globalIdx === subs.length - 1;
              const showBody = (sub.body || "").trim().length > 0;
              const a11y = traceCheckpointStatusLabel(sub.status);
              return (
                <li
                  key={`${s.id}-sub-${globalIdx}`}
                  aria-current={isLive ? "step" : undefined}
                  className={`flex items-stretch gap-1.5 px-1.5 py-1.5 sm:px-2 ${
                    isLive
                      ? "rounded-md bg-amber-500/[0.08] ring-1 ring-amber-500/25 dark:bg-amber-500/10 dark:ring-amber-400/20"
                      : ""
                  }`}
                >
                  <div className={`w-1 shrink-0 self-stretch rounded-full ${traceCheckpointStripClass(sub.status)}`} aria-hidden />
                  <div className="flex shrink-0 self-start pt-0.5" role="img" aria-label={a11y}>
                    <StatusGlyph status={sub.status} className={iconBox} />
                  </div>
                  <span className={`shrink-0 self-start text-right font-medium tabular-nums text-app-muted ${idxCls}`} aria-hidden>
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1 self-start">{showBody ? renderTraceStepBody(s, sub.body, stepLinks, detailCls) : null}</div>
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
      {sqlSubs.map((sub) => {
        const globalIdx = subs.indexOf(sub);
        const isLive = streaming && isLastStage && globalIdx === subs.length - 1;
        const title = traceSqlCaptionShort(sub.sqlCaption);
        return (
          <div
            key={`${s.id}-sql-${globalIdx}`}
            aria-current={isLive ? "step" : undefined}
            className={`overflow-hidden rounded-lg border border-indigo-200/75 bg-indigo-50/[0.42] shadow-sm dark:border-indigo-800/55 dark:bg-indigo-950/40 ${
              isLive ? "ring-2 ring-amber-400/45 dark:ring-amber-400/35" : ""
            }`}
          >
            <div className="flex items-center gap-2 border-b border-indigo-200/65 bg-white/70 px-2.5 py-1.5 dark:border-indigo-800/45 dark:bg-indigo-950/60">
              <Code2 className="h-3.5 w-3.5 shrink-0 text-indigo-600 dark:text-indigo-400" strokeWidth={2.25} aria-hidden />
              <span className="min-w-0 flex-1 truncate text-[11px] font-semibold leading-tight text-indigo-950 dark:text-indigo-50">
                {title}
              </span>
            </div>
            <div className="p-1.5 sm:p-2">
              <div className="overflow-x-auto rounded-md border border-neutral-600/80 bg-[#14141c] shadow-inner dark:border-neutral-500/50">
                <SqlBlock
                  sql={sub.sql || ""}
                  className="mt-0 rounded-none border-0 bg-transparent p-2.5 text-[11px] leading-relaxed sm:p-3 sm:text-xs sm:leading-5"
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CopilotExecutionTrace({
  steps,
  compact,
  title = "推理过程",
  variant = "plain",
  streaming = false
}: Props) {
  if (!steps.length) return null;

  const titleCls = compact
    ? "mb-2 text-xs font-semibold uppercase tracking-wide text-app-secondary"
    : "mb-2 text-sm font-semibold text-app-primary";

  const stageTitleCls = compact ? "text-[12px] font-semibold leading-tight" : "text-[13px] font-semibold leading-tight";
  const idxCls = compact ? "w-3.5 pt-px text-[9px]" : "w-4 pt-px text-[10px]";
  const detailCls = compact
    ? "text-[11px] leading-snug text-app-secondary"
    : "text-[12px] leading-snug text-app-secondary";
  const iconBox = compact ? "h-3.5 w-3.5" : "h-4 w-4";

  const list = (
    <div className="min-w-0">
      <p className={titleCls}>{title}</p>
      <div className="space-y-3" aria-label={title}>
        {steps.map((s, stageIdx) => {
          const subs = annotateSubCheckpointsWithStatus(s.id, splitTraceStepDetailIntoSubCheckpoints(s));
          const isLastStage = stageIdx === steps.length - 1;
          const stepLinks = parseTraceEntityLinks(s.links);

          return (
            <section key={`${s.id}-${stageIdx}`} className="min-w-0">
              <h3 className={`mb-1 border-b border-neutral-200/90 pb-1 text-app-primary dark:border-neutral-700 ${stageTitleCls}`}>
                {s.label}
              </h3>

              {subs.length === 0 ? (
                <p className={`text-app-muted ${compact ? "py-1 text-[11px]" : "py-1 text-xs"}`}>（本步暂无说明）</p>
              ) : s.id === "reasoning_4" ? (
                <Reasoning4StepLayout
                  s={s}
                  subs={subs}
                  stepLinks={stepLinks}
                  streaming={streaming}
                  isLastStage={isLastStage}
                  detailCls={detailCls}
                  iconBox={iconBox}
                  idxCls={idxCls}
                />
              ) : (
                <ol className="m-0 list-none divide-y divide-neutral-200/90 p-0 dark:divide-neutral-700/90">
                  {subs.map((sub, subIdx) => {
                    const isLive = streaming && isLastStage && subIdx === subs.length - 1;
                    const subNo = subIdx + 1;
                    const showBody = (sub.body || "").trim().length > 0;
                    const a11y = traceCheckpointStatusLabel(sub.status);

                    return (
                      <li
                        key={`${s.id}-sub-${subIdx}`}
                        aria-current={isLive ? "step" : undefined}
                        className={`flex items-stretch gap-1.5 py-1.5 ${isLive ? "rounded-md bg-amber-500/[0.08] ring-1 ring-amber-500/25 dark:bg-amber-500/10 dark:ring-amber-400/20" : ""}`}
                      >
                        <div
                          className={`w-1 shrink-0 self-stretch rounded-full ${traceCheckpointStripClass(sub.status)}`}
                          aria-hidden
                        />
                        <div className="flex shrink-0 self-start pt-0.5" role="img" aria-label={a11y}>
                          <StatusGlyph status={sub.status} className={iconBox} />
                        </div>
                        <span className={`shrink-0 self-start text-right font-medium tabular-nums text-app-muted ${idxCls}`} aria-hidden>
                          {subNo}
                        </span>
                        <div className="min-w-0 flex-1 self-start">
                          {showBody ? renderTraceStepBody(s, sub.body, stepLinks, detailCls) : null}
                          {sub.sql ? (
                            <div className={showBody ? "mt-1" : ""}>
                              {sub.sqlCaption ? (
                                <p className="mb-0.5 text-[10px] font-medium leading-tight text-app-secondary">{sub.sqlCaption}</p>
                              ) : null}
                              <div className="overflow-x-auto rounded border border-neutral-200/80 bg-neutral-50/90 dark:border-neutral-700 dark:bg-neutral-900/60 [&_.sql-block]:mt-0">
                                <SqlBlock sql={sub.sql} />
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );

  if (variant === "framed") {
    return (
      <div
        className={`rounded-lg border border-app-border bg-neutral-50/40 dark:border-neutral-700 dark:bg-neutral-950/30 ${
          compact ? "px-2 py-2" : "px-2.5 py-2"
        }`}
      >
        {list}
      </div>
    );
  }

  return <div className="min-w-0">{list}</div>;
}

export default memo(CopilotExecutionTrace);
