"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { api } from "../../lib/api";
import { API } from "../../lib/api";
import { readUserPreferences, writeUserPreferences } from "../../lib/userPreferences";
import AssistantStructuredAnswer from "../../components/AssistantStructuredAnswer";
import Breadcrumbs from "../../components/Breadcrumbs";
import ConfirmDialog from "../../components/ConfirmDialog";
import EmptyState from "../../components/EmptyState";
import SqlBlock from "../../components/SqlBlock";
import CsvExportButton from "../../components/CsvExportButton";
import CopilotExecutionTrace from "../../components/CopilotExecutionTrace";
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
  type PipelineTraceStep,
  type QueryResult
} from "../../lib/chatSessions";

type AskResponse = {
  intent?: "sql_query" | "general_qa";
  answer?: string;
  sql: string;
  explanation: string;
  query_result: QueryResult;
  pipeline_trace?: PipelineTraceStep[];
};

type StreamStage = "intent_recognizing" | "answer_generating" | "sql_executing";

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

type AskPayload = {
  question: string;
  table_id: number | null;
  business_domain_id: number | null;
  chat_model?: string | null;
};
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
  const [livePipelineTrace, setLivePipelineTrace] = useState<PipelineTraceStep[]>([]);
  const [expandedExplanationMessageIds, setExpandedExplanationMessageIds] = useState<string[]>([]);
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

  useEffect(() => {
    if (!chatModelMenuOpen && !bizDomainMenuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setChatModelMenuOpen(false);
        setBizDomainMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chatModelMenuOpen, bizDomainMenuOpen]);

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

  useEffect(() => {
    if (loading) {
      setChatModelMenuOpen(false);
      setBizDomainMenuOpen(false);
    }
  }, [loading]);

  useEffect(() => {
    if (!sessionIdFromUrl) return;
    const state = setActiveSession(sessionIdFromUrl);
    syncState(state);
  }, [sessionIdFromUrl]);

  async function streamAsk(
    content: string,
    onStageChange?: (stage: StreamStage) => void,
    askOpts?: Partial<AskPayload>,
    onTrace?: (row: PipelineTraceStep) => void
  ) {
    const cm = askOpts?.chat_model;
    const body: AskPayload = {
      question: content,
      table_id: askOpts?.table_id ?? null,
      business_domain_id: askOpts?.business_domain_id ?? null,
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
        } else if (event === "trace") {
          const parsed = JSON.parse(data) as PipelineTraceStep;
          if (parsed && typeof parsed.id === "string" && typeof parsed.label === "string") {
            onTrace?.(parsed);
          }
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
    setLivePipelineTrace([]);
    setLoading(true);

    try {
      const tableParamNum = tableIdFromUrl ? Number(tableIdFromUrl) : NaN;
      const askPayload: AskPayload = {
        question: content,
        table_id: Number.isFinite(tableParamNum) ? tableParamNum : null,
        business_domain_id: typeof sessionAfterUser.business_domain_id === "number" ? sessionAfterUser.business_domain_id : null,
        chat_model: chatModelSelect === "auto" ? null : chatModelSelect
      };
      const traceAcc: PipelineTraceStep[] = [];
      let res: AskResponse;
      try {
        res = await streamAsk(
          content,
          (stage) => setStreamStage(stage),
          askPayload,
          (row) => {
            traceAcc.push(row);
            setLivePipelineTrace((prev) => [...prev, row]);
          }
        );
      } catch {
        res = await api<AskResponse>("/api/ask", {
          method: "POST",
          body: JSON.stringify(askPayload)
        });
      }
      const mergedPipeline: PipelineTraceStep[] | undefined = (() => {
        const fromApi = res.pipeline_trace;
        if (Array.isArray(fromApi) && fromApi.length) {
          const cleaned = fromApi.filter(
            (x): x is PipelineTraceStep =>
              !!x && typeof x === "object" && typeof x.id === "string" && typeof x.label === "string"
          );
          if (cleaned.length) return cleaned;
        }
        return traceAcc.length ? traceAcc : undefined;
      })();
      const assistantMessage: ChatMessage = {
        id: `msg-assistant-${Date.now()}`,
        role: "assistant",
        intent: res.intent,
        answer: res.answer || (res.intent === "general_qa" ? "这个问题无需执行 SQL。" : "已完成 SQL 生成与执行，请查看结果。"),
        sql: res.sql || "",
        explanation: res.explanation || "",
        query_result: res.query_result || { ok: false, columns: [], rows: [], error: "没有返回查询结果" },
        pipeline_trace: mergedPipeline,
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
      setLivePipelineTrace([]);
    }
  }

  const activeSession = useMemo(() => sessions.find((s) => s.id === activeSessionId) || null, [sessions, activeSessionId]);
  const selectedBusinessDomainTitle = useMemo(() => {
    if (!activeSession?.business_domain_id) {
      return "关联业务域后可拉取该域下配置的知识库语义检索。";
    }
    const d = businessDomains.find((x) => x.id === activeSession.business_domain_id);
    return (d?.name || "").trim() || "关联业务域后可拉取该域下配置的知识库语义检索。";
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
    <main className="flex h-screen w-full overflow-hidden bg-app-main">
      <section className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-app-main">
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

                <div className="divide-y divide-app-subtle rounded-xl bg-white/60">
                  {projectSessions.map((session) => (
                    <div
                      key={session.id}
                      className="flex w-full items-stretch gap-1 px-2 py-2 transition hover:bg-app-hover sm:px-3 sm:py-3"
                    >
                      <button
                        type="button"
                        className="min-w-0 flex-1 px-1 py-1 text-left sm:px-2"
                        onClick={() => openSessionFromProject(session.id)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="line-clamp-1 text-[18px] font-semibold text-app-primary sm:text-[20px]">{session.title}</p>
                            <p className="mt-0.5 line-clamp-1 text-[13px] text-app-secondary sm:text-[14px]">{getSessionPreview(session)}</p>
                          </div>
                          <span className="shrink-0 pt-1 text-[13px] text-app-muted sm:text-[14px]">
                            {new Date(session.updated_at).toLocaleDateString("zh-CN")}
                          </span>
                        </div>
                      </button>
                      <button
                        type="button"
                        className="shrink-0 self-center rounded-md px-2 py-1.5 text-xs text-[var(--app-danger)] hover:bg-red-50"
                        onClick={() => setPendingDeleteSessionId(session.id)}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                  {!projectSessions.length && <p className="px-3 py-10 text-center text-sm text-app-muted">该项目还没有历史对话</p>}
                </div>
              </div>
            </section>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-app-subtle px-4 py-3 sm:px-6">
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

            <section className="min-h-0 flex-1 overflow-y-auto px-4 pb-36 pt-3 sm:px-6 sm:pb-40">
              <div className="mx-auto w-full max-w-3xl space-y-6">
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
                        className="min-h-[80px] w-full resize-none rounded-xl border border-app-border bg-white px-3 py-2 text-sm leading-6 text-app-primary outline-none placeholder:text-app-muted"
                        value={editingText}
                        onChange={(e) => setEditingText(e.target.value)}
                      />
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          className="inline-flex min-h-[2rem] items-center justify-center rounded-full border border-app-border bg-white px-3 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                          onClick={() => setEditingMessageId("")}
                        >
                          取消
                        </button>
                        <button
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
                  <div key={m.id} className="group flex justify-end">
                    <button
                      className="mr-1 self-end rounded-md border border-app-border bg-white px-2 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                      onClick={() => beginEditUserMessage(m)}
                    >
                      编辑
                    </button>
                    <div className="max-w-2xl break-words rounded-2xl bg-white px-4 py-2.5 text-sm leading-relaxed text-app-primary">
                      {m.question}
                    </div>
                  </div>
                );
              }
              return (
                <div key={m.id} className="rounded-2xl border border-app-border bg-white p-4">
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
                              ? "border-app-border bg-app-hover text-app-secondary"
                              : "border-app-activeBorder bg-app-activeBg text-app-chipText"
                          }`}
                        >
                          {isGeneralQaMessage ? "通用问答" : "SQL 分析"}
                        </span>
                      </div>
                    {m.pipeline_trace && m.pipeline_trace.length > 0 ? (
                      <div className="mb-3">
                        <CopilotExecutionTrace steps={m.pipeline_trace} />
                      </div>
                    ) : null}
                    <AssistantStructuredAnswer
                      answer={m.answer}
                      explanation={m.explanation}
                      showExplanation={!isGeneralQaMessage || expandedExplanationMessageIds.includes(m.id)}
                    />
                  </div>
                  {!isGeneralQaMessage && (
                    <div className="mt-3 space-y-2 border-t border-app-soft pt-3">
                      <details className="rounded-lg bg-app-chip px-3 py-2" open>
                        <summary className="cursor-pointer text-xs text-app-secondary">SQL</summary>
                        <SqlBlock sql={m.sql || ""} />
                      </details>
                      <details className="rounded-lg bg-app-chip px-3 py-2" open>
                        <summary className="cursor-pointer text-xs text-app-secondary">执行结果</summary>
                        {!queryResult.ok && <p className="mt-2 text-sm text-rose-500">{queryResult.error || "查询执行失败"}</p>}
                        {!!queryResult.ok && (
                          <>
                          <div className="mt-2 overflow-auto rounded-lg border border-app-border">
                            <table className="min-w-[560px] border-collapse text-xs text-app-ink md:min-w-[620px]">
                              <thead>
                                <tr>
                                  {queryResult.columns.map((c) => (
                                    <th key={c} scope="col" className="border-b border-app-border bg-app-hover px-3 py-2 text-left font-medium text-app-secondary">
                                      {c}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {queryResult.rows.slice(0, 20).map((row, idx) => (
                                  <tr key={idx} className="odd:bg-white even:bg-app-hover">
                                    {queryResult.columns.map((c) => (
                                      <td key={`${idx}-${c}`} className="border-b border-app-subtle px-3 py-2 align-top text-app-primary">
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
                      className="rounded-md border border-app-border bg-white px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                      onClick={() => copyMessage(m)}
                    >
                      复制
                    </button>
                    {!isGeneralQaMessage && (
                      <button
                        className="rounded-md border border-app-border bg-white px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                        onClick={() => retryFromAssistant(m.id)}
                      >
                        重试 SQL
                      </button>
                    )}
                    {isGeneralQaMessage && (
                      <button
                        className="rounded-md border border-app-border bg-white px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
                        onClick={() => continueFollowUp(m.id)}
                      >
                        继续追问
                      </button>
                    )}
                    {isGeneralQaMessage && !!m.explanation && (
                      <button
                        className="rounded-md border border-app-border bg-white px-2.5 py-1 text-xs text-app-secondary transition hover:bg-app-hover hover:text-app-primary"
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
                <div className="max-w-full flex-1 rounded-2xl border border-app-border bg-white px-4 py-3 text-sm text-app-secondary">
                  <p className="text-sm font-medium text-app-ink">{stageLabelMap[streamStage]}...</p>
                  <div className="mt-2 flex gap-2">
                    {stageOrder.map((stage) => {
                      const activeIdx = stageOrder.indexOf(streamStage);
                      const idx = stageOrder.indexOf(stage);
                      const done = idx <= activeIdx;
                      return <span key={stage} className={`h-1.5 w-14 rounded-full ${done ? "bg-app-secondary" : "bg-app-border"}`} />;
                    })}
                  </div>
                  {livePipelineTrace.length > 0 ? (
                    <div className="mt-3 min-w-0">
                      <CopilotExecutionTrace steps={livePipelineTrace} compact />
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {!displayMessages.length && (
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

            <section className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-app-main via-app-main to-transparent px-4 pb-4 pt-8 sm:px-6 sm:pb-5">
              <div className="mx-auto w-full max-w-3xl">
                <div className="pointer-events-auto">
                <div className="copilot-dock-composer rounded-[14px] border border-app-border bg-app-card shadow-[var(--app-shadow-card)]">
                  <textarea
                    ref={questionInputRef}
                    rows={2}
                    className="max-h-[200px] min-h-[4.5rem] w-full resize-none border-0 bg-transparent px-4 pb-2 pt-3 text-[15px] leading-relaxed text-app-primary outline-none placeholder:text-app-muted focus-visible:ring-0 disabled:opacity-50"
                    placeholder="追加或继续提问…"
                    value={question}
                    maxLength={2000}
                    disabled={loading}
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
                          disabled={!llmCatalog?.has_llm || loading}
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
                            disabled={loading}
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
          </>
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
