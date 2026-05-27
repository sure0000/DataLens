"use client";

import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { stripAutoRepairExplanationNote } from "../../lib/copilotTraceMarkdown";
import type { PipelineTraceStep } from "../../lib/chatSessions";
import { streamAsk, type AskPayload, type AskResponse, type StreamStage } from "../../lib/copilotStream";
import { chatPanel, chipWarning } from "../../lib/themeClasses";
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
  }, [ctx?.busy, ctx?.streamPreview.answer, ctx?.streamPreview.explanation]);

  if (!ctx?.busy) return null;

  const combinedRaw =
    ctx.streamPreview.answer.trim() && ctx.streamPreview.explanation.trim()
      ? `${ctx.streamPreview.answer.trim()}\n\n${ctx.streamPreview.explanation.trim()}`
      : ctx.streamPreview.answer.trim() || ctx.streamPreview.explanation.trim();
  const combined = stripAutoRepairExplanationNote(combinedRaw.trim());

  const hasNarrative = combined.trim().length > 0;

  return (
    <div ref={rootRef} className="flex min-w-0 max-w-full justify-start">
      <div className={`min-w-0 max-w-[min(100%,40rem)] rounded-2xl px-4 py-3 ${chatPanel}`}>
        <p className="text-xs text-app-muted" aria-live="polite">
          <span className={`mr-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${chipWarning}`}>
            生成中
          </span>
          {stageLabelMap[ctx.streamStage]}
        </p>
        <div className="mt-2 min-w-0 text-app-primary">
          {hasNarrative ? (
            <>
              <ChatGptStyleBody text={combined.trim()} />
              <span
                className="mt-1 inline-block h-[1em] w-0.5 rounded-sm bg-app-primary/70 motion-safe:animate-pulse"
                aria-hidden
              />
            </>
          ) : (
            <p className="text-sm leading-relaxed text-app-secondary">正在处理您的问题…</p>
          )}
        </div>
      </div>
    </div>
  );
});

/** 底栏一行状态提示 */
export const CopilotGenerationDockStatus = memo(function CopilotGenerationDockStatus() {
  const ctx = useContext(GenerationContext);
  if (!ctx?.busy) return null;

  return (
    <p className="pointer-events-auto truncate px-1 text-center text-xs text-app-muted">
      {stageLabelMap[ctx.streamStage]}
    </p>
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
