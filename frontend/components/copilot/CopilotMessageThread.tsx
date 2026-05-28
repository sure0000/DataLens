"use client";

import { memo } from "react";
import { stripAutoRepairExplanationNote } from "../../lib/copilotTraceMarkdown";
import { type ChatMessage } from "../../lib/chatSessions";
import SqlBlock from "../SqlBlock";
import CsvExportButton from "../CsvExportButton";
import { alertWarning, chatPanel, textDanger, userBubble } from "../../lib/themeClasses";
import ChatGptStyleBody from "./ChatGptStyleBody";
import OntologyMappingBlock from "./OntologyMappingBlock";

type QueryResult = {
  ok: boolean;
  columns: string[];
  rows: Record<string, unknown>[];
  error?: string;
};

export type CopilotMessageThreadProps = {
  messages: ChatMessage[];
  editingMessageId: string;
  editingText: string;
  setEditingText: (v: string) => void;
  setEditingMessageId: (v: string) => void;
  saveEditAndResubmit: () => void;
  copyMessage: (m: ChatMessage) => void;
  retryFromAssistant: (messageId: string) => void;
  onApplySuggestedDomain?: (domainId: number, question: string) => void;
};

const CopilotMessageThread = memo(function CopilotMessageThread({
  messages,
  editingMessageId,
  editingText,
  setEditingText,
  setEditingMessageId,
  saveEditAndResubmit,
  copyMessage,
  retryFromAssistant,
  onApplySuggestedDomain,
}: CopilotMessageThreadProps) {
  return (
    <>
      {messages.map((m, msgIdx) => {
        const queryResult = (m.query_result || {
          ok: false,
          columns: [],
          rows: [],
          error: "历史记录无执行结果",
        }) as QueryResult;
        const isGeneralQa =
          m.intent === "general_qa" ||
          (!m.sql &&
            !queryResult.ok &&
            (queryResult.error?.includes("无需SQL") || queryResult.error?.includes("无需 SQL") || false));

        if (m.role === "user") {
          if (editingMessageId === m.id) {
            return (
              <div key={m.id} className="ml-auto w-full max-w-2xl rounded-2xl border border-app-border bg-[var(--app-card-bg)] p-3">
                <textarea
                  className="min-h-[72px] w-full resize-none rounded-lg border border-app-border bg-transparent px-3 py-2 text-sm text-app-primary outline-none"
                  value={editingText}
                  onChange={(e) => setEditingText(e.target.value)}
                />
                <div className="mt-2 flex justify-end gap-2">
                  <button type="button" className="app-button-secondary app-button-xs" onClick={() => setEditingMessageId("")}>
                    取消
                  </button>
                  <button type="button" className="app-button app-button-xs" onClick={saveEditAndResubmit}>
                    发送
                  </button>
                </div>
              </div>
            );
          }
          return (
            <div key={m.id} className="group flex justify-end">
              <div className={`max-w-[min(100%,32rem)] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${userBubble}`}>
                {m.question}
              </div>
            </div>
          );
        }

        const narrativeRaw =
          (m.answer || "").trim() && (m.explanation || "").trim()
            ? `${(m.answer || "").trim()}\n\n${(m.explanation || "").trim()}`
            : (m.answer || "").trim() || (m.explanation || "").trim();
        const narrative = stripAutoRepairExplanationNote(narrativeRaw.trim());
        const userQuestion =
          messages
            .slice(0, msgIdx)
            .reverse()
            .find((x) => x.role === "user" && x.question?.trim())?.question?.trim() || "";

        return (
          <div key={m.id} className="flex justify-start">
            <div className={`min-w-0 max-w-[min(100%,40rem)] rounded-2xl px-4 py-3 ${chatPanel}`}>
              {m.routing_trace?.domain_suggestion?.requires_confirmation &&
                typeof m.routing_trace.domain_suggestion.domain_id === "number" &&
                m.retry_question?.trim() &&
                onApplySuggestedDomain && (
                  <div className={`mb-3 rounded-lg px-3 py-2 text-xs ${alertWarning}`}>
                    <p>
                      建议使用业务域「{m.routing_trace.domain_suggestion.domain_name || m.routing_trace.domain_suggestion.domain_id}」
                    </p>
                    <button
                      type="button"
                      className="mt-2 text-xs font-medium text-app-primary underline"
                      onClick={() =>
                        onApplySuggestedDomain(m.routing_trace!.domain_suggestion!.domain_id, m.retry_question!.trim())
                      }
                    >
                      切换并重试
                    </button>
                  </div>
                )}

              {m.ontology_mapping ? (
                <OntologyMappingBlock mapping={m.ontology_mapping} fallbackQuestion={userQuestion} />
              ) : null}

              {narrative ? <ChatGptStyleBody text={narrative} /> : <p className="text-sm text-app-muted">（无回复内容）</p>}

              {!isGeneralQa && m.sql?.trim() ? (
                <div className="mt-3">
                  <p className="mb-1.5 text-xs font-medium text-app-secondary">生成的 SQL</p>
                  <SqlBlock sql={m.sql} />
                </div>
              ) : null}

              {!isGeneralQa && queryResult.ok && queryResult.columns.length > 0 && (
                <div className="mt-3 max-w-full overflow-x-auto rounded-lg border border-app-border">
                  <table className="w-full min-w-0 table-auto border-collapse text-xs">
                    <thead>
                      <tr>
                        {queryResult.columns.map((c) => (
                          <th key={c} className="border-b border-app-border bg-app-hover px-2 py-1.5 text-left font-medium text-app-secondary">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {queryResult.rows.slice(0, 20).map((row, idx) => (
                        <tr key={idx} className="odd:bg-transparent even:bg-app-hover/50">
                          {queryResult.columns.map((c) => (
                            <td key={`${idx}-${c}`} className="border-b border-app-subtle px-2 py-1.5 text-app-primary">
                              {String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="flex justify-end border-t border-app-subtle px-2 py-1">
                    <CsvExportButton result={queryResult} />
                  </div>
                </div>
              )}

              {!isGeneralQa && !queryResult.ok && m.sql && (
                <p className={`mt-2 text-sm ${textDanger}`}>{queryResult.error || "查询未成功"}</p>
              )}

              <div className="mt-3 flex gap-3 border-t border-app-subtle pt-2 text-xs text-app-muted">
                <button type="button" className="hover:text-app-primary" onClick={() => copyMessage(m)}>
                  复制
                </button>
                {!isGeneralQa && m.sql ? (
                  <button type="button" className="hover:text-app-primary" onClick={() => retryFromAssistant(m.id)}>
                    重试
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
});

export default CopilotMessageThread;
