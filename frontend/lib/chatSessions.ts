import { getActiveBusinessDomainId } from "./businessDomain";

export type QueryResult = {
  ok: boolean;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count?: number;
  error?: string;
  review_required?: boolean;
};

export type DomainSuggestion = {
  domain_id: number;
  domain_name?: string;
  score?: number;
  requires_confirmation?: boolean;
  auto_applicable?: boolean;
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
  /** 完整映射句：问题如何对应到本体资产 */
  description?: string;
  /** 匹配类型：exact（标签/别名出现在问题中）| semantic（语义推断） */
  match_type?: string;
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

export type RoutingTrace = {
  routing_mode?: string;
  candidate_table_count?: number;
  candidate_table_ids?: number[];
  candidate_sources?: Record<string, string[]>;
  fallback_reason?: string;
  top_table_scores?: { table_id: number; fq_name: string; score: number; sources: string[] }[];
  domain_suggestion?: DomainSuggestion | null;
  auto_domain_applied?: boolean;
  embed_calls?: number;
  kb_search_calls?: number;
  ontology_trace?: { iri?: string; label?: string; type?: string; source?: string; match_score?: number; maps_to?: string; match_type?: string }[];
};

export type SqlReview = {
  review_required?: boolean;
  trust_level?: string;
  execution_mode?: string;
  reasons?: string[];
  sql_table_ids?: number[];
  out_of_domain_table_ids?: number[];
  outside_candidate_table_ids?: number[];
};

/** 管线 trace 中可点击跳转的实体（由后端 matches 定位原文子串） */
export type TraceEntityLinkKind = "table" | "datasource" | "database" | "business_domain" | "knowledge_base";

export type TraceEntityLink = {
  kind: TraceEntityLinkKind;
  id?: number;
  datasource_id?: number;
  database_name?: string;
  matches: string[];
};

const TRACE_ENTITY_LINK_KINDS: TraceEntityLinkKind[] = [
  "table",
  "datasource",
  "database",
  "business_domain",
  "knowledge_base"
];

function normalizeTraceEntityLinks(raw: unknown): TraceEntityLink[] | undefined {
  if (!Array.isArray(raw) || !raw.length) return undefined;
  const out: TraceEntityLink[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const kind = o.kind;
    if (typeof kind !== "string" || !TRACE_ENTITY_LINK_KINDS.includes(kind as TraceEntityLinkKind)) continue;
    const matchesRaw = o.matches;
    if (!Array.isArray(matchesRaw)) continue;
    const matches = matchesRaw.filter((m): m is string => typeof m === "string" && m.trim().length > 0);
    if (!matches.length) continue;
    const id = typeof o.id === "number" ? o.id : undefined;
    const datasource_id = typeof o.datasource_id === "number" ? o.datasource_id : undefined;
    const database_name = typeof o.database_name === "string" ? o.database_name : undefined;
    out.push({
      kind: kind as TraceEntityLinkKind,
      id,
      datasource_id,
      database_name,
      matches
    });
  }
  return out.length ? out : undefined;
}

/** 后端 pipeline_trace / SSE trace：从用户输入到 SQL 的步骤说明 */
export type PipelineTraceStep = {
  id: string;
  label: string;
  detail?: string;
  /** 可选：与 detail 文案对应的站内详情链接 */
  links?: TraceEntityLink[];
};

/** 对话展示用：隐藏内部 SQL 修复步骤，以及「SQL 执行失败」类 trace（错误已在正文 / 执行结果区呈现） */
/** 流式阶段临时进度（不入库） */
export function stripStreamEphemeralTraceSteps(steps: PipelineTraceStep[]): PipelineTraceStep[] {
  return steps.filter((s) => !s.id.startsWith("live_"));
}

export function filterCopilotTraceSteps(steps: PipelineTraceStep[]): PipelineTraceStep[] {
  return steps.filter((s) => {
    if (s.id === "sql_repair" || s.id === "sql_repair_result") return false;
    if (s.id !== "sql_execute") return true;
    const d = (s.detail || "").trim();
    if (/成功[：:]/.test(d)) return true;
    if (/未成功|^失败|失败[：:]/.test(d)) return false;
    return true;
  });
}

/** 对话页默认只展示对用户有意义的步骤，避免冗长推理检查点 */
const SIMPLE_TRACE_STEP_IDS = new Set([
  "reasoning_1",
  "ontology_match",
  "sql_decision",
  "reasoning_gq",
  "reasoning_4",
  "reasoning_7",
  "routing_review",
  "routing_meta",
]);

export function compactCopilotTraceSteps(steps: PipelineTraceStep[]): PipelineTraceStep[] {
  return filterCopilotTraceSteps(steps).filter((s) => SIMPLE_TRACE_STEP_IDS.has(s.id));
}

/** 流式 / 持久化 trace：同 id 步骤以最新一条为准 */
export function upsertPipelineTraceStep(steps: PipelineTraceStep[], row: PipelineTraceStep): PipelineTraceStep[] {
  const idx = steps.findIndex((s) => s.id === row.id);
  if (idx === -1) return [...steps, row];
  const next = [...steps];
  next[idx] = row;
  return next;
}

/** 推导面板用 trace：去掉与 OntologyMappingBlock 重复的 ontology_match */
export function traceStepsForDerivationPanel(steps: PipelineTraceStep[], hasOntologyMapping: boolean): PipelineTraceStep[] {
  const compact = compactCopilotTraceSteps(steps);
  if (!hasOntologyMapping) return compact;
  return compact.filter((s) => s.id !== "ontology_match");
}

export type SqlDerivationOntologyUsage = {
  ontology_label?: string;
  ontology_kind?: string;
  sql_role?: string;
  sql_fragment?: string;
  rationale?: string;
};

export type SqlDerivation = {
  pattern?: string;
  ontology_usage?: SqlDerivationOntologyUsage[];
  assumptions?: string[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  intent?: "sql_query" | "general_qa";
  question?: string;
  answer?: string;
  sql?: string;
  explanation?: string;
  referenced_columns?: string[];
  sql_derivation?: SqlDerivation;
  query_result?: QueryResult;
  pipeline_trace?: PipelineTraceStep[];
  routing_trace?: RoutingTrace;
  sql_review?: SqlReview;
  ontology_mapping?: OntologyMapping;
  /** 域推荐确认后用于「切换域并重试」的原问题 */
  retry_question?: string;
  created_at: string;
};

export type ChatSession = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  pinned?: boolean;
  project_id?: string;
  archived_at?: string;
  /** 关联业务域，用于拉取该域下配置的知识库上下文 */
  business_domain_id?: number;
  messages: ChatMessage[];
};

export type ChatProject = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

type StoredState = {
  sessions: ChatSession[];
  activeSessionId: string;
};

const SESSIONS_KEY = "chatbi_sessions_v2";
const ACTIVE_SESSION_KEY = "chatbi_active_session_id_v2";
const UPDATE_EVENT = "chatbi-sessions-updated";
const PROJECTS_KEY = "chatbi_projects_v1";

function scopedKey(base: string): string {
  const domainId = getActiveBusinessDomainId();
  return `${base}__domain_${domainId ?? "global"}`;
}

export function getSessionStorageKeys() {
  return {
    sessionsKey: scopedKey(SESSIONS_KEY),
    projectsKey: scopedKey(PROJECTS_KEY),
    activeSessionKey: scopedKey(ACTIVE_SESSION_KEY),
    updateEvent: UPDATE_EVENT
  };
}

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix: string) {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function formatSessionTitle(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return "新对话";
  return trimmed.length > 20 ? `${trimmed.slice(0, 20)}...` : trimmed;
}

function normalizePipelineTrace(raw: unknown): PipelineTraceStep[] | undefined {
  if (!Array.isArray(raw) || !raw.length) return undefined;
  const out: PipelineTraceStep[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const id = typeof o.id === "string" ? o.id : "";
    const label = typeof o.label === "string" ? o.label : "";
    if (!id || !label) continue;
    const links = normalizeTraceEntityLinks(o.links);
    out.push({
      id,
      label,
      detail: typeof o.detail === "string" ? o.detail : undefined,
      ...(links?.length ? { links } : {})
    });
  }
  return out.length ? out : undefined;
}

function normalizeSqlDerivation(raw: unknown): SqlDerivation | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const pattern = typeof o.pattern === "string" ? o.pattern : undefined;
  const assumptions = Array.isArray(o.assumptions)
    ? o.assumptions.filter((a): a is string => typeof a === "string" && a.trim().length > 0)
    : undefined;
  const usageRaw = o.ontology_usage;
  let ontology_usage: SqlDerivationOntologyUsage[] | undefined;
  if (Array.isArray(usageRaw) && usageRaw.length) {
    ontology_usage = usageRaw
      .filter((u): u is Record<string, unknown> => !!u && typeof u === "object")
      .map((u) => ({
        ontology_label: typeof u.ontology_label === "string" ? u.ontology_label : undefined,
        ontology_kind: typeof u.ontology_kind === "string" ? u.ontology_kind : undefined,
        sql_role: typeof u.sql_role === "string" ? u.sql_role : undefined,
        sql_fragment: typeof u.sql_fragment === "string" ? u.sql_fragment : undefined,
        rationale: typeof u.rationale === "string" ? u.rationale : undefined
      }))
      .filter((u) => u.ontology_label || u.sql_fragment);
    if (!ontology_usage.length) ontology_usage = undefined;
  }
  if (!pattern && !assumptions?.length && !ontology_usage?.length) return undefined;
  return { pattern, assumptions, ontology_usage };
}

