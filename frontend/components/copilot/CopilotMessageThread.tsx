"use client";

import { memo } from "react";
import { stripAutoRepairExplanationNote } from "../../lib/copilotTraceMarkdown";
import { filterCopilotTraceSteps, type ChatMessage } from "../../lib/chatSessions";
import CopilotExecutionTrace from "../CopilotExecutionTrace";
import SqlBlock from "../SqlBlock";
import CsvExportButton from "../CsvExportButton";
import { alertWarning, chatPanel, textDanger, userBubble } from "../../lib/themeClasses";
import ChatGptStyleBody from "./ChatGptStyleBody";

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
  beginEditUserMessage: (m: ChatMessage) => void;
  saveEditAndResubmit: () => void;
  copyMessage: (m: ChatMessage) => void;
  retryFromAssistant: (messageId: string) => void;
  continueFollowUp: (messageId: string) => void;
  onApplySuggestedDomain?: (domainId: number, question: string) => void;
};

const CopilotMessageThread = memo(function CopilotMessageThread({
  messages,
  editingMessageId,
  editingText,
  setEditingText,
  setEditingMessageId,
  beginEditUserMessage,
  saveEditAndResubmit,
  copyMessage,
  retryFromAssistant,
  continueFollowUp,
  onApplySuggestedDomain
}: CopilotMessageThreadProps) {
  return (
    <>
      {messages.map((m) => {
        const queryResult = (m.query_result || {
          ok: false,
          columns: [],
          rows: [],
          error: "历史记录无执行结果"
        }) as QueryResult;
        const isGeneralQaMessage =
          m.intent === "general_qa" ||
          (!m.sql &&
            !queryResult.ok &&
            (queryResult.error?.includes("无需SQL") || queryResult.error?.includes("无需 SQL") || false));

        if (m.role === "user") {
          if (editingMessageId === m.id) {
            return (
              <div key={m.id} className="ml-auto w-full max-w-2xl rounded-2xl bg-[var(--app-card-bg)]/70 p-3">
                <textarea
                  className="min-h-[80px] w-full resize-none rounded-xl border border-app-border bg-[var(--app-card-bg)] px-3 py-2 text-sm leading-6 text-app-primary outline-none placeholder:text-app-muted"
                  value={editingText}
                  onChange={(e) => setEditingText(e.target.value)}
                />
                <div className="mt-2 flex justify-end gap-2">
                  <button
                    type="button"
                    className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-app-border bg-[var(--app-card-bg)] px-3 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                    onClick={() => setEditingMessageId("")}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-app-primary bg-app-primary px-3 text-xs font-medium text-white transition hover:bg-[var(--app-primary-hover)]"
                    onClick={saveEditAndResubmit}
                  >
                    重新发送
                  </button>
                </div>
              </div>
            );
          }
          return (
            <div key={m.id} className="group flex min-w-0 max-w-full justify-end">
              <button
                type="button"
                className="mr-1 self-end rounded-md border border-app-border bg-[var(--app-card-bg)] px-2 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                onClick={() => beginEditUserMessage(m)}
              >
                编辑
              </button>
              <div className={`max-w-[min(100%,36rem)] shrink break-words rounded-[1.25rem] px-4 py-2.5 text-left text-[15px] leading-7 ${userBubble}`}>
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

        const traceSteps =
          m.pipeline_trace && m.pipeline_trace.length > 0
            ? filterCopilotTraceSteps(m.pipeline_trace)
            : [];
        const traceTitle = isGeneralQaMessage ? "执行检查点" : "推理检查点";
        const narrativeTrim = (narrative || "").trim();
        const showNarrative = narrativeTrim.length > 0;
        const showEmptyFallback = traceSteps.length === 0 && !showNarrative;

        return (
          <div key={m.id} className="min-w-0 max-w-full">
            <div className="flex min-w-0 max-w-full justify-start">
              <div className={`min-w-0 max-w-[min(100%,42rem)] rounded-[1.35rem] px-4 py-3 ${chatPanel}`}>
                {((m.explanation || "").includes("护栏") || (m.answer || "").includes("不能提供")) && (
                  <div className={`mb-2 rounded-lg px-3 py-2 text-xs ${alertWarning}`}>
                    该回答触发了 QA 安全边界，仅提供合规范围内的替代建议。
                  </div>
                )}
                {m.routing_trace?.domain_suggestion?.requires_confirmation &&
                  typeof m.routing_trace.domain_suggestion.domain_id === "number" &&
                  m.retry_question?.trim() && (
                    <div className={`mb-2 rounded-lg px-3 py-2 text-xs ${alertWarning}`}>
                      <p>
                        系统推荐业务域「{m.routing_trace.domain_suggestion.domain_name || m.routing_trace.domain_suggestion.domain_id}」
                        {typeof m.routing_trace.domain_suggestion.score === "number"
                          ? `（置信度 ${(m.routing_trace.domain_suggestion.score * 100).toFixed(0)}%）`
                          : ""}
                        。当前未绑定业务域，路由范围可能偏大。
                      </p>
                      {onApplySuggestedDomain ? (
                        <button
                          type="button"
                          className="mt-2 inline-flex min-h-[1.75rem] items-center justify-center rounded-full border border-app-border bg-[var(--app-card-bg)] px-3 text-[11px] font-medium text-app-primary transition hover:bg-app-hover"
                          onClick={() =>
                            onApplySuggestedDomain(
                              m.routing_trace!.domain_suggestion!.domain_id,
                              m.retry_question!.trim()
                            )
                          }
                        >
                          切换到此域并重新提问
                        </button>
                      ) : null}
                    </div>
                  )}
                {m.routing_trace?.auto_domain_applied && m.routing_trace?.domain_suggestion?.domain_name && (
                  <div className="mb-2 rounded-lg border border-app-border bg-app-chip px-3 py-2 text-xs text-app-secondary">
                    已自动绑定推荐业务域「{m.routing_trace.domain_suggestion.domain_name}」参与本次路由。
                  </div>
                )}
                {m.sql_review?.review_required && (
                  <div className={`mb-2 rounded-lg px-3 py-2 text-xs ${alertWarning}`}>
                    <p className="font-medium text-app-primary">SQL 需人工确认后再执行</p>
                    {(m.sql_review.reasons || []).map((reason) => (
                      <p key={reason} className="mt-1 text-app-secondary">
                        {reason}
                      </p>
                    ))}
                    <p className="mt-1 text-app-muted">请核对 SQL 引用的表是否在本业务域与路由候选范围内。</p>
                  </div>
                )}
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                      isGeneralQaMessage
                        ? "border-app-border bg-app-hover text-app-secondary"
                        : "border-app-activeBorder bg-app-activeBg text-app-chipText"
                    }`}
                  >
                    {isGeneralQaMessage ? "通用问答" : "SQL 分析"}
                  </span>
                </div>
                <div className="min-w-0 space-y-3">
                  {traceSteps.length > 0 ? (
                    <CopilotExecutionTrace steps={traceSteps} title={traceTitle} variant="framed" />
                  ) : null}
                  {showNarrative ? <ChatGptStyleBody text={narrativeTrim} /> : null}
                  {showEmptyFallback ? (
                    <p className="text-[15px] leading-7 text-app-secondary">（无返回）</p>
                  ) : null}
                </div>
                {!isGeneralQaMessage && (
                  <div className="mt-3 space-y-2 border-t border-app-soft pt-3">
                    <details className="rounded-lg bg-app-chip px-3 py-2" open>
                      <summary className="cursor-pointer text-xs text-app-secondary">SQL</summary>
                      <SqlBlock sql={m.sql || ""} />
                    </details>
                    <details className="rounded-lg bg-app-chip px-3 py-2" open>
                      <summary className="cursor-pointer text-xs text-app-secondary">执行结果</summary>
                      {!queryResult.ok && (
                        <p className={`mt-2 text-sm ${textDanger}`}>{queryResult.error || "查询执行失败"}</p>
                      )}
                      {!!queryResult.ok && (
                        <>
                          <div className="mt-2 max-w-full overflow-x-auto rounded-lg border border-app-border">
                            <table className="w-full min-w-0 table-auto border-collapse text-xs text-app-ink">
                              <thead>
                                <tr>
                                  {queryResult.columns.map((c) => (
                                    <th
                                      key={c}
                                      scope="col"
                                      className="border-b border-app-border bg-app-hover px-2 py-2 text-left font-medium text-app-secondary sm:px-3"
                                    >
                                      {c}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {queryResult.rows.slice(0, 20).map((row, idx) => (
                                  <tr key={idx} className="odd:bg-[var(--app-card-bg)] even:bg-app-hover">
                                    {queryResult.columns.map((c) => (
                                      <td
                                        key={`${idx}-${c}`}
                                        className="max-w-[12rem] border-b border-app-subtle px-2 py-2 align-top break-words text-app-primary sm:max-w-none sm:px-3"
                                      >
                                        {String(row[c] ?? "")}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                                {!queryResult.rows.length && (
                                  <tr>
                                    <td className="px-3 py-3 text-app-muted" colSpan={Math.max(1, queryResult.columns.length)}>
                                      查询成功但无返回数据
                                    </td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                          <div className="mt-2 flex justify-end">
                            <CsvExportButton result={queryResult} />
                          </div>
                        </>
                      )}
                    </details>
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-2 border-t border-app-soft pt-3">
                  <button
                    type="button"
                    className="rounded-md border border-app-border bg-[var(--app-card-bg)] px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                    onClick={() => copyMessage(m)}
                  >
                    复制
                  </button>
                  {!isGeneralQaMessage && (
                    <button
                      type="button"
                      className="rounded-md border border-app-border bg-[var(--app-card-bg)] px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                      onClick={() => retryFromAssistant(m.id)}
                    >
                      重试 SQL
                    </button>
                  )}
                  {isGeneralQaMessage && (
                    <button
                      type="button"
                      className="rounded-md border border-app-border bg-[var(--app-card-bg)] px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                      onClick={() => continueFollowUp(m.id)}
                    >
                      继续追问
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
});

export default CopilotMessageThread;
