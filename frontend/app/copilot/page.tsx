"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api";
import { API } from "../../lib/api";
import AssistantStructuredAnswer from "../../components/AssistantStructuredAnswer";
import Breadcrumbs from "../../components/Breadcrumbs";
import ConfirmDialog from "../../components/ConfirmDialog";
import EmptyState from "../../components/EmptyState";
import {
  appendAssistantMessage,
  appendUserMessage,
  createSession,
  getSessionStorageKeys,
  moveSessionToProject,
  readProjects,
  readSessionState,
  setActiveSession,
  type ChatProject,
  type ChatMessage,
  type ChatSession,
  type QueryResult
} from "../../lib/chatSessions";

type AskResponse = {
  intent?: "sql_query" | "general_qa";
  answer?: string;
  sql: string;
  explanation: string;
  query_result: QueryResult;
};

type StreamStage = "intent_recognizing" | "answer_generating" | "sql_executing";
const PENDING_PROJECT_QUESTION_KEY = "chatbi_pending_project_question_v1";
const QUICK_QUESTIONS = [
  "近30天订单量和GMV按天趋势如何？",
  "本周各渠道转化率对比，并给出异常点说明",
  "复购用户占比最近三个月变化如何？",
  "哪些地区退款率偏高？请按周统计"
];

function CopilotPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { updateEvent } = getSessionStorageKeys();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [projects, setProjects] = useState<ChatProject[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [editingMessageId, setEditingMessageId] = useState<string>("");
  const [editingText, setEditingText] = useState("");
  const [streamStage, setStreamStage] = useState<StreamStage>("intent_recognizing");
  const [expandedExplanationMessageIds, setExpandedExplanationMessageIds] = useState<string[]>([]);
  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const projectIdFromUrl = searchParams.get("project") || "";
  const sessionIdFromUrl = searchParams.get("session") || "";
  const bottomAnchorRef = useRef<HTMLDivElement | null>(null);
  const questionInputRef = useRef<HTMLTextAreaElement | null>(null);

  function loadSessionsFromStorage() {
    const state = readSessionState();
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
    setProjects(readProjects());
  }

  function syncState(state?: { sessions: ChatSession[]; activeSessionId: string }) {
    if (!state) {
      loadSessionsFromStorage();
      return;
    }
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
  }

  function ensureActiveSession() {
    const state = readSessionState();
    const existing = state.sessions.find((s) => s.id === state.activeSessionId);
    if (existing) {
      syncState(state);
      return existing;
    }
    const created = createSession();
    syncState(created);
    return created.sessions.find((s) => s.id === created.activeSessionId) || null;
  }

  useEffect(() => {
    loadSessionsFromStorage();
    const onUpdate = () => loadSessionsFromStorage();
    window.addEventListener(updateEvent, onUpdate);
    window.addEventListener("storage", onUpdate);
    return () => {
      window.removeEventListener(updateEvent, onUpdate);
      window.removeEventListener("storage", onUpdate);
    };
  }, [updateEvent]);

  useEffect(() => {
    if (!sessionIdFromUrl) return;
    const state = setActiveSession(sessionIdFromUrl);
    syncState(state);
  }, [sessionIdFromUrl]);

  async function streamAsk(content: string, onStageChange?: (stage: StreamStage) => void) {
    const resp = await fetch(`${API}/api/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: content, table_id: null })
    });
    if (!resp.ok || !resp.body) {
      throw new Error("stream not available");
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let payload = "";

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
        if (event === "chunk") {
          const parsed = JSON.parse(data) as { chunk: string };
          payload += parsed.chunk;
        } else if (event === "status") {
          const parsed = JSON.parse(data) as { stage?: StreamStage };
          if (parsed.stage) onStageChange?.(parsed.stage);
        }
      }
    }

    return JSON.parse(payload) as AskResponse;
  }

  async function submit(rawContent?: string, options?: { fromMessageId?: string; activeSessionId?: string }) {
    const content = (rawContent ?? question).trim();
    if (!content || loading) return;
    const currentSession =
      (options?.activeSessionId ? readSessionState().sessions.find((s) => s.id === options.activeSessionId) || null : null) || ensureActiveSession();
    if (!currentSession) return;
    const userMessageResult = appendUserMessage(content, {
      activeSessionId: currentSession.id,
      fromMessageId: options?.fromMessageId
    });
    const sessionAfterUser = userMessageResult.session;
    syncState(userMessageResult.state);
    if (!rawContent) setQuestion("");
    setEditingMessageId("");
    setEditingText("");
    setExpandedExplanationMessageIds([]);
    setStreamStage("intent_recognizing");
    setLoading(true);

    try {
      let res: AskResponse;
      try {
        res = await streamAsk(content, (stage) => setStreamStage(stage));
      } catch {
        res = await api<AskResponse>("/api/ask", {
          method: "POST",
          body: JSON.stringify({ question: content, table_id: null })
        });
      }
      const assistantMessage: ChatMessage = {
        id: `msg-assistant-${Date.now()}`,
        role: "assistant",
        intent: res.intent,
        answer: res.answer || (res.intent === "general_qa" ? "这个问题无需执行 SQL。" : "已完成 SQL 生成与执行，请查看结果。"),
        sql: res.sql || "",
        explanation: res.explanation || "",
        query_result: res.query_result || { ok: false, columns: [], rows: [], error: "没有返回查询结果" },
        created_at: new Date().toISOString()
      };
      const next = appendAssistantMessage(sessionAfterUser.id, assistantMessage);
      syncState(next);
    } catch {
      const errorMessage: ChatMessage = {
        id: `msg-assistant-error-${Date.now()}`,
        role: "assistant",
        answer: "请求失败，请检查后端服务或稍后重试。",
        sql: "",
        explanation: "",
        query_result: { ok: false, columns: [], rows: [], error: "请求失败" },
        created_at: new Date().toISOString()
      };
      const next = appendAssistantMessage(sessionAfterUser.id, errorMessage);
      syncState(next);
    } finally {
      setLoading(false);
      setStreamStage("intent_recognizing");
    }
  }

  const activeSession = useMemo(() => sessions.find((s) => s.id === activeSessionId) || null, [sessions, activeSessionId]);
  const displayMessages = useMemo(() => activeSession?.messages || [], [activeSession]);
  const projectLandingMode = !!projectIdFromUrl && !sessionIdFromUrl;
  const projectSessions = useMemo(() => {
    if (!projectLandingMode) return [];
    if (projectIdFromUrl === "__unassigned__") return sessions.filter((s) => !s.project_id && !s.archived_at);
    return sessions.filter((s) => s.project_id === projectIdFromUrl && !s.archived_at);
  }, [projectLandingMode, projectIdFromUrl, sessions]);
  const activeProject = useMemo(() => projects.find((p) => p.id === projectIdFromUrl) || null, [projects, projectIdFromUrl]);
  const stageLabelMap: Record<StreamStage, string> = {
    intent_recognizing: "意图识别中",
    answer_generating: "生成回答中",
    sql_executing: "执行 SQL 中"
  };
  const stageOrder: StreamStage[] = ["intent_recognizing", "answer_generating", "sql_executing"];

  function getSessionPreview(session: ChatSession) {
    const latestUser = [...session.messages].reverse().find((m) => m.role === "user" && m.question?.trim());
    if (latestUser?.question?.trim()) return latestUser.question.trim();
    const latestAssistant = [...session.messages].reverse().find((m) => m.role === "assistant" && m.answer?.trim());
    return latestAssistant?.answer?.trim() || "暂无内容";
  }

  function openSessionFromProject(sessionId: string) {
    router.push(`/copilot?session=${encodeURIComponent(sessionId)}`);
  }

  function startFromProjectLanding() {
    const content = question.trim();
    if (!content) return;
    const created = createSession();
    if (!created.activeSessionId) return;
    const targetProjectId = projectIdFromUrl === "__unassigned__" ? "" : projectIdFromUrl;
    const moved = moveSessionToProject(created.activeSessionId, targetProjectId);
    syncState(moved);
    sessionStorage.setItem(PENDING_PROJECT_QUESTION_KEY, content);
    setQuestion("");
    router.push(`/copilot?session=${encodeURIComponent(created.activeSessionId)}`);
  }

  useEffect(() => {
    bottomAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages.length, loading]);

  useEffect(() => {
    if (!sessionIdFromUrl) return;
    const pending = sessionStorage.getItem(PENDING_PROJECT_QUESTION_KEY);
    if (!pending?.trim()) return;
    sessionStorage.removeItem(PENDING_PROJECT_QUESTION_KEY);
    submit(pending, { activeSessionId: sessionIdFromUrl });
  }, [sessionIdFromUrl]);

  async function copyMessage(m: ChatMessage) {
    const text = [m.answer, m.sql ? `SQL:\n${m.sql}` : "", m.explanation ? `解释:\n${m.explanation}` : ""].filter(Boolean).join("\n\n");
    await navigator.clipboard.writeText(text || m.question || "");
  }

  function retryFromAssistant(messageId: string) {
    if (!activeSession) return;
    const idx = activeSession.messages.findIndex((m) => m.id === messageId);
    if (idx <= 0) return;
    const userMsg = [...activeSession.messages.slice(0, idx)].reverse().find((m) => m.role === "user");
    if (!userMsg?.question) return;
    submit(userMsg.question, { fromMessageId: userMsg.id });
  }

  function continueFollowUp(messageId: string) {
    if (!activeSession) return;
    const idx = activeSession.messages.findIndex((m) => m.id === messageId);
    if (idx <= 0) return;
    const userMsg = [...activeSession.messages.slice(0, idx)].reverse().find((m) => m.role === "user");
    setQuestion(userMsg?.question ? `继续基于这个问题深入：${userMsg.question}` : "继续追问上一个回答的细节：");
    questionInputRef.current?.focus();
  }

  function toggleExplanation(messageId: string) {
    setExpandedExplanationMessageIds((prev) =>
      prev.includes(messageId) ? prev.filter((id) => id !== messageId) : [...prev, messageId]
    );
  }

  function beginEditUserMessage(m: ChatMessage) {
    if (!m.question) return;
    setEditingMessageId(m.id);
    setEditingText(m.question);
  }

  function saveEditAndResubmit() {
    if (!editingText.trim()) return;
    setConfirmState({
      title: "确认提交修改？",
      description: "将基于修改后的问题重新生成后续回答。",
      confirmText: "确认提交",
      action: () => submit(editingText, { fromMessageId: editingMessageId })
    });
  }

  async function handleConfirm() {
    if (!confirmState) return;
    setConfirmLoading(true);
    try {
      await confirmState.action();
      setConfirmState(null);
    } finally {
      setConfirmLoading(false);
    }
  }

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#f7f7f8]">
      <section className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#f7f7f8]">
        {projectLandingMode ? (
          <>
            <section className="min-h-0 flex-1 overflow-y-auto px-4 py-5 text-[#111827]">
              <div className="mx-auto w-full max-w-3xl">
                <div className="mb-5 flex items-center gap-2 text-[32px] font-semibold leading-tight text-[#1f2937]">
                  <svg className="h-7 w-7 text-[#374151]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M4 7.5a2.5 2.5 0 0 1 2.5-2.5h3l1.6 1.8h6.4A2.5 2.5 0 0 1 20 9.3v7.2a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-9z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <h1 className="text-[34px] font-semibold tracking-[-0.01em]">
                    {activeProject?.name || (projectIdFromUrl === "__unassigned__" ? "未归类" : "临时问答")}
                  </h1>
                </div>

                <div className="mb-6 flex items-center gap-2 rounded-full border border-[#e5e7eb] bg-white px-3 py-2 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
                  <button
                    className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#4b5563] hover:bg-[#f3f4f6]"
                    onClick={startFromProjectLanding}
                    aria-label="新建聊天"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                  </button>
                  <textarea
                    ref={questionInputRef}
                    className="min-h-[28px] flex-1 resize-none bg-transparent text-[16px] leading-7 text-[#111827] outline-none placeholder:text-[#9ca3af]"
                    placeholder={`在${activeProject?.name || "临时问答"}中新聊天`}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        startFromProjectLanding();
                      }
                    }}
                  />
                  <div className="flex items-center gap-1">
                    <button className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#6b7280] hover:bg-[#f3f4f6]" aria-label="语音">
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <rect x="9" y="4" width="6" height="10" rx="3" stroke="currentColor" strokeWidth="1.6" />
                        <path d="M6 11a6 6 0 0 0 12 0M12 17v3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                      </svg>
                    </button>
                    <button className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#6b7280] hover:bg-[#f3f4f6]" aria-label="更多">
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <circle cx="6" cy="12" r="1.2" fill="currentColor" />
                        <circle cx="12" cy="12" r="1.2" fill="currentColor" />
                        <circle cx="18" cy="12" r="1.2" fill="currentColor" />
                      </svg>
                    </button>
                  </div>
                </div>

                <div className="mb-2 flex items-center gap-2 text-[13px]">
                  <span className="rounded-full bg-[#eceff3] px-3 py-1 font-medium text-[#111827]">聊天</span>
                  <span className="px-2 py-1 text-[#6b7280]">来源</span>
                </div>

                <div className="divide-y divide-[#eceff1] rounded-xl bg-white/55">
                  {projectSessions.map((session) => (
                    <button
                      key={session.id}
                      className="w-full px-3 py-3 text-left transition hover:bg-[#f9fafb]"
                      onClick={() => openSessionFromProject(session.id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="line-clamp-1 text-[20px] font-semibold text-[#111827]">{session.title}</p>
                          <p className="mt-0.5 line-clamp-1 text-[14px] text-[#6b7280]">{getSessionPreview(session)}</p>
                        </div>
                        <span className="shrink-0 pt-1 text-[14px] text-[#9ca3af]">{new Date(session.updated_at).toLocaleDateString("zh-CN")}</span>
                      </div>
                    </button>
                  ))}
                  {!projectSessions.length && <p className="px-3 py-10 text-center text-sm text-[#9ca3af]">该项目还没有历史对话</p>}
                </div>
              </div>
            </section>
          </>
        ) : (
          <>
            <div className="px-6 py-4">
              <Breadcrumbs
                items={[
                  { label: "首页", href: "/" },
                  { label: "Copilot", href: "/copilot" },
                  { label: activeSession?.title || "新对话" }
                ]}
              />
            </div>

            <section className="min-h-0 flex-1 overflow-y-auto px-4 pb-48 pt-2">
              <div className="mx-auto w-full max-w-3xl space-y-8">
            {displayMessages.map((m) => {
              const queryResult = m.query_result || { ok: false, columns: [], rows: [], error: "历史记录无执行结果" };
              const isGeneralQaMessage =
                m.intent === "general_qa" ||
                (!m.sql &&
                  !queryResult.ok &&
                  (queryResult.error?.includes("无需SQL") || queryResult.error?.includes("无需 SQL") || false));
              if (m.role === "user") {
                if (editingMessageId === m.id) {
                  return (
                    <div key={m.id} className="ml-auto w-full max-w-2xl rounded-2xl bg-white/70 p-3">
                      <textarea
                        className="min-h-[80px] w-full resize-none rounded-xl border border-[#e5e7eb] bg-white px-3 py-2 text-sm leading-6 text-[#111827] outline-none placeholder:text-[#9ca3af]"
                        value={editingText}
                        onChange={(e) => setEditingText(e.target.value)}
                      />
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-[#e5e7eb] bg-white px-3 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                          onClick={() => setEditingMessageId("")}
                        >
                          取消
                        </button>
                        <button
                          className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-[#111827] bg-[#111827] px-3 text-xs font-medium text-white transition hover:bg-black"
                          onClick={saveEditAndResubmit}
                        >
                          重新发送
                        </button>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={m.id} className="group flex justify-end">
                    <button
                      className="mr-1 self-end rounded-md border border-[#e5e7eb] bg-white px-2 py-1 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                      onClick={() => beginEditUserMessage(m)}
                    >
                      编辑
                    </button>
                    <div className="max-w-2xl break-words rounded-2xl bg-white px-4 py-2.5 text-sm leading-6 text-[#111827]">
                      {m.question}
                    </div>
                  </div>
                );
              }
              return (
                <div key={m.id} className="rounded-2xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                  <div className="min-w-0">
                      {((m.explanation || "").includes("护栏") || (m.answer || "").includes("不能提供")) && (
                        <div className="mb-2 rounded-lg border border-[#fcd34d] bg-[#fffbeb] px-3 py-2 text-xs text-[#92400e]">
                          该回答触发了 QA 安全边界，仅提供合规范围内的替代建议。
                        </div>
                      )}
                      <div className="mb-2 flex items-center gap-2">
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                            isGeneralQaMessage
                              ? "border-[#d1d5db] bg-[#f3f4f6] text-[#4b5563]"
                              : "border-[#cbd5e1] bg-[#eef2ff] text-[#475569]"
                          }`}
                        >
                          {isGeneralQaMessage ? "通用问答" : "SQL 分析"}
                        </span>
                      </div>
                    <AssistantStructuredAnswer
                      answer={m.answer}
                      explanation={m.explanation}
                      showExplanation={!isGeneralQaMessage || expandedExplanationMessageIds.includes(m.id)}
                    />
                  </div>
                  {!isGeneralQaMessage && (
                    <div className="mt-3 space-y-2 border-t border-[#eef2f7] pt-3">
                      <details className="rounded-lg bg-[#f8fafc] px-3 py-2" open>
                        <summary className="cursor-pointer text-xs text-[#6b7280]">SQL</summary>
                        <pre className="mt-2 overflow-x-auto rounded-lg bg-[#f3f4f6] p-3 text-xs text-[#111827]">{m.sql || "-- 无 SQL --"}</pre>
                      </details>
                      <details className="rounded-lg bg-[#f8fafc] px-3 py-2">
                        <summary className="cursor-pointer text-xs text-[#6b7280]">执行结果</summary>
                        {!queryResult.ok && <p className="mt-2 text-sm text-rose-500">{queryResult.error || "查询执行失败"}</p>}
                        {!!queryResult.ok && (
                          <div className="mt-2 overflow-auto rounded-lg border border-[#e5e7eb]">
                            <table className="min-w-[560px] border-collapse text-xs text-[#374151] md:min-w-[620px]">
                              <thead>
                                <tr>
                                  {queryResult.columns.map((c) => (
                                    <th key={c} scope="col" className="border-b border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-left font-medium text-[#6b7280]">
                                      {c}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {queryResult.rows.slice(0, 20).map((row, idx) => (
                                  <tr key={idx} className="odd:bg-white even:bg-[#fafafa]">
                                    {queryResult.columns.map((c) => (
                                      <td key={`${idx}-${c}`} className="border-b border-[#f1f5f9] px-3 py-2 align-top text-[#111827]">
                                        {String(row[c] ?? "")}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                                {!queryResult.rows.length && (
                                  <tr>
                                    <td className="px-3 py-3 text-[#9ca3af]" colSpan={Math.max(1, queryResult.columns.length)}>
                                      查询成功但无返回数据
                                    </td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </details>
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-[#eef2f7] pt-3">
                    <button
                      className="rounded-md border border-[#e5e7eb] bg-white px-2.5 py-1 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                      onClick={() => copyMessage(m)}
                    >
                      复制
                    </button>
                    {!isGeneralQaMessage && (
                      <button
                        className="rounded-md border border-[#e5e7eb] bg-white px-2.5 py-1 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                        onClick={() => retryFromAssistant(m.id)}
                      >
                        重试 SQL
                      </button>
                    )}
                    {isGeneralQaMessage && (
                      <button
                        className="rounded-md border border-[#e5e7eb] bg-white px-2.5 py-1 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                        onClick={() => continueFollowUp(m.id)}
                      >
                        继续追问
                      </button>
                    )}
                    {isGeneralQaMessage && !!m.explanation && (
                      <button
                        className="rounded-md border border-[#e5e7eb] bg-white px-2.5 py-1 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                        onClick={() => toggleExplanation(m.id)}
                      >
                        {expandedExplanationMessageIds.includes(m.id) ? "收起解释" : "展开解释"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="flex items-start">
                <div className="rounded-2xl border border-[#e5e7eb] bg-white px-4 py-3 text-sm text-[#4b5563] shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                  <p className="text-sm font-medium text-[#374151]">{stageLabelMap[streamStage]}...</p>
                  <div className="mt-2 flex gap-2">
                    {stageOrder.map((stage) => {
                      const activeIdx = stageOrder.indexOf(streamStage);
                      const idx = stageOrder.indexOf(stage);
                      const done = idx <= activeIdx;
                      return <span key={stage} className={`h-1.5 w-14 rounded-full ${done ? "bg-[#6b7280]" : "bg-[#d1d5db]"}`} />;
                    })}
                  </div>
                </div>
              </div>
            )}

            {!displayMessages.length && (
              <div className="mx-auto mt-16 max-w-xl text-center">
                <p className="text-[1.75rem] font-semibold text-[#111827]">今天想分析什么数据？</p>
                <p className="mt-2 text-sm text-[#6b7280]">输入业务问题即可，我会生成 SQL、执行并解释关键结论。</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {QUICK_QUESTIONS.map((item) => (
                    <button
                      key={item}
                      className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-[#e5e7eb] bg-white px-3 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
                      onClick={() => {
                        setQuestion(item);
                        questionInputRef.current?.focus();
                      }}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div ref={bottomAnchorRef} />
          </div>
            </section>

            <section className="pointer-events-none absolute inset-x-0 bottom-0 z-10 px-3 pb-5 pt-10">
              <div className="mx-auto w-full max-w-3xl space-y-0">
                <div className="h-14 rounded-t-[1.8rem] bg-gradient-to-t from-[#f7f7f8] via-[#f7f7f8]/80 to-transparent" />
                <div className="pointer-events-auto -mt-2">
                <div className="rounded-[1.7rem] border border-[#e5e7eb] bg-white p-2 shadow-[0_10px_28px_rgba(15,23,42,0.12)]">
                  <textarea
                    ref={questionInputRef}
                    className="min-h-[86px] w-full resize-none bg-transparent px-2 py-2 text-sm leading-6 text-[#111827] outline-none placeholder:text-[#9ca3af]"
                    placeholder="例如：近30天各渠道订单转化率趋势，并标注异常波动日期"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        submit();
                      }
                    }}
                  />
                  <div className="flex items-center justify-end gap-2 px-1 pb-1">
                    <p className="mr-auto self-center text-xs text-[#9ca3af]">Enter 发送，Shift+Enter 换行</p>
                    <button className={`inline-flex min-h-[2.1rem] items-center justify-center rounded-full border border-[#111827] bg-[#111827] px-4 text-sm font-medium text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-60 ${loading ? "is-loading" : ""}`} onClick={() => submit()} disabled={loading || !question.trim()}>
                      {loading ? "生成中..." : "发送"}
                    </button>
                  </div>
                </div>
                </div>
              </div>
            </section>
          </>
        )}
      </section>

      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || ""}
        description={confirmState?.description}
        confirmText={confirmState?.confirmText}
        danger={!!confirmState?.danger}
        loading={confirmLoading}
        onCancel={() => setConfirmState(null)}
        onConfirm={handleConfirm}
      />
    </main>
  );
}

export default function CopilotPage() {
  return (
    <Suspense fallback={<main className="app-page text-[#6b7280]">加载中...</main>}>
      <CopilotPageContent />
    </Suspense>
  );
}
