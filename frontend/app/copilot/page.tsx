"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, formatApiError } from "../../lib/api";
import { readUserPreferences } from "../../lib/userPreferences";
import { chatModelForAsk } from "../../lib/llmPreference";
import ConfirmDialog from "../../components/ConfirmDialog";
import CopilotMessageThread from "../../components/copilot/CopilotMessageThread";
import SessionList from "../../components/copilot/SessionList";
import {
  CopilotGenerationDockStatus,
  CopilotGenerationProvider,
  CopilotStreamBubble,
  type ActiveAsk
} from "../../components/copilot/CopilotGenerationContext";
import {
  appendAssistantMessage,
  appendUserMessage,
  createSession,
  deleteSession,
  focusOrCreateUnassignedSession,
  getSessionStorageKeys,
  moveSessionToProject,
  readProjects,
  readSessionState,
  setSessionBusinessDomain,
  setActiveSession,
  type ChatProject,
  type ChatMessage,
  type ChatSession
} from "../../lib/chatSessions";
import type { AskPayload, AskResponse } from "../../lib/copilotStream";
import { getActiveBusinessDomainId, setActiveBusinessDomainId } from "../../lib/businessDomain";
import { useBusinessDomain } from "../../hooks/useBusinessDomain";

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
  const [activeAsk, setActiveAsk] = useState<ActiveAsk | null>(null);
  const settlingSessionRef = useRef<string | null>(null);
  const activeAskRef = useRef<ActiveAsk | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [projects, setProjects] = useState<ChatProject[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [editingMessageId, setEditingMessageId] = useState<string>("");
  const [editingText, setEditingText] = useState("");
  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [pendingDeleteSessionId, setPendingDeleteSessionId] = useState<string | null>(null);
  const projectIdFromUrl = searchParams.get("project") || "";
  const sessionIdFromUrl = searchParams.get("session") || "";
  const tableIdFromUrl = searchParams.get("table");
  const bottomAnchorRef = useRef<HTMLDivElement | null>(null);
  const chatScrollRef = useRef<HTMLElement | null>(null);
  const activeDomainId = useBusinessDomain();
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
    const projectParam =
      typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("project") : null;
    if (projectParam && projectParam !== "__unassigned__") {
      const created = createSession();
      if (!created.activeSessionId) return null;
      const moved = moveSessionToProject(created.activeSessionId, projectParam);
      syncState(moved);
      return moved.sessions.find((s) => s.id === moved.activeSessionId) || null;
    }
    const focused = focusOrCreateUnassignedSession();
    syncState(focused);
    return focused.sessions.find((s) => s.id === focused.activeSessionId) || null;
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
  }, [updateEvent, activeDomainId]);

  /** 表详情「去 Copilot」常用 /copilot?table=…，未带 session 时会沿用上次打开的对话骨架。与侧栏「新聊天」对齐：聚焦未归类空槽并写入 session + project + table。 */
  useLayoutEffect(() => {
    if (!tableIdFromUrl) return;
    const tid = Number(tableIdFromUrl);
    if (!Number.isFinite(tid)) return;
    if (sessionIdFromUrl) return;
    const state = focusOrCreateUnassignedSession();
    if (!state.activeSessionId) return;
    syncState(state);
    router.replace(
      `/copilot?project=__unassigned__&session=${encodeURIComponent(state.activeSessionId)}&table=${encodeURIComponent(String(tid))}`
    );
  }, [tableIdFromUrl, sessionIdFromUrl, router]);

  activeAskRef.current = activeAsk;

  useEffect(() => {
    if (!sessionIdFromUrl) return;
    const state = setActiveSession(sessionIdFromUrl);
    syncState(state);
  }, [sessionIdFromUrl]);

  const handleSettled = useCallback((res: AskResponse) => {
    const sid = settlingSessionRef.current;
    const retryQuestion = activeAskRef.current?.payload.question?.trim();
    if (!sid) {
      setActiveAsk(null);
      return;
    }
    const domainSuggestion = res.routing_trace?.domain_suggestion;
    const needsDomainConfirm =
      !!domainSuggestion?.requires_confirmation && typeof domainSuggestion.domain_id === "number";
    const assistantMessage: ChatMessage = {
      id: `msg-assistant-${Date.now()}`,
      role: "assistant",
      intent: res.intent,
      answer: res.answer || (res.intent === "general_qa" ? "这个问题无需执行 SQL。" : "已完成 SQL 生成与执行，请查看结果。"),
      sql: res.sql || "",
      explanation: res.explanation || "",
      query_result: res.query_result || { ok: false, columns: [], rows: [], error: "没有返回查询结果" },
      routing_trace: res.routing_trace,
      sql_review: res.sql_review,
      ontology_mapping: res.ontology_mapping,
      retry_question: needsDomainConfirm && retryQuestion ? retryQuestion : undefined,
      created_at: new Date().toISOString()
    };
    const next = appendAssistantMessage(sid, assistantMessage);
    syncState(next);
    setActiveAsk(null);
  }, []);

  const handleStreamFail = useCallback(async () => {
    const ask = activeAskRef.current;
    const sid = settlingSessionRef.current;
    if (!ask || !sid) {
      setActiveAsk(null);
      return;
    }
    try {
      const res = await api<AskResponse>("/api/ask", {
        method: "POST",
        body: JSON.stringify(ask.payload)
      });
      handleSettled(res);
    } catch (e: unknown) {
      const detail =
        e instanceof ApiError
          ? formatApiError(e)
          : e instanceof Error
            ? e.message
            : "请求失败，请检查后端服务或稍后重试。";
      const errorMessage: ChatMessage = {
        id: `msg-assistant-error-${Date.now()}`,
        role: "assistant",
        answer: detail,
        sql: "",
        explanation: "",
        query_result: { ok: false, columns: [], rows: [], error: "请求失败" },
        created_at: new Date().toISOString()
      };
      const next = appendAssistantMessage(sid, errorMessage);
      syncState(next);
      setActiveAsk(null);
    }
  }, [handleSettled]);

  const applySuggestedDomain = useCallback(
    (domainId: number, question: string) => {
      const sid = activeSessionId;
      if (!sid || !question.trim() || activeAsk) return;
      setActiveBusinessDomainId(domainId);
      submit(question.trim(), { activeSessionId: sid });
    },
    [activeAsk, activeSessionId]
  );

  function submit(rawContent?: string, options?: { fromMessageId?: string; activeSessionId?: string }) {
    const content = (rawContent ?? question).trim();
    if (!content || activeAsk) return;
    let currentSession =
      (options?.activeSessionId ? readSessionState().sessions.find((s) => s.id === options.activeSessionId) || null : null) || ensureActiveSession();
    if (!currentSession) return;
    const activeDomainId = getActiveBusinessDomainId();
    const sessionDomainId =
      typeof currentSession.business_domain_id === "number" && Number.isFinite(currentSession.business_domain_id)
        ? currentSession.business_domain_id
        : (typeof activeDomainId === "number" && Number.isFinite(activeDomainId) ? activeDomainId : null);
    if (
      currentSession.business_domain_id == null &&
      typeof sessionDomainId === "number" &&
      Number.isFinite(sessionDomainId)
    ) {
      const currentSessionId = currentSession.id;
      const nextState = setSessionBusinessDomain(currentSession.id, sessionDomainId);
      syncState(nextState);
      currentSession = nextState.sessions.find((s) => s.id === currentSessionId) || currentSession;
    }
    const userMessageResult = appendUserMessage(content, {
      activeSessionId: currentSession.id,
      fromMessageId: options?.fromMessageId
    });
    const sessionAfterUser = userMessageResult.session;
    syncState(userMessageResult.state);
    if (!rawContent) setQuestion("");
    setEditingMessageId("");
    setEditingText("");
    const tableParamNum = tableIdFromUrl ? Number(tableIdFromUrl) : NaN;
    const askPayload: AskPayload = {
      question: content,
      table_id: Number.isFinite(tableParamNum) ? tableParamNum : null,
      business_domain_id: sessionDomainId,
      chat_model: chatModelForAsk(readUserPreferences().chatModel)
    };
    settlingSessionRef.current = sessionAfterUser.id;
    setActiveAsk({
      key: Date.now(),
      sessionId: sessionAfterUser.id,
      payload: askPayload
    });
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

  function getSessionPreview(session: ChatSession) {
    const latestUser = [...session.messages].reverse().find((m) => m.role === "user" && m.question?.trim());
    if (latestUser?.question?.trim()) return latestUser.question.trim();
    const latestAssistant = [...session.messages].reverse().find((m) => m.role === "assistant" && m.answer?.trim());
    return latestAssistant?.answer?.trim() || "暂无内容";
  }

  function openSessionFromProject(sessionId: string) {
    router.push(`/copilot?session=${encodeURIComponent(sessionId)}`);
  }

  function removeSessionById(sessionId: string) {
    const meta = sessions.find((s) => s.id === sessionId);
    const pid = (meta?.project_id || "").trim();
    const next = deleteSession(sessionId);
    loadSessionsFromStorage();
    if (sessionIdFromUrl === sessionId) {
      if (next.activeSessionId) {
        router.push(`/copilot?session=${encodeURIComponent(next.activeSessionId)}`);
      } else {
        router.push(pid ? `/copilot?project=${encodeURIComponent(pid)}` : "/copilot?project=__unassigned__");
      }
    }
  }

  function startFromProjectLanding() {
    const content = question.trim();
    if (!content) return;
    const base =
      projectIdFromUrl === "__unassigned__"
        ? focusOrCreateUnassignedSession()
        : (() => {
            const c = createSession();
            if (!c.activeSessionId) return c;
            return moveSessionToProject(c.activeSessionId, projectIdFromUrl);
          })();
    if (!base.activeSessionId) return;
    syncState(base);
    sessionStorage.setItem(PENDING_PROJECT_QUESTION_KEY, content);
    setQuestion("");
    const sid = base.activeSessionId;
    if (projectIdFromUrl === "__unassigned__") {
      router.push(`/copilot?project=__unassigned__&session=${encodeURIComponent(sid)}`);
    } else {
      router.push(`/copilot?session=${encodeURIComponent(sid)}`);
    }
  }

  const scrollThreadNearBottom = useCallback((behavior: ScrollBehavior) => {
    const el = chatScrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior });
      return;
    }
    bottomAnchorRef.current?.scrollIntoView({ behavior });
  }, []);

  useEffect(() => {
    scrollThreadNearBottom(displayMessages.length > 0 ? "smooth" : "auto");
  }, [displayMessages.length, activeAsk?.key, scrollThreadNearBottom]);

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
    <main className="flex h-screen w-full max-w-[100vw] overflow-x-hidden overflow-y-hidden bg-app-main">
      <section className="relative flex min-h-0 min-w-0 max-w-full flex-1 flex-col overflow-hidden bg-app-main">
        {projectLandingMode ? (
          <>
            <section className="min-h-0 flex-1 overflow-y-auto px-4 py-5 text-app-primary sm:px-6">
              <div className="mx-auto w-full max-w-3xl">
                <div className="mb-5">
                  <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.01em] text-app-primary sm:text-[32px]">
                    {activeProject?.name || (projectIdFromUrl === "__unassigned__" ? "未归类" : "临时问答")}
                  </h1>
                </div>

                <div className="mb-6">
                  <div className="flex min-h-[48px] items-end gap-2 rounded-full border border-[var(--app-card-border)] bg-[var(--app-card-bg)] px-3 py-2 sm:items-center">
                    <button
                      type="button"
                      className="mb-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--app-text-secondary)] transition hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text-primary)] sm:mb-0"
                      aria-label="清空输入"
                      onClick={() => {
                        setQuestion("");
                        questionInputRef.current?.focus();
                      }}
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                    </button>
                    <textarea
                      ref={questionInputRef}
                      rows={1}
                      className="max-h-[200px] min-h-[28px] w-0 flex-1 resize-none border-0 bg-transparent py-2 text-[15px] leading-6 text-app-primary outline-none placeholder:text-app-muted focus-visible:ring-0"
                      placeholder={`${activeProject?.name || (projectIdFromUrl === "__unassigned__" ? "未归类" : "临时问答")}中的新聊天`}
                      value={question}
                      maxLength={2000}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          startFromProjectLanding();
                        }
                      }}
                    />
                  </div>
                </div>

                <h2 className="mb-2 text-left text-[13px] font-medium text-app-secondary">历史会话</h2>

                <SessionList sessions={projectSessions} getPreview={getSessionPreview} onOpen={openSessionFromProject} onDelete={setPendingDeleteSessionId} />
              </div>
            </section>
          </>
        ) : (
          <CopilotGenerationProvider activeAsk={activeAsk} onSettled={handleSettled} onStreamError={handleStreamFail}>
            <div className="border-b border-app-subtle px-4 py-2 sm:px-6">
              <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-2">
                <h1 className="truncate text-sm font-medium text-app-primary">{activeSession?.title || "新对话"}</h1>
                {activeSession ? (
                  <button
                    type="button"
                    className="shrink-0 text-xs text-app-muted hover:text-[var(--app-danger)]"
                    onClick={() => setPendingDeleteSessionId(activeSession.id)}
                  >
                    删除
                  </button>
                ) : null}
              </div>
            </div>

            <section
              ref={chatScrollRef}
              data-copilot-scroll
              className={`min-h-0 min-w-0 max-w-full flex-1 overflow-y-auto overflow-x-hidden px-4 pt-3 sm:px-6 ${activeAsk ? "pb-44 sm:pb-52" : "pb-36 sm:pb-40"}`}
            >
              <div className="mx-auto min-w-0 w-full max-w-3xl space-y-6">
            <CopilotMessageThread
              messages={displayMessages}
              editingMessageId={editingMessageId}
              editingText={editingText}
              setEditingText={setEditingText}
              setEditingMessageId={setEditingMessageId}
              saveEditAndResubmit={saveEditAndResubmit}
              copyMessage={copyMessage}
              retryFromAssistant={retryFromAssistant}
              onApplySuggestedDomain={applySuggestedDomain}
            />
            <CopilotStreamBubble />

            {!displayMessages.length && !activeAsk && (
              <div className="mx-auto mt-20 max-w-md text-center">
                <p className="text-lg font-medium text-app-primary">输入问题开始分析</p>
                <p className="mt-1 text-sm text-app-muted">支持自然语言问答与 SQL 查数</p>
                <div className="mt-4 flex flex-col gap-2">
                  {QUICK_QUESTIONS.slice(0, 2).map((item) => (
                    <button
                      key={item}
                      type="button"
                      className="rounded-lg border border-app-border px-3 py-2 text-left text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
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

            <section className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-app-main via-app-main/95 to-transparent px-4 pb-4 pt-6 sm:px-6">
              <div className="pointer-events-auto mx-auto max-w-3xl">
                <CopilotGenerationDockStatus />
                <div className="mt-1 flex items-end gap-2 rounded-2xl border border-app-border bg-app-card p-2 shadow-sm">
                  <textarea
                    ref={questionInputRef}
                    rows={2}
                    className="max-h-[160px] min-h-[2.75rem] flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-[15px] leading-relaxed text-app-primary outline-none placeholder:text-app-muted disabled:opacity-50"
                    placeholder="输入问题，Enter 发送"
                    value={question}
                    maxLength={2000}
                    disabled={!!activeAsk}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        submit();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="app-button shrink-0 disabled:opacity-40"
                    disabled={!!activeAsk || !question.trim()}
                    onClick={() => submit()}
                  >
                    发送
                  </button>
                </div>
              </div>
            </section>
          </CopilotGenerationProvider>
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

      <ConfirmDialog
        open={pendingDeleteSessionId !== null}
        title="删除对话"
        description="删除后无法恢复，确定删除该对话？"
        danger
        confirmText="删除"
        onCancel={() => setPendingDeleteSessionId(null)}
        onConfirm={() => {
          if (pendingDeleteSessionId) removeSessionById(pendingDeleteSessionId);
          setPendingDeleteSessionId(null);
        }}
      />
    </main>
  );
}

export default function CopilotPage() {
  return (
    <Suspense fallback={<main className="app-page text-app-secondary">加载中...</main>}>
      <CopilotPageContent />
    </Suspense>
  );
}
