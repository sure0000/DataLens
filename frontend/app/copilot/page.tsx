"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { api } from "../../lib/api";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { readUserPreferences, writeUserPreferences } from "../../lib/userPreferences";
import Breadcrumbs from "../../components/Breadcrumbs";
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
  setActiveSession,
  setSessionBusinessDomain,
  type ChatProject,
  type ChatMessage,
  type ChatSession,
  filterCopilotTraceSteps,
  stripStreamEphemeralTraceSteps,
  type PipelineTraceStep
} from "../../lib/chatSessions";
import type { AskPayload, AskResponse } from "../../lib/copilotStream";

type LlmCatalog = {
  auto_id: string;
  auto_label: string;
  auto_resolved: string;
  auto_resolved_label?: string;
  models: {
    id: string;
    label: string;
    provider: string;
    kind_label: string;
    connection_name: string;
    model_id: string;
    model_short_label?: string;
    model_family?: string;
  }[];
  has_llm: boolean;
};

/** 对话模型下拉：仅展示接入自定义名与模型 ID（与偏好设置中的命名一致） */
function formatPreferenceModelDisplay(m: LlmCatalog["models"][number]): string {
  const name = (m.connection_name || "").trim();
  const mid = (m.model_id || "").trim();
  if (name && mid) return `${name} · ${mid}`;
  if (name) return name;
  if (mid) return mid;
  return m.label;
}

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
  const [businessDomains, setBusinessDomains] = useState<{ id: number; name: string }[]>([]);
  const [llmCatalog, setLlmCatalog] = useState<LlmCatalog | null>(null);
  const [chatModelSelect, setChatModelSelect] = useState("auto");
  const projectIdFromUrl = searchParams.get("project") || "";
  const sessionIdFromUrl = searchParams.get("session") || "";
  const tableIdFromUrl = searchParams.get("table");
  const bottomAnchorRef = useRef<HTMLDivElement | null>(null);
  const chatScrollRef = useRef<HTMLElement | null>(null);
  const questionInputRef = useRef<HTMLTextAreaElement | null>(null);
  const chatModelDropdownRef = useRef<HTMLDivElement | null>(null);
  const chatModelMenuPortalRef = useRef<HTMLUListElement | null>(null);
  const [chatModelMenuOpen, setChatModelMenuOpen] = useState(false);
  const [chatModelMenuFixedStyle, setChatModelMenuFixedStyle] = useState<CSSProperties | null>(null);
  const bizDomainDropdownRef = useRef<HTMLDivElement | null>(null);
  const bizDomainMenuPortalRef = useRef<HTMLUListElement | null>(null);
  const [bizDomainMenuOpen, setBizDomainMenuOpen] = useState(false);
  const [bizDomainMenuFixedStyle, setBizDomainMenuFixedStyle] = useState<CSSProperties | null>(null);

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
  }, [updateEvent]);

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

  useEffect(() => {
    api<{ domains: { id: number; name: string }[] }>("/api/business-domains")
      .then((r) => setBusinessDomains(r.domains || []))
      .catch(() => setBusinessDomains([]));
  }, []);

  /** 与偏好设置「可选模型」一致：仅用户新增的接入，不含环境变量内置的 DeepSeek/OpenAI 条目 */
  const preferenceChatModels = useMemo(() => {
    if (!llmCatalog?.has_llm) return [];
    return llmCatalog.models.filter((m) => m.model_family === "custom" || m.id.startsWith("conn:"));
  }, [llmCatalog]);

  const chatModelChoiceIds = useMemo(() => {
    if (!llmCatalog) return new Set<string>();
    return new Set([llmCatalog.auto_id, ...preferenceChatModels.map((m) => m.id)]);
  }, [llmCatalog, preferenceChatModels]);

  const chatModelDisplayFull = useMemo(() => {
    if (!llmCatalog?.has_llm) return "未配置 LLM";
    if (chatModelSelect === llmCatalog.auto_id) return "自动";
    const m = preferenceChatModels.find((x) => x.id === chatModelSelect);
    return m ? formatPreferenceModelDisplay(m) : "自动";
  }, [llmCatalog, chatModelSelect, preferenceChatModels]);

  const chatModelButtonTitle = useMemo(() => {
    if (!llmCatalog?.has_llm) return undefined;
    if (chatModelSelect === llmCatalog.auto_id) return undefined;
    const m = preferenceChatModels.find((x) => x.id === chatModelSelect);
    return m ? formatPreferenceModelDisplay(m) : undefined;
  }, [llmCatalog, chatModelSelect, preferenceChatModels]);

  useEffect(() => {
    api<LlmCatalog>("/api/llm/catalog")
      .then((c) => {
        setLlmCatalog(c);
        const pref = readUserPreferences().chatModel;
        const ids = new Set([
          c.auto_id,
          ...c.models.filter((m) => m.model_family === "custom" || m.id.startsWith("conn:")).map((m) => m.id)
        ]);
        setChatModelSelect(ids.has(pref) ? pref : c.auto_id);
      })
      .catch(() => setLlmCatalog(null));
  }, []);

  useEffect(() => {
    const onPrefs = () => {
      const pref = readUserPreferences().chatModel;
      setChatModelSelect((prev) => {
        if (!llmCatalog) return pref;
        return chatModelChoiceIds.has(pref) ? pref : llmCatalog.auto_id;
      });
    };
    window.addEventListener("datalens-user-prefs-updated", onPrefs);
    return () => window.removeEventListener("datalens-user-prefs-updated", onPrefs);
  }, [llmCatalog, chatModelChoiceIds]);

  useEscapeKey(() => { setChatModelMenuOpen(false); setBizDomainMenuOpen(false); }, chatModelMenuOpen || bizDomainMenuOpen);

  useEffect(() => {
    if (!chatModelMenuOpen && !bizDomainMenuOpen) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (chatModelMenuOpen) {
        if (!chatModelDropdownRef.current?.contains(t) && !chatModelMenuPortalRef.current?.contains(t)) {
          setChatModelMenuOpen(false);
        }
      }
      if (bizDomainMenuOpen) {
        if (!bizDomainDropdownRef.current?.contains(t) && !bizDomainMenuPortalRef.current?.contains(t)) {
          setBizDomainMenuOpen(false);
        }
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [chatModelMenuOpen, bizDomainMenuOpen]);

  useLayoutEffect(() => {
    if (!chatModelMenuOpen || !llmCatalog?.has_llm) {
      setChatModelMenuFixedStyle(null);
      return;
    }
    function updatePosition() {
      const el = chatModelDropdownRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const margin = 8;
      const maxHCap = Math.min(window.innerHeight * 0.5, 256);
      const spaceAbove = rect.top - margin;
      const spaceBelow = window.innerHeight - rect.bottom - margin;
      const preferAbove = spaceAbove >= 64 && spaceAbove >= spaceBelow - 40;
      const minW = rect.width;
      const left = Math.max(margin, Math.min(rect.left, window.innerWidth - minW - margin));
      if (preferAbove) {
        const maxH = Math.min(maxHCap, Math.max(64, spaceAbove - 4));
        setChatModelMenuFixedStyle({
          position: "fixed",
          left,
          top: rect.top - 4,
          minWidth: minW,
          maxHeight: maxH,
          transform: "translateY(-100%)",
          zIndex: 200
        });
      } else {
        const maxH = Math.min(maxHCap, Math.max(64, spaceBelow - 4));
        setChatModelMenuFixedStyle({
          position: "fixed",
          left,
          top: rect.bottom + 4,
          minWidth: minW,
          maxHeight: maxH,
          transform: "none",
          zIndex: 200
        });
      }
    }
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [chatModelMenuOpen, llmCatalog?.has_llm]);

  activeAskRef.current = activeAsk;

  useEffect(() => {
    if (activeAsk) {
      setChatModelMenuOpen(false);
      setBizDomainMenuOpen(false);
    }
  }, [activeAsk]);

  useEffect(() => {
    if (!sessionIdFromUrl) return;
    const state = setActiveSession(sessionIdFromUrl);
    syncState(state);
  }, [sessionIdFromUrl]);

  const handleSettled = useCallback((res: AskResponse, traceAcc: PipelineTraceStep[]) => {
    const sid = settlingSessionRef.current;
    if (!sid) {
      setActiveAsk(null);
      return;
    }
    const mergedPipeline: PipelineTraceStep[] | undefined = (() => {
      const fromApi = res.pipeline_trace;
      if (Array.isArray(fromApi) && fromApi.length) {
        const cleaned = fromApi.filter(
          (x): x is PipelineTraceStep =>
            !!x && typeof x === "object" && typeof x.id === "string" && typeof x.label === "string"
        );
        if (cleaned.length) return filterCopilotTraceSteps(cleaned);
      }
      return traceAcc.length ? filterCopilotTraceSteps(stripStreamEphemeralTraceSteps(traceAcc)) : undefined;
    })();
    const assistantMessage: ChatMessage = {
      id: `msg-assistant-${Date.now()}`,
      role: "assistant",
      intent: res.intent,
      answer: res.answer || (res.intent === "general_qa" ? "这个问题无需执行 SQL。" : "已完成 SQL 生成与执行，请查看结果。"),
      sql: res.sql || "",
      explanation: res.explanation || "",
      query_result: res.query_result || { ok: false, columns: [], rows: [], error: "没有返回查询结果" },
      pipeline_trace: mergedPipeline?.length ? mergedPipeline : undefined,
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
      handleSettled(res, []);
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
      const next = appendAssistantMessage(sid, errorMessage);
      syncState(next);
      setActiveAsk(null);
    }
  }, [handleSettled]);

  function submit(rawContent?: string, options?: { fromMessageId?: string; activeSessionId?: string }) {
    const content = (rawContent ?? question).trim();
    if (!content || activeAsk) return;
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
    const tableParamNum = tableIdFromUrl ? Number(tableIdFromUrl) : NaN;
    const askPayload: AskPayload = {
      question: content,
      table_id: Number.isFinite(tableParamNum) ? tableParamNum : null,
      business_domain_id: typeof sessionAfterUser.business_domain_id === "number" ? sessionAfterUser.business_domain_id : null,
      chat_model: chatModelSelect === "auto" ? null : chatModelSelect
    };
    settlingSessionRef.current = sessionAfterUser.id;
    setActiveAsk({
      key: Date.now(),
      sessionId: sessionAfterUser.id,
      payload: askPayload
    });
  }

  const activeSession = useMemo(() => sessions.find((s) => s.id === activeSessionId) || null, [sessions, activeSessionId]);
  const selectedBusinessDomainTitle = useMemo(() => {
    if (!activeSession?.business_domain_id) {
      return "选择业务域后：将该域挂载的全部数据表元数据纳入问数上下文，并启用域内知识库语义检索。";
    }
    const d = businessDomains.find((x) => x.id === activeSession.business_domain_id);
    return (d?.name || "").trim() || "选择业务域后：将该域挂载的全部数据表元数据纳入问数上下文，并启用域内知识库语义检索。";
  }, [activeSession, businessDomains]);

  const businessDomainDisplayFull = useMemo(() => {
    if (!activeSession) return "不关联";
    const id = activeSession.business_domain_id;
    if (id == null || id === undefined) return "不关联";
    const d = businessDomains.find((x) => x.id === id);
    return (d?.name || "").trim() || "不关联";
  }, [activeSession, businessDomains]);

  useLayoutEffect(() => {
    if (!bizDomainMenuOpen) {
      setBizDomainMenuFixedStyle(null);
      return;
    }
    function updatePosition() {
      const el = bizDomainDropdownRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const margin = 8;
      const maxHCap = Math.min(window.innerHeight * 0.5, 256);
      const spaceAbove = rect.top - margin;
      const spaceBelow = window.innerHeight - rect.bottom - margin;
      const preferAbove = spaceAbove >= 64 && spaceAbove >= spaceBelow - 40;
      const minW = rect.width;
      const left = Math.max(margin, Math.min(rect.left, window.innerWidth - minW - margin));
      if (preferAbove) {
        const maxH = Math.min(maxHCap, Math.max(64, spaceAbove - 4));
        setBizDomainMenuFixedStyle({
          position: "fixed",
          left,
          top: rect.top - 4,
          minWidth: minW,
          maxHeight: maxH,
          transform: "translateY(-100%)",
          zIndex: 200
        });
      } else {
        const maxH = Math.min(maxHCap, Math.max(64, spaceBelow - 4));
        setBizDomainMenuFixedStyle({
          position: "fixed",
          left,
          top: rect.bottom + 4,
          minWidth: minW,
          maxHeight: maxH,
          transform: "none",
          zIndex: 200
        });
      }
    }
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [bizDomainMenuOpen]);

  const chatBreadcrumbItems = useMemo(() => {
    const title = activeSession?.title || "新对话";
    const pid = (activeSession?.project_id || "").trim();
    if (!pid) {
      return [
        { label: "首页", href: "/" },
        { label: "未归类", href: "/copilot?project=__unassigned__" },
        { label: title }
      ];
    }
    const p = projects.find((x) => x.id === pid);
    if (p) {
      return [
        { label: "首页", href: "/" },
        { label: p.name, href: `/copilot?project=${encodeURIComponent(pid)}` },
        { label: title }
      ];
    }
    return [
      { label: "首页", href: "/" },
      { label: "未知项目", href: "/copilot" },
      { label: title }
    ];
  }, [activeSession, projects]);
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

  function continueFollowUp(messageId: string) {
    if (!activeSession) return;
    const idx = activeSession.messages.findIndex((m) => m.id === messageId);
    if (idx <= 0) return;
    const userMsg = [...activeSession.messages.slice(0, idx)].reverse().find((m) => m.role === "user");
    setQuestion(userMsg?.question ? `继续基于这个问题深入：${userMsg.question}` : "继续追问上一个回答的细节：");
    questionInputRef.current?.focus();
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
                  <div className="flex min-h-[48px] items-end gap-2 rounded-full border border-neutral-200 bg-white px-3 py-2 shadow-[0_1px_2px_rgba(15,23,42,0.05)] sm:items-center">
                    <button
                      type="button"
                      className="mb-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-800 sm:mb-0"
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
                      className="max-h-[200px] min-h-[28px] w-0 flex-1 resize-none border-0 bg-transparent py-2 text-[15px] leading-6 text-neutral-900 outline-none placeholder:text-neutral-400 focus-visible:ring-0"
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
            <div className="border-b border-app-subtle px-4 py-3 sm:px-6">
              <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center justify-between gap-2">
                <Breadcrumbs items={chatBreadcrumbItems} />
                {activeSession ? (
                  <button
                    type="button"
                    className="shrink-0 text-sm text-[var(--app-danger)] hover:underline"
                    onClick={() => setPendingDeleteSessionId(activeSession.id)}
                  >
                    删除对话
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
              beginEditUserMessage={beginEditUserMessage}
              saveEditAndResubmit={saveEditAndResubmit}
              copyMessage={copyMessage}
              retryFromAssistant={retryFromAssistant}
              continueFollowUp={continueFollowUp}
            />
            <CopilotStreamBubble />

            {!displayMessages.length && !activeAsk && (
              <div className="mx-auto mt-16 max-w-xl text-center">
                <p className="text-[1.75rem] font-semibold text-app-primary">今天想分析什么数据？</p>
                <p className="mt-2 text-sm text-app-secondary">输入业务问题即可，我会生成 SQL、执行并解释关键结论。</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {QUICK_QUESTIONS.map((item) => (
                    <button
                      key={item}
                      className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-app-border bg-white px-3 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
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

            <section className="pointer-events-none absolute inset-x-0 bottom-0 z-10 max-w-full bg-gradient-to-t from-app-main from-35% via-app-main/98 to-transparent px-4 pb-4 pt-10 sm:px-6 sm:pb-5">
              <div className="mx-auto flex min-w-0 max-w-3xl flex-col gap-2">
                <CopilotGenerationDockStatus />
                <div className="pointer-events-auto min-w-0">
                <div className="copilot-dock-composer rounded-[14px] border border-app-border bg-app-card shadow-[var(--app-shadow-card)]">
                  <textarea
                    ref={questionInputRef}
                    rows={2}
                    className="max-h-[200px] min-h-[4.5rem] w-full resize-none border-0 bg-transparent px-4 pb-2 pt-3 text-[15px] leading-relaxed text-app-primary outline-none placeholder:text-app-muted focus-visible:ring-0 disabled:opacity-50"
                    placeholder="追加或继续提问…"
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
                  <div className="flex flex-nowrap items-center justify-between gap-2 px-3 py-2.5">
                    <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                      <div
                        ref={chatModelDropdownRef}
                        className="relative inline-flex min-h-[2rem] w-max shrink-0 items-center gap-1.5 rounded-full border border-app-border bg-app-hover px-2.5 py-1.5"
                      >
                        <span className="select-none shrink-0 text-[13px] leading-none text-app-secondary" aria-hidden title="模型">
                          ∞
                        </span>
                        <button
                          type="button"
                          disabled={!llmCatalog?.has_llm || !!activeAsk}
                          title={chatModelButtonTitle}
                          aria-expanded={chatModelMenuOpen}
                          aria-haspopup="listbox"
                          className="flex cursor-pointer items-center gap-1 rounded-md py-0.5 text-left text-xs font-medium text-app-primary outline-none focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
                          onClick={() => {
                            setBizDomainMenuOpen(false);
                            setChatModelMenuOpen((o) => !o);
                          }}
                        >
                          <span className="whitespace-nowrap leading-snug">{chatModelDisplayFull}</span>
                          <svg
                            className={`h-3.5 w-3.5 shrink-0 text-app-secondary transition-transform ${chatModelMenuOpen ? "rotate-180" : ""}`}
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            aria-hidden
                          >
                            <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </button>
                      </div>
                      {activeSession ? (
                        <div
                          ref={bizDomainDropdownRef}
                          className="relative inline-flex min-h-[2rem] w-max shrink-0 items-center gap-1.5 rounded-full border border-app-border bg-app-hover px-2.5 py-1.5"
                        >
                          <span className="shrink-0 text-app-secondary" aria-hidden title="业务域">
                            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
                              <path d="M4 5h7v6H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 13h7v6H4z" strokeLinejoin="round" />
                            </svg>
                          </span>
                          <button
                            type="button"
                            disabled={!!activeAsk}
                            title={activeSession.business_domain_id ? selectedBusinessDomainTitle : undefined}
                            aria-expanded={bizDomainMenuOpen}
                            aria-haspopup="listbox"
                            className="flex cursor-pointer items-center gap-1 rounded-md py-0.5 text-left text-xs font-medium text-app-primary outline-none focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
                            onClick={() => {
                              setChatModelMenuOpen(false);
                              setBizDomainMenuOpen((o) => !o);
                            }}
                          >
                            <span className="whitespace-nowrap leading-snug">{businessDomainDisplayFull}</span>
                            <svg
                              className={`h-3.5 w-3.5 shrink-0 text-app-secondary transition-transform ${bizDomainMenuOpen ? "rotate-180" : ""}`}
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              aria-hidden
                            >
                              <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </button>
                        </div>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {question.length > 1800 && (
                        <span className="text-[10px] text-amber-600">{question.length}/2000</span>
                      )}
                      {tableIdFromUrl && Number.isFinite(Number(tableIdFromUrl)) && (
                        <span
                          className="max-w-[4.5rem] truncate text-[10px] text-app-secondary"
                          title={`URL 已指定数据表 ID ${tableIdFromUrl}，请求将带上表级知识库与固定条目`}
                        >
                          表 {tableIdFromUrl}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                </div>
              </div>
            </section>
          </CopilotGenerationProvider>
        )}
      </section>

      {typeof document !== "undefined" &&
        chatModelMenuOpen &&
        llmCatalog &&
        llmCatalog.has_llm &&
        chatModelMenuFixedStyle &&
        createPortal(
          <ul
            ref={chatModelMenuPortalRef}
            role="listbox"
            style={chatModelMenuFixedStyle}
            className="w-max overflow-auto rounded-xl border border-app-border bg-app-card py-1 shadow-[var(--app-shadow-card)]"
          >
            <li role="none">
              <button
                type="button"
                role="option"
                aria-selected={chatModelSelect === llmCatalog.auto_id}
                className={`flex w-full px-3 py-2 text-left text-xs ${
                  chatModelSelect === llmCatalog.auto_id
                    ? "bg-app-activeBg font-medium text-app-chipText"
                    : "text-app-primary hover:bg-app-hover"
                }`}
                onClick={() => {
                  setChatModelSelect(llmCatalog.auto_id);
                  writeUserPreferences({ chatModel: llmCatalog.auto_id });
                  setChatModelMenuOpen(false);
                }}
              >
                自动
              </button>
            </li>
            {preferenceChatModels.map((m) => {
              const line = formatPreferenceModelDisplay(m);
              return (
                <li key={m.id} role="none">
                  <button
                    type="button"
                    role="option"
                    aria-selected={chatModelSelect === m.id}
                    className={`flex w-full px-3 py-2 text-left text-xs whitespace-nowrap ${
                      chatModelSelect === m.id
                        ? "bg-app-activeBg font-medium text-app-chipText"
                        : "text-app-primary hover:bg-app-hover"
                    }`}
                    onClick={() => {
                      setChatModelSelect(m.id);
                      writeUserPreferences({ chatModel: m.id });
                      setChatModelMenuOpen(false);
                    }}
                  >
                    {line}
                  </button>
                </li>
              );
            })}
          </ul>,
          document.body
        )}

      {typeof document !== "undefined" &&
        bizDomainMenuOpen &&
        activeSession &&
        bizDomainMenuFixedStyle &&
        createPortal(
          <ul
            ref={bizDomainMenuPortalRef}
            role="listbox"
            style={bizDomainMenuFixedStyle}
            className="w-max overflow-auto rounded-xl border border-app-border bg-app-card py-1 shadow-[var(--app-shadow-card)]"
          >
            <li role="none">
              <button
                type="button"
                role="option"
                aria-selected={activeSession.business_domain_id == null}
                className={`flex w-full px-3 py-2 text-left text-xs ${
                  activeSession.business_domain_id == null
                    ? "bg-app-activeBg font-medium text-app-chipText"
                    : "text-app-primary hover:bg-app-hover"
                }`}
                onClick={() => {
                  setSessionBusinessDomain(activeSession.id, undefined);
                  loadSessionsFromStorage();
                  setBizDomainMenuOpen(false);
                }}
              >
                不关联
              </button>
            </li>
            {businessDomains.map((d) => (
              <li key={d.id} role="none">
                <button
                  type="button"
                  role="option"
                  aria-selected={activeSession.business_domain_id === d.id}
                  className={`flex w-full px-3 py-2 text-left text-xs whitespace-nowrap ${
                    activeSession.business_domain_id === d.id
                      ? "bg-app-activeBg font-medium text-app-chipText"
                      : "text-app-primary hover:bg-app-hover"
                  }`}
                  onClick={() => {
                    setSessionBusinessDomain(activeSession.id, d.id);
                    loadSessionsFromStorage();
                    setBizDomainMenuOpen(false);
                  }}
                >
                  {d.name}
                </button>
              </li>
            ))}
          </ul>,
          document.body
        )}

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