function normalizeMessage(raw: Partial<ChatMessage>): ChatMessage {
  const referenced_columns = Array.isArray(raw.referenced_columns)
    ? raw.referenced_columns.filter((c): c is string => typeof c === "string" && c.trim().length > 0)
    : undefined;
  return {
    id: raw.id || makeId("msg"),
    role: raw.role === "user" ? "user" : "assistant",
    intent: raw.intent === "sql_query" || raw.intent === "general_qa" ? raw.intent : undefined,
    question: raw.question || "",
    answer: raw.answer || "",
    sql: raw.sql || "",
    explanation: raw.explanation || "",
    referenced_columns: referenced_columns?.length ? referenced_columns : undefined,
    sql_derivation: normalizeSqlDerivation(raw.sql_derivation),
    query_result: raw.query_result || { ok: false, columns: [], rows: [], error: "历史记录无执行结果" },
    pipeline_trace: normalizePipelineTrace(raw.pipeline_trace),
    routing_trace: raw.routing_trace,
    sql_review: raw.sql_review,
    ontology_mapping: raw.ontology_mapping,
    retry_question: raw.retry_question,
    created_at: raw.created_at || nowIso()
  };
}

function normalizeSession(raw: Partial<ChatSession>): ChatSession {
  const domainId = raw.business_domain_id;
  return {
    id: raw.id || makeId("session"),
    title: raw.title || "新对话",
    created_at: raw.created_at || nowIso(),
    updated_at: raw.updated_at || nowIso(),
    pinned: !!raw.pinned,
    project_id: raw.project_id || "",
    archived_at: raw.archived_at || "",
    business_domain_id: typeof domainId === "number" && Number.isFinite(domainId) ? domainId : undefined,
    messages: (raw.messages || []).map((msg) => normalizeMessage(msg))
  };
}

