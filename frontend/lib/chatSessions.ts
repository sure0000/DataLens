export type QueryResult = {
  ok: boolean;
  columns: string[];
  rows: Record<string, unknown>[];
  error?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  intent?: "sql_query" | "general_qa";
  question?: string;
  answer?: string;
  sql?: string;
  explanation?: string;
  query_result?: QueryResult;
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

export function getSessionStorageKeys() {
  return {
    sessionsKey: SESSIONS_KEY,
    projectsKey: PROJECTS_KEY,
    activeSessionKey: ACTIVE_SESSION_KEY,
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

function normalizeMessage(raw: Partial<ChatMessage>): ChatMessage {
  return {
    id: raw.id || makeId("msg"),
    role: raw.role === "user" ? "user" : "assistant",
    intent: raw.intent === "sql_query" || raw.intent === "general_qa" ? raw.intent : undefined,
    question: raw.question || "",
    answer: raw.answer || "",
    sql: raw.sql || "",
    explanation: raw.explanation || "",
    query_result: raw.query_result || { ok: false, columns: [], rows: [], error: "历史记录无执行结果" },
    created_at: raw.created_at || nowIso()
  };
}

function normalizeSession(raw: Partial<ChatSession>): ChatSession {
  return {
    id: raw.id || makeId("session"),
    title: raw.title || "新对话",
    created_at: raw.created_at || nowIso(),
    updated_at: raw.updated_at || nowIso(),
    pinned: !!raw.pinned,
    project_id: raw.project_id || "",
    archived_at: raw.archived_at || "",
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
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<ChatSession>[]) : [];
    return sortSessions(parsed.map((s) => normalizeSession(s)));
  } catch {
    return [];
  }
}

export function readSessionState(): StoredState {
  const sessions = readSessionsOnly();
  const savedActive = localStorage.getItem(ACTIVE_SESSION_KEY) || "";
  const activeSessionId = sessions.some((s) => s.id === savedActive) ? savedActive : sessions[0]?.id || "";
  return { sessions, activeSessionId };
}

function writeSessionState(next: StoredState) {
  const sessions = sortSessions(next.sessions);
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  if (next.activeSessionId) localStorage.setItem(ACTIVE_SESSION_KEY, next.activeSessionId);
  else localStorage.removeItem(ACTIVE_SESSION_KEY);
}

export function emitSessionUpdate() {
  window.dispatchEvent(new Event(UPDATE_EVENT));
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
  const created = createSession();
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
  try {
    const raw = localStorage.getItem(PROJECTS_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<ChatProject>[]) : [];
    return parsed.map((project) => normalizeProject(project)).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  } catch {
    return [];
  }
}

function writeProjects(projects: ChatProject[]) {
  localStorage.setItem(PROJECTS_KEY, JSON.stringify(projects));
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
