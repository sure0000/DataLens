import { API } from "./api";
import type { PipelineTraceStep, RoutingTrace, SqlReview } from "./chatSessions";

export type StreamStage = "intent_recognizing" | "answer_generating" | "sql_executing";

export type AskPayload = {
  question: string;
  table_id: number | null;
  business_domain_id: number | null;
  chat_model?: string | null;
};

export type OntologyMappingItem = {
  kind?: string;
  label?: string;
  definition?: string;
  maps_to?: string;
  iri?: string;
  type?: string;
};

export type OntologyMappingLink = {
  question_phrase?: string;
  target_kind?: string;
  target_label?: string;
  target_definition?: string;
  physical_tables?: string;
  description?: string;
};

export type OntologyMapping = {
  matched?: boolean;
  summary?: string;
  question?: string;
  mappings?: OntologyMappingLink[];
  items?: OntologyMappingItem[];
  skipped?: boolean;
  skip_reason?: string | null;
};

export type AskResponse = {
  intent?: "sql_query" | "general_qa";
  answer?: string;
  sql: string;
  explanation: string;
  query_result: {
    ok: boolean;
    columns: string[];
    rows: Record<string, unknown>[];
    row_count?: number;
    error?: string;
    review_required?: boolean;
  };
  pipeline_trace?: PipelineTraceStep[];
  routing_trace?: RoutingTrace;
  sql_review?: SqlReview;
  ontology_mapping?: OntologyMapping;
};

/**
 * SSE /api/ask/stream：delta 合并由调用方 schedule 回调控制，此处每个事件仍只解析一次。
 */
export async function streamAsk(
  askOpts: AskPayload,
  onStageChange?: (stage: StreamStage) => void,
  onTrace?: (row: PipelineTraceStep) => void,
  onStreamText?: (partial: { answer: string; explanation: string }) => void
): Promise<AskResponse> {
  const cm = askOpts.chat_model;
  const body: AskPayload = {
    question: askOpts.question,
    table_id: askOpts.table_id ?? null,
    business_domain_id: askOpts.business_domain_id ?? null,
    chat_model: cm === "auto" || cm === "" || cm == null ? null : cm
  };
  const resp = await fetch(`${API}/api/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!resp.ok || !resp.body) {
    throw new Error("stream not available");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let legacyPayload = "";
  let accAnswer = "";
  let accExplanation = "";
  let streamFlushRaf = 0;

  const flushStreamPreviewNow = () => {
    if (streamFlushRaf) {
      cancelAnimationFrame(streamFlushRaf);
      streamFlushRaf = 0;
    }
    onStreamText?.({ answer: accAnswer, explanation: accExplanation });
  };

  const scheduleStreamPreview = () => {
    if (streamFlushRaf || !onStreamText) return;
    streamFlushRaf = requestAnimationFrame(() => {
      streamFlushRaf = 0;
      onStreamText({ answer: accAnswer, explanation: accExplanation });
    });
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    const segments = pending.split("\n\n");
    pending = segments.pop() || "";

    for (const segment of segments) {
      const lines = segment.split("\n");
      const eventLine = lines.find((l) => l.startsWith("event:"));
      const dataLine = lines.find((l) => l.startsWith("data:"));
      const event = eventLine?.replace("event:", "").trim();
      const data = dataLine?.replace("data:", "").trim() || "";
      if (event === "result") {
        flushStreamPreviewNow();
        return JSON.parse(data) as AskResponse;
      }
      if (event === "delta") {
        const parsed = JSON.parse(data) as { field?: string; delta?: string };
        if (parsed.field === "answer" && typeof parsed.delta === "string") accAnswer += parsed.delta;
        else if (parsed.field === "explanation" && typeof parsed.delta === "string") accExplanation += parsed.delta;
        scheduleStreamPreview();
      } else if (event === "chunk") {
        const parsed = JSON.parse(data) as { chunk: string };
        legacyPayload += parsed.chunk;
      } else if (event === "status") {
        const parsed = JSON.parse(data) as { stage?: StreamStage };
        if (parsed.stage) onStageChange?.(parsed.stage);
      } else if (event === "trace") {
        const parsed = JSON.parse(data) as PipelineTraceStep;
        if (parsed && typeof parsed.id === "string" && typeof parsed.label === "string") {
          onTrace?.(parsed);
        }
      }
    }
  }

  if (legacyPayload.trim()) {
    flushStreamPreviewNow();
    return JSON.parse(legacyPayload) as AskResponse;
  }
  flushStreamPreviewNow();
  throw new Error("stream ended without result");
}
