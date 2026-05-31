"use client";

import { createContext, memo, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { stripAutoRepairExplanationNote } from "../../lib/copilotTraceMarkdown";
import { upsertPipelineTraceStep, type PipelineTraceStep } from "../../lib/chatSessions";
import { streamAsk, type AskPayload, type AskResponse, type StreamStage } from "../../lib/copilotStream";
import { chatPanel } from "../../lib/themeClasses";
import ChatGptStyleBody from "./ChatGptStyleBody";
import CopilotLiveTrace from "./CopilotLiveTrace";

export type ActiveAsk = {
  key: number;
  sessionId: string;
  payload: AskPayload;
};

type Ctx = {
  busy: boolean;
  streamStage: StreamStage;
};

type PreviewCtx = {
  busy: boolean;
  streamPreview: { answer: string; explanation: string };
  streamTraceSteps: PipelineTraceStep[];
};

const GenerationStatusContext = createContext<Ctx | null>(null);
const GenerationPreviewContext = createContext<PreviewCtx | null>(null);

const stageLabelMap: Record<StreamStage, string> = {
  intent_recognizing: "意图识别中",
  answer_generating: "生成回答中",
  sql_executing: "执行 SQL 中"
};

export const CopilotStreamBubble = memo(function CopilotStreamBubble() {
  const previewCtx = useContext(GenerationPreviewContext);
  const statusCtx = useContext(GenerationStatusContext);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!previewCtx?.busy) return;
    const scrollEl = rootRef.current?.closest("[data-copilot-scroll]");
    if (!scrollEl) return;
    const id = window.setTimeout(() => {
      scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: "auto" });
    }, 48);
    return () => clearTimeout(id);
  }, [
    previewCtx?.busy,
    previewCtx?.streamPreview.answer,
    previewCtx?.streamPreview.explanation,
    previewCtx?.streamTraceSteps.length
  ]);

  if (!previewCtx?.busy) return null;

  const answerText = stripAutoRepairExplanationNote(previewCtx.streamPreview.answer.trim());
  const explanationText = stripAutoRepairExplanationNote(previewCtx.streamPreview.explanation.trim());
  const hasStreamText = !!(answerText || explanationText);

  return (
    <div ref={rootRef} className="flex min-w-0 max-w-full justify-start">
      <div className={`min-w-0 max-w-[min(100%,40rem)] rounded-2xl px-4 py-3 ${chatPanel}`}>
        <CopilotLiveTrace steps={previewCtx.streamTraceSteps} />

        <div className="min-w-0 text-app-primary" aria-live="polite">
          {answerText ? (
            <div className="mb-2">
              <p className="mb-1 text-xs font-medium text-app-secondary">执行摘要</p>
              <ChatGptStyleBody text={answerText} />
            </div>
          ) : null}
          {explanationText ? (
            <div className={answerText ? "mb-2" : ""}>
              {(answerText || statusCtx?.streamStage !== "intent_recognizing") ? (
                <p className="mb-1 text-xs font-medium text-app-secondary">SQL 推导说明</p>
              ) : null}
              <ChatGptStyleBody text={explanationText} />
            </div>
          ) : null}
          <div className="mt-1 flex items-center gap-1 text-app-muted" aria-hidden>
            {!hasStreamText ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40 motion-safe:animate-pulse" />
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60 motion-safe:animate-pulse [animation-delay:120ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80 motion-safe:animate-pulse [animation-delay:240ms]" />
              </>
            ) : null}
            <span className="inline-block h-[1em] w-0.5 rounded-sm bg-app-primary/70 motion-safe:animate-pulse" />
          </div>
        </div>
      </div>
    </div>
  );
});

/** 底栏一行状态提示 */
export const CopilotGenerationDockStatus = memo(function CopilotGenerationDockStatus() {
  const ctx = useContext(GenerationStatusContext);
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
  onSettled: (result: AskResponse) => void;
  onStreamError: () => void;
};

export function CopilotGenerationProvider({ activeAsk, children, onSettled, onStreamError }: ProviderProps) {
  const [streamStage, setStreamStage] = useState<StreamStage>("intent_recognizing");
  const [streamPreview, setStreamPreview] = useState({ answer: "", explanation: "" });
  const [streamTraceSteps, setStreamTraceSteps] = useState<PipelineTraceStep[]>([]);
  const runIdRef = useRef(0);
  const onSettledRef = useRef(onSettled);
  const onStreamErrorRef = useRef(onStreamError);
  onSettledRef.current = onSettled;
  onStreamErrorRef.current = onStreamError;

  const busy = !!activeAsk;

  const statusCtxValue = useMemo<Ctx>(
    () => ({
      busy,
      streamStage,
    }),
    [busy, streamStage]
  );
  const previewCtxValue = useMemo<PreviewCtx>(
    () => ({
      busy,
      streamPreview,
      streamTraceSteps,
    }),
    [busy, streamPreview, streamTraceSteps]
  );

  useEffect(() => {
    if (!activeAsk) {
      setStreamStage("intent_recognizing");
      setStreamPreview({ answer: "", explanation: "" });
      setStreamTraceSteps([]);
      return;
    }

    const runId = ++runIdRef.current;
    setStreamStage("intent_recognizing");
    setStreamPreview({ answer: "", explanation: "" });
    setStreamTraceSteps([]);

    let cancelled = false;

    (async () => {
      try {
        const res = await streamAsk(
          activeAsk.payload,
          (stage) => {
            if (!cancelled && runId === runIdRef.current) setStreamStage(stage);
          },
          (row) => {
            if (!cancelled && runId === runIdRef.current) {
              setStreamTraceSteps((prev) => upsertPipelineTraceStep(prev, row));
            }
          },
          (partial) => {
            if (!cancelled && runId === runIdRef.current) setStreamPreview(partial);
          }
        );
        if (cancelled || runId !== runIdRef.current) return;
        onSettledRef.current(res);
      } catch {
        if (!cancelled && runId === runIdRef.current) onStreamErrorRef.current();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeAsk?.key, activeAsk?.sessionId]);

  return (
    <GenerationStatusContext.Provider value={statusCtxValue}>
      <GenerationPreviewContext.Provider value={previewCtxValue}>{children}</GenerationPreviewContext.Provider>
    </GenerationStatusContext.Provider>
  );
}
