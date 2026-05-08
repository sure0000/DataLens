"use client";

import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { formatPipelineTraceForBodyMarkdown } from "../../lib/copilotTraceMarkdown";
import { filterCopilotTraceSteps, type PipelineTraceStep } from "../../lib/chatSessions";
import { streamAsk, type AskPayload, type AskResponse, type StreamStage } from "../../lib/copilotStream";
import ChatGptStyleBody from "./ChatGptStyleBody";

export type ActiveAsk = {
  key: number;
  sessionId: string;
  payload: AskPayload;
};

type Ctx = {
  busy: boolean;
  streamStage: StreamStage;
  streamPreview: { answer: string; explanation: string };
  livePipelineTrace: PipelineTraceStep[];
};

const GenerationContext = createContext<Ctx | null>(null);

const stageLabelMap: Record<StreamStage, string> = {
  intent_recognizing: "意图识别中",
  answer_generating: "生成回答中",
  sql_executing: "执行 SQL 中"
};

const stageOrder: StreamStage[] = ["intent_recognizing", "answer_generating", "sql_executing"];

export const CopilotStreamBubble = memo(function CopilotStreamBubble() {
  const ctx = useContext(GenerationContext);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ctx?.busy) return;
    const scrollEl = rootRef.current?.closest("[data-copilot-scroll]");
    if (!scrollEl) return;
    const id = window.setTimeout(() => {
      scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: "auto" });
    }, 48);
    return () => clearTimeout(id);
  }, [ctx?.busy, ctx?.streamPreview.answer, ctx?.streamPreview.explanation, ctx?.livePipelineTrace]);

  if (!ctx?.busy) return null;

  const combined =
    ctx.streamPreview.answer.trim() && ctx.streamPreview.explanation.trim()
      ? `${ctx.streamPreview.answer.trim()}\n\n${ctx.streamPreview.explanation.trim()}`
      : ctx.streamPreview.answer.trim() || ctx.streamPreview.explanation.trim();

  const traceSteps = filterCopilotTraceSteps(ctx.livePipelineTrace);
  const traceMd = traceSteps.length ? formatPipelineTraceForBodyMarkdown(traceSteps) : "";
  const bodyParts: string[] = [];
  if (traceMd) bodyParts.push(traceMd);
  if (combined.trim()) bodyParts.push(combined.trim());
  const fullBody = bodyParts.join("\n\n");

  return (
    <div ref={rootRef} className="flex min-w-0 max-w-full justify-start">
      <div className="min-w-0 max-w-[min(100%,42rem)] rounded-[1.35rem] border border-neutral-200/80 bg-white px-4 py-3 shadow-sm dark:border-neutral-700 dark:bg-neutral-900 dark:shadow-none">
        <div className="mb-3 flex min-w-0 flex-wrap items-center gap-2">
          <span className="rounded-full border border-amber-200/90 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-100">
            生成中
          </span>
          <span className="text-xs text-app-secondary">{stageLabelMap[ctx.streamStage]}</span>
          <div className="ml-auto flex min-w-[4.5rem] max-w-[45%] shrink-0 gap-1">
            {stageOrder.map((stage) => {
              const activeIdx = stageOrder.indexOf(ctx.streamStage);
              const idx = stageOrder.indexOf(stage);
              const done = idx <= activeIdx;
              return (
                <span
                  key={stage}
                  title={stageLabelMap[stage]}
                  className={`h-1 min-w-0 flex-1 rounded-full ${done ? "bg-emerald-600 dark:bg-emerald-500" : "bg-neutral-200 dark:bg-neutral-600"}`}
                />
              );
            })}
          </div>
        </div>

        <div className="min-w-0 text-app-primary" aria-live="polite">
          {fullBody ? (
            <>
              <ChatGptStyleBody text={fullBody} />
              {combined.trim() ? (
                <span
                  className="mt-1 inline-block h-[1.05em] w-0.5 translate-y-px rounded-sm bg-app-primary/80 motion-safe:animate-pulse"
                  aria-hidden
                />
              ) : null}
            </>
          ) : (
            <p className="text-[15px] leading-7 text-app-secondary">正在连接分析管线并准备上下文…</p>
          )}
        </div>
      </div>
    </div>
  );
});