function normalizeProject(raw: Partial<ChatProject>): ChatProject {
  const ts = nowIso();
  return {
    id: raw.id || makeId("project"),
    name: (raw.name || "").trim() || "未命名项目",
    created_at: raw.created_at || ts,
    updated_at: raw.updated_at || ts
  };
}

function sortSessions(list: ChatSession[]) {
  return [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

function readSessionsOnly(): ChatSession[] {
  const { sessionsKey } = getSessionStorageKeys();
  try {
    const raw = localStorage.getItem(sessionsKey);
    const parsed = raw ? (JSON.parse(raw) as Partial<ChatSession>[]) : [];
    return sortSessions(parsed.map((s) => normalizeSession(s)));
  } catch {
    return [];
  }
}

export function readSessionState(): StoredState {
  const { activeSessionKey } = getSessionStorageKeys();
  const sessions = readSessionsOnly();
  const savedActive = localStorage.getItem(activeSessionKey) || "";
  const activeSessionId = sessions.some((s) => s.id === savedActive) ? savedActive : sessions[0]?.id || "";
  return { sessions, activeSessionId };
}

function writeSessionState(next: StoredState) {
  const { sessionsKey, activeSessionKey } = getSessionStorageKeys();
  const sessions = sortSessions(next.sessions);
  try {
    localStorage.setItem(sessionsKey, JSON.stringify(sessions));
    if (next.activeSessionId) localStorage.setItem(activeSessionKey, next.activeSessionId);
    else localStorage.removeItem(activeSessionKey);
  } catch (e) {
    if (e instanceof DOMException && e.name === "QuotaExceededError") {
      // 存储已满：删除最旧的非置顶会话后重试
      const trimmed = sessions.filter((s) => !s.pinned).slice(0, sessions.length - 5);
      const kept = [...sessions.filter((s) => s.pinned), ...trimmed];
      try {
        localStorage.setItem(sessionsKey, JSON.stringify(kept));
      } catch {
        // 仍然失败则静默忽略，不阻断用户操作
      }
    }
  }
}

export function emitSessionUpdate() {
  window.dispatchEvent(new Event(UPDATE_EVENT));
}

export function isUnusedUnassignedSession(s: ChatSession): boolean {
  return !(s.project_id || "").trim() && !s.archived_at && s.messages.length === 0;
}

/** 未归类下仅保留一个空对话槽：有则激活并合并重复空会话，无则新建。 */
export function focusOrCreateUnassignedSession(): StoredState {
  const state = readSessionState();
  const empties = state.sessions
    .filter(isUnusedUnassignedSession)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  if (empties.length > 0) {
    const keep = empties[0];
    const sessions =
      empties.length > 1
        ? state.sessions.filter((s) => !isUnusedUnassignedSession(s) || s.id === keep.id)
        : state.sessions;
    writeSessionState({ sessions, activeSessionId: keep.id });
    emitSessionUpdate();
    return readSessionState();
  }
  return createSession();
}

export function createSession(initialTitle = "新对话"): StoredState {
  const state = readSessionState();
  const ts = nowIso();
  const session: ChatSession = {
    id: makeId("session"),
    title: initialTitle,
    created_at: ts,
    updated_at: ts,
    pinned: false,
    messages: []
  };
  const nextState = { sessions: [session, ...state.sessions], activeSessionId: session.id };
  writeSessionState(nextState);
  emitSessionUpdate();
  return readSessionState();
}

export function setActiveSession(id: string): StoredState {
  const state = readSessionState();
  const activeSessionId = state.sessions.some((s) => s.id === id) ? id : state.sessions[0]?.id || "";
  const nextState = { sessions: state.sessions, activeSessionId };
  writeSessionState(nextState);
  emitSessionUpdate();
  return readSessionState();
}

export function setSessionBusinessDomain(sessionId: string, businessDomainId: number | undefined): StoredState {
  const state = readSessionState();
  const sessions = state.sessions.map((s) =>
    s.id === sessionId
      ? { ...s, business_domain_id: businessDomainId, updated_at: nowIso() }
      : s
  );
  writeSessionState({ sessions, activeSessionId: state.activeSessionId });
  emitSessionUpdate();
  return readSessionState();
}

export function toggleSessionPin(id: string): StoredState {
  const state = readSessionState();
  const sessions = state.sessions.map((s) => (s.id === id ? { ...s, pinned: !s.pinned } : s));
  writeSessionState({ sessions, activeSessionId: state.activeSessionId });
  emitSessionUpdate();
  return readSessionState();
}

export function renameSession(id: string, title: string): StoredState {
  const nextTitle = title.trim() || "新对话";
  const state = readSessionState();
  const sessions = state.sessions.map((s) => (s.id === id ? { ...s, title: nextTitle, updated_at: nowIso() } : s));
  writeSessionState({ sessions, activeSessionId: state.activeSessionId });
  emitSessionUpdate();
  return readSessionState();
}

export function deleteSession(id: string): StoredState {
  const state = readSessionState();
  const sessions = state.sessions.filter((s) => s.id !== id);
  const activeSessionId =
    state.activeSessionId === id ? sessions[0]?.id || "" : sessions.some((s) => s.id === state.activeSessionId) ? state.activeSessionId : sessions[0]?.id || "";
  writeSessionState({ sessions, activeSessionId });
  emitSessionUpdate();
  return readSessionState();
}

export function upsertSession(session: ChatSession, activeSessionId?: string): StoredState {
  const state = readSessionState();
  const sessions = [session, ...state.sessions.filter((s) => s.id !== session.id)];
  const nextState = {
    sessions,
    activeSessionId: typeof activeSessionId === "string" ? activeSessionId : state.activeSessionId
  };
  writeSessionState(nextState);
  emitSessionUpdate();
  return readSessionState();
}

export function appendUserMessage(
  content: string,
  options?: { activeSessionId?: string; fromMessageId?: string }
): { state: StoredState; session: ChatSession; message: ChatMessage; baseMessages: ChatMessage[] } {
  const state = readSessionState();
  let session =
    state.sessions.find((s) => s.id === options?.activeSessionId) ||
    state.sessions.find((s) => s.id === state.activeSessionId) ||
    null;
  if (!session) {
    return appendUserMessageInNewSession(content);
  }

  const targetIdx = options?.fromMessageId ? session.messages.findIndex((m) => m.id === options.fromMessageId) : -1;
  const baseMessages = targetIdx >= 0 ? session.messages.slice(0, targetIdx) : session.messages;
  const userMessage: ChatMessage = {
    id: makeId("msg-user"),
    role: "user",
    question: content,
    created_at: nowIso()
  };
  const messages = [...baseMessages, userMessage];
  session = {
    ...session,
    title: session.messages.length ? session.title : formatSessionTitle(content),
    updated_at: nowIso(),
    messages
  };
  const nextState = upsertSession(session, session.id);
  return { state: nextState, session, message: userMessage, baseMessages };
}

function appendUserMessageInNewSession(content: string) {
  const created = focusOrCreateUnassignedSession();
  const active = created.sessions.find((s) => s.id === created.activeSessionId);
  if (!active) {
    throw new Error("创建会话失败");
  }
  return appendUserMessage(content, { activeSessionId: active.id });
}

export function appendAssistantMessage(sessionId: string, message: ChatMessage): StoredState {
  const state = readSessionState();
  const target = state.sessions.find((s) => s.id === sessionId);
  if (!target) {
    return state;
  }
  const session: ChatSession = {
    ...target,
    updated_at: nowIso(),
    messages: [...target.messages, normalizeMessage(message)]
  };
  return upsertSession(session, sessionId);
}

export function groupSessionsByTime(sessions: ChatSession[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  const yesterdayStart = todayStart - dayMs;
  const weekStart = todayStart - 7 * dayMs;
  const monthStart = todayStart - 30 * dayMs;
  const groups = {
    today: [] as ChatSession[],
    yesterday: [] as ChatSession[],
    week: [] as ChatSession[],
    month: [] as ChatSession[],
    older: [] as ChatSession[]
  };

  sessions.forEach((s) => {
    const updatedAt = new Date(s.updated_at).getTime();
    if (updatedAt >= todayStart) groups.today.push(s);
    else if (updatedAt >= yesterdayStart) groups.yesterday.push(s);
    else if (updatedAt >= weekStart) groups.week.push(s);
    else if (updatedAt >= monthStart) groups.month.push(s);
    else groups.older.push(s);
  });

  const sortByUpdated = (items: ChatSession[]) => [...items].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return [
    { key: "today", title: "今天", items: sortByUpdated(groups.today) },
    { key: "yesterday", title: "昨天", items: sortByUpdated(groups.yesterday) },
    { key: "week", title: "过去 7 天", items: sortByUpdated(groups.week) },
    { key: "month", title: "过去 30 天", items: sortByUpdated(groups.month) },
    { key: "older", title: "更早", items: sortByUpdated(groups.older) }
  ].filter((g) => g.items.length > 0);
}

export function readProjects(): ChatProject[] {
  const { projectsKey } = getSessionStorageKeys();
  try {
    const raw = localStorage.getItem(projectsKey);
    const parsed = raw ? (JSON.parse(raw) as Partial<ChatProject>[]) : [];
    return parsed.map((project) => normalizeProject(project)).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  } catch {
    return [];
  }
}

function writeProjects(projects: ChatProject[]) {
  const { projectsKey } = getSessionStorageKeys();
  localStorage.setItem(projectsKey, JSON.stringify(projects));
}

export function createProject(name: string): ChatProject[] {
  const trimmed = name.trim();
  if (!trimmed) return readProjects();
  const current = readProjects();
  const ts = nowIso();
  const next: ChatProject = {
    id: makeId("project"),
    name: trimmed,
    created_at: ts,
    updated_at: ts
  };
  const projects = [next, ...current];
  writeProjects(projects);
  emitSessionUpdate();
  return readProjects();
}

export function renameProject(id: string, name: string): ChatProject[] {
  const trimmed = name.trim();
  if (!trimmed) return readProjects();
  const projects = readProjects().map((project) =>
    project.id === id ? { ...project, name: trimmed, updated_at: nowIso() } : project
  );
  writeProjects(projects);
  emitSessionUpdate();
  return readProjects();
}

export function deleteProject(id: string): { projects: ChatProject[]; state: StoredState } {
  const projects = readProjects().filter((project) => project.id !== id);
  writeProjects(projects);
  const state = readSessionState();
  const sessions = state.sessions.map((session) => (session.project_id === id ? { ...session, project_id: "" } : session));
  writeSessionState({ sessions, activeSessionId: state.activeSessionId });
  emitSessionUpdate();
  return { projects: readProjects(), state: readSessionState() };
}

export function moveSessionToProject(sessionId: string, projectId: string): StoredState {
  const state = readSessionState();
  const sessions = state.sessions.map((session) =>
    session.id === sessionId ? { ...session, project_id: projectId, updated_at: nowIso() } : session
  );
  writeSessionState({ sessions, activeSessionId: state.activeSessionId });
  emitSessionUpdate();
  return readSessionState();
}

export function toggleSessionArchive(sessionId: string): StoredState {
  const state = readSessionState();
  const sessions = state.sessions.map((session) =>
    session.id === sessionId
      ? {
          ...session,
          archived_at: session.archived_at ? "" : nowIso(),
          updated_at: nowIso()
        }
      : session
  );
  writeSessionState({ sessions, activeSessionId: state.activeSessionId });
  emitSessionUpdate();
  return readSessionState();
}
