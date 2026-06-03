"use client";

import { memo, useMemo, useState } from "react";
import { Icon } from "../AppIcons";
import type { OntologyMapping, PipelineTraceStep, SqlDerivation } from "../../lib/chatSessions";
import {
  transformStepsToNarrative,
  narrativeToSummary,
  type NarrativeLine,
} from "../../lib/thinkingProcess";

/* ── Props ────────────────────────────────────────────── */

type Props = {
  steps: PipelineTraceStep[];
  ontologyMapping?: OntologyMapping;
  sqlDerivation?: SqlDerivation;
  intent?: "sql_query" | "general_qa";
  streaming?: boolean;
  compact?: boolean;
  defaultExpanded?: boolean;
};

/* ── 样式常量 ──────────────────────────────────────────── */

const THINKING_BG = "bg-amber-50/60 dark:bg-amber-950/20";
const THINKING_BORDER = "border-amber-200/80 dark:border-amber-800/30";
const THINKING_HOVER = "hover:bg-amber-100/50 dark:hover:bg-amber-900/20";
const THINKING_TEXT = "text-amber-800 dark:text-amber-200";
const THINKING_MUTED = "text-amber-600/70 dark:text-amber-400/60";

/* ── 子组件 ──────────────────────────────────────────── */

/** 单行叙述，可选子行（五层分解） */
function NarrativeRow({
  line,
  isLast,
  streaming,
}: {
  line: NarrativeLine;
  isLast: boolean;
  streaming: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="flex items-start gap-2">
        {/* 左侧时间线指示器 */}
        <div className="mt-1.5 flex shrink-0 flex-col items-center">
          <span
            className={`block h-1.5 w-1.5 rounded-full ${
              isLast && streaming
                ? "bg-amber-500 motion-safe:animate-pulse"
                : "bg-amber-400/60 dark:bg-amber-500/40"
            }`}
            aria-hidden
          />
        </div>
        <span
          className={`text-[13px] leading-relaxed ${
            isLast && streaming
              ? "text-amber-900 dark:text-amber-100"
              : "text-amber-700/80 dark:text-amber-300/70"
          }`}
        >
          {line.text}
        </span>
      </div>

      {/* 五层子行 */}
      {line.subLines && line.subLines.length > 0 && (
        <div className="ml-5 mt-1 space-y-0.5">
          {line.subLines.map((sub) => (
            <div
              key={sub.key}
              className={`text-[11px] leading-relaxed ${
                sub.text.includes("未匹配")
                  ? "text-amber-500/60 dark:text-amber-500/40"
                  : "text-amber-600/80 dark:text-amber-400/60"
              }`}
            >
              {sub.text}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 主组件 ──────────────────────────────────────────── */

const CopilotThinkingProcess = memo(function CopilotThinkingProcess({
  steps,
  ontologyMapping,
  sqlDerivation,
  intent,
  streaming = false,
  compact = false,
  defaultExpanded = false,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const narrative = useMemo(
    () =>
      transformStepsToNarrative(steps, {
        ontologyMapping,
        sqlDerivation,
        intent,
      }),
    [steps, ontologyMapping, sqlDerivation, intent]
  );

  const summary = useMemo(() => narrativeToSummary(narrative), [narrative]);

  if (!narrative.length) return null;

  const totalSteps = 9; // 管线总步骤数
  const currentStep = narrative.length;
  const headerCls = compact ? "px-2.5 py-1.5" : "px-3 py-2";

  return (
    <section
      className={`mb-3 overflow-hidden rounded-xl border ${THINKING_BORDER} ${THINKING_BG}`}
      aria-label="思考过程"
    >
      {/* ── 头部：折叠/展开 ── */}
      <button
        type="button"
        className={`flex w-full items-center gap-2 text-left transition-colors ${headerCls} ${THINKING_HOVER}`}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="text-sm" aria-hidden>
          💭
        </span>
        <span className={`text-[12px] font-semibold uppercase tracking-wide ${THINKING_TEXT}`}>
          思考过程
        </span>
        {streaming ? (
          <span className="ml-1 rounded-full bg-amber-200/80 dark:bg-amber-800/50 px-1.5 py-0 text-[10px] tabular-nums text-amber-700 dark:text-amber-300">
            {currentStep}/{totalSteps}
          </span>
        ) : null}
        {!streaming && (
          <span className="ml-auto shrink-0 text-[10px] text-amber-500/70 dark:text-amber-500/50">
            {expanded ? "收起 ▲" : "展开 ▼"}
          </span>
        )}
        {compact && !expanded && (
          <span className="ml-auto truncate text-[10px] text-amber-600/60 dark:text-amber-400/40">
            {summary}
          </span>
        )}
      </button>

      {/* ── 折叠时一行摘要（非 compact 模式） ── */}
      {!expanded && !compact && summary && (
        <div className="border-t border-amber-200/60 dark:border-amber-800/20 px-3 pb-2 pt-1.5">
          <p className="truncate text-[11px] text-amber-600/70 dark:text-amber-400/50">
            {summary}
          </p>
        </div>
      )}

      {/* ── 展开时完整叙述 ── */}
      {expanded && (
        <div className="border-t border-amber-200/60 dark:border-amber-800/20">
          <div className={`space-y-2.5 ${compact ? "px-2.5 py-2" : "px-3 py-2.5"}`}>
            {narrative.map((line, idx) => (
              <NarrativeRow
                key={line.key}
                line={line}
                isLast={idx === narrative.length - 1}
                streaming={streaming}
              />
            ))}
          </div>

          {/* 流式中的思考中动画 */}
          {streaming && (
            <div
              className={`flex items-center gap-1.5 border-t border-amber-200/40 dark:border-amber-800/20 ${
                compact ? "px-2.5 py-1.5" : "px-3 py-2"
              }`}
              aria-hidden
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400/60 motion-safe:animate-pulse" />
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400/60 motion-safe:animate-pulse [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400/60 motion-safe:animate-pulse [animation-delay:300ms]" />
              <span className="ml-1 text-[10px] text-amber-500/60 dark:text-amber-400/40">
                思考中…
              </span>
            </div>
          )}
        </div>
      )}
    </section>
  );
});

export default CopilotThinkingProcess;
