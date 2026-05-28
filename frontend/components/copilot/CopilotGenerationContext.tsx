"use client";

import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { stripAutoRepairExplanationNote } from "../../lib/copilotTraceMarkdown";
import { streamAsk, type AskPayload, type AskResponse, type StreamStage } from "../../lib/copilotStream";
import { chatPanel } from "../../lib/themeClasses";
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
        <div className="min-w-0 text-app-primary" aria-live="polite">
          {hasNarrative ? <ChatGptStyleBody text={combined.trim()} /> : null}
          <div className="mt-1 flex items-center gap-1 text-app-muted" aria-hidden>
            {!hasNarrative ? (
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
  onSettled: (result: AskResponse) => void;
  onStreamError: () => void;
};

export function CopilotGenerationProvider({ activeAsk, children, onSettled, onStreamError }: ProviderProps) {
  const [streamStage, setStreamStage] = useState<StreamStage>("intent_recognizing");
  const [streamPreview, setStreamPreview] = useState({ answer: "", explanation: "" });
  const runIdRef = useRef(0);
  const onSettledRef = useRef(onSettled);
  const onStreamErrorRef = useRef(onStreamError);
  onSettledRef.current = onSettled;
  onStreamErrorRef.current = onStreamError;

  const busy = !!activeAsk;

  const ctxValue = useMemo<Ctx>(
    () => ({
      busy,
      streamStage,
      streamPreview
    }),
    [busy, streamStage, streamPreview]
  );

  useEffect(() => {
    if (!activeAsk) {
      setStreamStage("intent_recognizing");
      setStreamPreview({ answer: "", explanation: "" });
      return;
    }

    const runId = ++runIdRef.current;
    setStreamStage("intent_recognizing");
    setStreamPreview({ answer: "", explanation: "" });

    let cancelled = false;

    (async () => {
      try {
        const res = await streamAsk(
          activeAsk.payload,
          (stage) => {
            if (!cancelled && runId === runIdRef.current) setStreamStage(stage);
          },
          undefined,
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

  return <GenerationContext.Provider value={ctxValue}>{children}</GenerationContext.Provider>;
}