/** 底栏仅保留一行进度，避免大块面板与聊天区层叠 */
export const CopilotGenerationDockStatus = memo(function CopilotGenerationDockStatus() {
  const ctx = useContext(GenerationContext);
  if (!ctx?.busy) return null;

  return (
    <div className="pointer-events-auto min-h-0 min-w-0 rounded-xl border border-neutral-200/80 bg-white/90 px-3 py-2 shadow-sm backdrop-blur-sm dark:border-neutral-700 dark:bg-neutral-900/90">
      <div className="flex min-w-0 items-center gap-3">
        <p className="min-w-0 flex-1 truncate text-[13px] font-medium text-app-primary">{stageLabelMap[ctx.streamStage]}</p>
        <div className="flex min-w-[5rem] max-w-[40%] shrink-0 gap-1">
          {stageOrder.map((stage) => {
            const activeIdx = stageOrder.indexOf(ctx.streamStage);
            const idx = stageOrder.indexOf(stage);
            const done = idx <= activeIdx;
            return (
              <span
                key={stage}
                className={`h-0.5 min-w-0 flex-1 rounded-full ${done ? "bg-neutral-700 dark:bg-neutral-200" : "bg-neutral-200 dark:bg-neutral-700"}`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
});

type ProviderProps = {
  activeAsk: ActiveAsk | null;
  children: ReactNode;
  onSettled: (result: AskResponse, traceAcc: PipelineTraceStep[]) => void;
  onStreamError: () => void;
};

export function CopilotGenerationProvider({ activeAsk, children, onSettled, onStreamError }: ProviderProps) {
  const [streamStage, setStreamStage] = useState<StreamStage>("intent_recognizing");
  const [streamPreview, setStreamPreview] = useState({ answer: "", explanation: "" });
  const [livePipelineTrace, setLivePipelineTrace] = useState<PipelineTraceStep[]>([]);
  const traceAccRef = useRef<PipelineTraceStep[]>([]);
  const runIdRef = useRef(0);
  const onSettledRef = useRef(onSettled);
  const onStreamErrorRef = useRef(onStreamError);
  onSettledRef.current = onSettled;
  onStreamErrorRef.current = onStreamError;

  /** 每条 trace 立即入列渲染，避免 rAF 合并导致「结束时一次性出现」 */
  const enqueueLiveTrace = useCallback((row: PipelineTraceStep) => {
    traceAccRef.current.push(row);
    setLivePipelineTrace((prev) => [...prev, row]);
  }, []);

  const busy = !!activeAsk;

  const ctxValue = useMemo<Ctx>(
    () => ({
      busy,
      streamStage,
      streamPreview,
      livePipelineTrace
    }),
    [busy, streamStage, streamPreview, livePipelineTrace]
  );

  useEffect(() => {
    if (!activeAsk) {
      traceAccRef.current = [];
      setStreamStage("intent_recognizing");
      setStreamPreview({ answer: "", explanation: "" });
      setLivePipelineTrace([]);
      return;
    }

    const runId = ++runIdRef.current;
    traceAccRef.current = [];
    setStreamStage("intent_recognizing");
    setStreamPreview({ answer: "", explanation: "" });
    setLivePipelineTrace([]);

    let cancelled = false;

    (async () => {
      try {
        const res = await streamAsk(
          activeAsk.payload,
          (stage) => {
            if (!cancelled && runId === runIdRef.current) setStreamStage(stage);
          },
          (row) => {
            if (!cancelled && runId === runIdRef.current) enqueueLiveTrace(row);
          },
          (partial) => {
            if (!cancelled && runId === runIdRef.current) setStreamPreview(partial);
          }
        );
        if (cancelled || runId !== runIdRef.current) return;
        onSettledRef.current(res, traceAccRef.current);
      } catch {
        if (!cancelled && runId === runIdRef.current) onStreamErrorRef.current();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeAsk?.key, activeAsk?.sessionId, enqueueLiveTrace]);

  return <GenerationContext.Provider value={ctxValue}>{children}</GenerationContext.Provider>;
}
