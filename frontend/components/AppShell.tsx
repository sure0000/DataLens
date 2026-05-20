"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon, type NavIcon } from "./AppIcons";
import ConfirmDialog from "./ConfirmDialog";
import { useEscapeKey } from "../hooks/useEscapeKey";
import {
  createProject,
  createSession,
  deleteProject,
  deleteSession,
  focusOrCreateUnassignedSession,
  getSessionStorageKeys,
  moveSessionToProject,
  readProjects,
  readSessionState,
  renameProject,
  setActiveSession,
  type ChatProject,
  type ChatSession
} from "../lib/chatSessions";

const SIDEBAR_COLLAPSE_KEY = "datalens_sidebar_collapsed_v1";
/** 侧栏每个项目分组下默认展示的会话条数 */
const SIDEBAR_SESSION_PREVIEW_LIMIT = 5;
function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [projects, setProjects] = useState<ChatProject[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [activeProjectId, setActiveProjectId] = useState("all");
  const [sessionSearch, setSessionSearch] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [projectExpanded, setProjectExpanded] = useState(true);
  const [menuProjectId, setMenuProjectId] = useState("");
  const [editingProjectId, setEditingProjectId] = useState("");
  const [editingProjectName, setEditingProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const sessionSearchInputRef = useRef<HTMLInputElement | null>(null);
  const newProjectInputRef = useRef<HTMLInputElement | null>(null);
  const [pendingDeleteProjectId, setPendingDeleteProjectId] = useState<string | null>(null);
  const [sessionMenuId, setSessionMenuId] = useState("");
  const [pendingDeleteSessionId, setPendingDeleteSessionId] = useState<string | null>(null);
  /** false / undefined = 展开；true = 折叠子列表 */
  const [sidebarGroupCollapsed, setSidebarGroupCollapsed] = useState<Record<string, boolean>>({});
  /** true = 显示该分组下全部会话；false/undefined = 仅最近 5 条 */
  const [sidebarGroupSessionsFull, setSidebarGroupSessionsFull] = useState<Record<string, boolean>>({});
  const isCopilot = pathname.startsWith("/copilot");
  const { updateEvent } = getSessionStorageKeys();

  function loadCopilotSessions() {
    const state = readSessionState();
    const projectList = readProjects();
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
    setProjects(projectList);
  }

  useEffect(() => {
    const stored = localStorage.getItem(SIDEBAR_COLLAPSE_KEY);
    setSidebarCollapsed(stored === "1");
  }, []);

  useEffect(() => {
    loadCopilotSessions();
    const onUpdate = () => loadCopilotSessions();
    window.addEventListener(updateEvent, onUpdate);
    window.addEventListener("storage", onUpdate);
    return () => {
      window.removeEventListener(updateEvent, onUpdate);
      window.removeEventListener("storage", onUpdate);
    };
  }, [updateEvent]);

  function toggleSidebar() {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    localStorage.setItem(SIDEBAR_COLLAPSE_KEY, next ? "1" : "0");
  }

  function createCopilotSession() {
    const isNamedProject = activeProjectId !== "all" && activeProjectId !== "__unassigned__";
    let state = isNamedProject ? createSession() : focusOrCreateUnassignedSession();
    if (isNamedProject && state.activeSessionId) {
      state = moveSessionToProject(state.activeSessionId, activeProjectId);
    }
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
    setActiveProjectId(isNamedProject ? activeProjectId : "__unassigned__");
    setSearchMode(false);
    setSessionSearch("");
    const sid = state.activeSessionId;
    if (!sid) return;
    if (!isCopilot) {
      if (isNamedProject) {
        router.push("/copilot");
      } else {
        router.push(`/copilot?project=__unassigned__&session=${encodeURIComponent(sid)}`);
      }
      return;
    }
    if (!isNamedProject) {
      router.push(`/copilot?project=__unassigned__&session=${encodeURIComponent(sid)}`);
    }
  }

  function openProjectView(projectId: string) {
    setActiveProjectId(projectId);
    const url = projectId === "all" ? "/copilot" : `/copilot?project=${encodeURIComponent(projectId)}`;
    if (typeof window !== "undefined" && `${window.location.pathname}${window.location.search}` === url) return;
    router.push(url);
  }

  function createSessionInProject(projectId: string) {
    openProjectView(projectId || "__unassigned__");
  }

  function focusSessionSearch() {
    setSearchMode(true);
    setTimeout(() => sessionSearchInputRef.current?.focus(), 0);
  }

  function selectCopilotSession(id: string) {
    const state = setActiveSession(id);
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
    router.replace(`/copilot?session=${encodeURIComponent(id)}`);
  }

  function createCopilotProject() {
    const list = createProject(newProjectName);
    setProjects(list);
    const latest = list[0];
    if (latest) setActiveProjectId(latest.id);
    setNewProjectName("");
    setCreatingProject(false);
  }

  function submitRenameProject() {
    if (!editingProjectId) return;
    const list = renameProject(editingProjectId, editingProjectName);
    setProjects(list);
    setEditingProjectId("");
    setEditingProjectName("");
  }

  function removeCopilotProject(id: string) {
    const next = deleteProject(id);
    setProjects(next.projects);
    setSessions(next.state.sessions);
    setActiveSessionId(next.state.activeSessionId);
    if (activeProjectId === id) setActiveProjectId("all");
  }

  function removeCopilotSession(id: string) {
    const meta = sessions.find((s) => s.id === id);
    const pid = (meta?.project_id || "").trim();
    const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
    const sessionInUrl = params?.get("session") || "";
    const next = deleteSession(id);
    setSessions(next.sessions);
    setActiveSessionId(next.activeSessionId);
    setSessionMenuId("");
    if (isCopilot && sessionInUrl === id) {
      if (next.activeSessionId) {
        router.push(`/copilot?session=${encodeURIComponent(next.activeSessionId)}`);
      } else {
        router.push(pid ? `/copilot?project=${encodeURIComponent(pid)}` : "/copilot?project=__unassigned__");
      }
    }
  }


  function cancelSearchMode() {
    setSearchMode(false);
    setSessionSearch("");
  }

  function formatSessionMeta(updatedAt: string) {
    const date = new Date(updatedAt);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
  }

  function getSessionPreview(session: ChatSession) {
    const latestUser = [...session.messages].reverse().find((m) => m.role === "user" && m.question?.trim());
    if (latestUser?.question?.trim()) return latestUser.question.trim();
    const latestAssistant = [...session.messages].reverse().find((m) => m.role === "assistant" && m.answer?.trim());
    return latestAssistant?.answer?.trim() || "暂无内容";
  }

  useEffect(() => {
    const onClickOutside = (evt: MouseEvent) => {
      if (!(evt.target instanceof HTMLElement)) return;
      if (evt.target.closest("[data-menu-root='1']")) return;
      setMenuProjectId("");
      setSessionMenuId("");
    };
    window.addEventListener("mousedown", onClickOutside);
    return () => window.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    const onKeydown = (evt: KeyboardEvent) => {
      const isMetaK = (evt.metaKey || evt.ctrlKey) && evt.key.toLowerCase() === "k";
      if (isMetaK && isCopilot) {
        evt.preventDefault();
        focusSessionSearch();
      }
    };
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, [isCopilot]);

  useEscapeKey(() => {
    setMenuProjectId("");
    setSessionMenuId("");
    if (searchMode) cancelSearchMode();
  });

  useEffect(() => {
    if (!creatingProject) return;
    setTimeout(() => newProjectInputRef.current?.focus(), 0);
  }, [creatingProject]);

  useEffect(() => {
    if (pathname !== "/copilot") return;
    const params = new URLSearchParams(window.location.search);
    const projectId = params.get("project");
    if (projectId) {
      setActiveProjectId(projectId);
      return;
    }
    const sessionId = params.get("session");
    if (!sessionId) {
      setActiveProjectId("all");
      return;
    }
    const session = sessions.find((item) => item.id === sessionId);
    if (!session) return;
    setActiveProjectId(session.project_id || "__unassigned__");
  }, [pathname, sessions]);

  const unassignedSessionsSidebar = useMemo(
    () =>
      [...sessions]
        .filter((s) => !(s.project_id || "").trim() && !s.archived_at)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    [sessions]
  );

  function isSidebarGroupOpen(treeKey: string) {
    return sidebarGroupCollapsed[treeKey] !== true;
  }

  function toggleSidebarGroup(treeKey: string) {
    setSidebarGroupCollapsed((prev) => {
      const isOpen = prev[treeKey] !== true;
      if (isOpen) {
        setSidebarGroupSessionsFull((s) => ({ ...s, [treeKey]: false }));
        return { ...prev, [treeKey]: true };
      }
      return { ...prev, [treeKey]: false };
    });
  }

  function isSidebarGroupSessionsFull(treeKey: string) {
    return !!sidebarGroupSessionsFull[treeKey];
  }

  function toggleSidebarGroupSessionsFull(treeKey: string) {
    setSidebarGroupSessionsFull((prev) => ({ ...prev, [treeKey]: !prev[treeKey] }));
  }

  function renderSidebarSessionBlock(list: ChatSession[], treeKey: string) {
    if (!list.length || !isSidebarGroupOpen(treeKey)) return null;
    const full = isSidebarGroupSessionsFull(treeKey);
    const visible = full ? list : list.slice(0, SIDEBAR_SESSION_PREVIEW_LIMIT);
    const hasMore = list.length > SIDEBAR_SESSION_PREVIEW_LIMIT;
    return (
      <>
        <ul className="app-project-sidebar-children mt-0.5 space-y-0.5">
          {visible.map((s) => {
            const isSessionActive = activeSessionId === s.id;
            return (
              <li key={s.id} className="group/session-item relative">
                <div
                  className={`flex w-full items-center gap-0.5 rounded-[10px] py-0.5 pl-1 pr-0.5 transition-colors ${
                    isSessionActive ? "bg-[var(--app-active-bg)]" : "hover:bg-[var(--app-surface-hover)]"
                  }`}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate py-2 pl-0.5 text-left text-[13px] leading-snug text-[var(--app-text-primary)]"
                    onClick={() => selectCopilotSession(s.id)}
                  >
                    {s.title}
                  </button>
                  <button
                    type="button"
                    className={`app-control-button h-7 w-7 shrink-0 p-0 ${
                      sessionMenuId === s.id ? "opacity-100" : "opacity-0 group-hover/session-item:opacity-100"
                    }`}
                    data-menu-root="1"
                    aria-label="会话操作"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setSessionMenuId((prev) => (prev === s.id ? "" : s.id));
                    }}
                  >
                    <Icon name="more" className="h-4 w-4" />
                  </button>
                </div>
                {sessionMenuId === s.id && (
                  <div
                    className="app-dropdown-surface absolute left-0 right-0 top-full z-[25] mt-0.5 rounded-lg p-1 shadow-md"
                    data-menu-root="1"
                  >
                    <button
                      type="button"
                      className="app-control-button w-full justify-start text-[var(--app-danger)] hover:text-[var(--app-danger-hover)]"
                      onClick={() => {
                        setPendingDeleteSessionId(s.id);
                        setSessionMenuId("");
                      }}
                    >
                      删除对话
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {hasMore ? (
          <div className="app-project-sidebar-children mt-0.5 pl-1">
            <button
              type="button"
              className="text-xs text-[var(--app-text-secondary)] underline-offset-2 hover:text-[var(--app-text-primary)] hover:underline"
              onClick={() => toggleSidebarGroupSessionsFull(treeKey)}
            >
              {full ? `仅显示最近 ${SIDEBAR_SESSION_PREVIEW_LIMIT} 条` : `展开全部（${list.length}）`}
            </button>
          </div>
        ) : null}
      </>
    );
  }

  const normalizedSearch = sessionSearch.trim().toLowerCase();
  const searchResults = useMemo(() => {
    if (!normalizedSearch) return [];
    return sessions.filter((s) => {
      const titleHit = s.title.toLowerCase().includes(normalizedSearch);
      if (titleHit) return true;
      return getSessionPreview(s).toLowerCase().includes(normalizedSearch);
    });
  }, [sessions, normalizedSearch]);

  return (
    <div className="app-shell">
      {/* Mobile overlay */}
      <div
        className={`app-sidebar-overlay ${mobileOpen ? "is-open" : ""}`}
        onClick={() => setMobileOpen(false)}
        aria-hidden="true"
      />
      <aside
        aria-label="应用主导航"
        className={`app-sidebar flex shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${
          sidebarCollapsed ? "w-[68px] md:w-[76px]" : "w-[272px] lg:w-[288px]"
        } ${mobileOpen ? "is-mobile-open" : ""}`}
      >
        <div className="mb-2 flex items-center justify-between gap-1">
          {!sidebarCollapsed && (
            <Link
              href="/"
              className="app-sidebar-brand app-text-primary inline-flex items-center gap-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400/70"
            >
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-md text-[11px]" aria-hidden="true">
                <Icon name="brand" className="h-4 w-4" />
              </span>
              <span>DataLens</span>
            </Link>
          )}
          <button
            className="app-control-button border border-[var(--app-card-border)] bg-[var(--app-elevated-bg)]"
            onClick={toggleSidebar}
            title={sidebarCollapsed ? "展开侧边栏" : "折叠侧边栏"}
            aria-label={sidebarCollapsed ? "展开侧边栏" : "折叠侧边栏"}
          >
            <Icon name={sidebarCollapsed ? "chevronRight" : "chevronLeft"} className="h-4 w-4" />
          </button>
        </div>

        {sidebarCollapsed && (
          <div className="mb-3 flex flex-col items-center gap-1.5 pb-3">
            <button
              type="button"
              className="app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 text-lg leading-none"
              title="新聊天"
              aria-label="新聊天"
              onClick={createCopilotSession}
            >
              <Icon name="plus" className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0"
              title="搜索聊天"
              aria-label="搜索聊天"
              onClick={focusSessionSearch}
            >
              <Icon name="search" className="h-4 w-4" />
            </button>
            <Link
              href="/datasources"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isActive(pathname, "/datasources") ? "border-app-activeBorder bg-app-activeBg text-app-primary" : ""}`}
              title="数据源"
              aria-label="数据源"
            >
              <Icon name="database" />
            </Link>
            <Link
              href="/"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${pathname === "/" ? "border-app-activeBorder bg-app-activeBg text-app-primary" : ""}`}
              title="业务域"
              aria-label="业务域"
            >
              <Icon name="domain" />
            </Link>
            <Link
              href="/knowledge-bases"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isActive(pathname, "/knowledge-bases") ? "border-app-activeBorder bg-app-activeBg text-app-primary" : ""}`}
              title="语义知识库"
              aria-label="语义知识库"
            >
              <Icon name="book" />
            </Link>
            <Link
              href="/settings"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isActive(pathname, "/settings") ? "border-app-activeBorder bg-app-activeBg text-app-primary" : ""}`}
              title="偏好设置"
              aria-label="偏好设置"
            >
              <Icon name="settings" />
            </Link>
            <Link
              href="/copilot"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isCopilot ? "border-app-activeBorder bg-app-activeBg text-app-primary" : ""}`}
              title="助手"
              aria-label="打开 DataLens 助手"
            >
              <Icon name="spark" />
            </Link>
          </div>
        )}

        <section className="mt-4 pt-4">
          {!sidebarCollapsed && (
            <div className="space-y-1 pb-3">
              <button className="app-nav-item w-full rounded-lg" onClick={createCopilotSession}>
                <span className="app-text-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md">
                  <Icon name="plus" className="h-4 w-4" />
                </span>
                <span>新聊天</span>
              </button>
              <button className="app-nav-item w-full rounded-lg" onClick={focusSessionSearch}>
                <span className="app-text-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md">
                  <Icon name="search" className="h-4 w-4" />
                </span>
                <span>搜索聊天</span>
              </button>
              <Link href="/datasources" className={`app-nav-item rounded-lg ${isActive(pathname, "/datasources") ? "is-active" : ""}`}>
                <span className="app-text-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs">
                  <Icon name="database" />
                </span>
                <span>数据源</span>
              </Link>
              <Link href="/" className={`app-nav-item rounded-lg ${isActive(pathname, "/") ? "is-active" : ""}`}>
                <span className="app-text-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs">
                  <Icon name="domain" />
                </span>
                <span>业务域</span>
              </Link>
            <Link
              href="/knowledge-bases"
              className={`app-nav-item rounded-lg ${isActive(pathname, "/knowledge-bases") ? "is-active" : ""}`}
            >
              <span className="app-text-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs">
                <Icon name="book" />
              </span>
              <span>语义知识库</span>
            </Link>
              <Link href="/settings" className={`app-nav-item rounded-lg ${isActive(pathname, "/settings") ? "is-active" : ""}`}>
                <span className="app-text-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs">
                  <Icon name="settings" />
                </span>
                <span>偏好设置</span>
              </Link>
            </div>
          )}
          {sidebarCollapsed ? (
            <div className="h-2" />
          ) : (
            <div className="mt-3 space-y-2">
                {projectExpanded && (
                  <div className="px-1">
                    <div className="flex items-center justify-between py-1">
                      <p className="app-text-muted text-xs">项目</p>
                      <button className="app-control-button" onClick={() => setCreatingProject(true)}>
                        新项目
                      </button>
                    </div>
                    {creatingProject && (
                      <div className="app-toolbar mt-2">
                        <input
                          ref={newProjectInputRef}
                          className="app-input app-toolbar-input !rounded-md !px-2 !py-1 text-xs"
                          placeholder="输入项目名"
                          value={newProjectName}
                          onChange={(e) => setNewProjectName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") createCopilotProject();
                            if (e.key === "Escape") {
                              setCreatingProject(false);
                              setNewProjectName("");
                            }
                          }}
                        />
                        <button
                          type="button"
                          className="app-control-button shrink-0"
                          onClick={() => {
                            setCreatingProject(false);
                            setNewProjectName("");
                          }}
                        >
                          取消
                        </button>
                        <button type="button" className="app-control-button app-toolbar-action shrink-0" onClick={createCopilotProject}>
                          确定
                        </button>
                      </div>
                    )}
                    <div className="app-project-sidebar-tree mt-1 space-y-3">
                      <div className="app-project-sidebar-group">
                        <div
                          className={`app-project-sidebar-folder group/unassigned flex items-center gap-0.5 rounded-[10px] pr-1 transition-colors ${
                            activeProjectId === "__unassigned__" ? "bg-[var(--app-active-bg)]" : "hover:bg-[var(--app-surface-hover)]"
                          }`}
                        >
                          <button
                            type="button"
                            className="app-control-button h-7 w-7 shrink-0 p-0"
                            aria-expanded={isSidebarGroupOpen("__unassigned__")}
                            aria-label="展开或折叠未归类下的会话"
                            onClick={() => toggleSidebarGroup("__unassigned__")}
                          >
                            <Icon
                              name={isSidebarGroupOpen("__unassigned__") ? "chevronDown" : "chevronRight"}
                              className="h-4 w-4"
                            />
                          </button>
                          <button
                            type="button"
                            className="flex min-w-0 flex-1 items-center gap-2 px-0.5 py-2 text-left text-[13px] font-medium text-[var(--app-text-primary)]"
                            onClick={() => openProjectView("__unassigned__")}
                          >
                            <Icon name="folder" className="h-[18px] w-[18px] shrink-0 text-[var(--app-text-secondary)]" />
                            <span className="min-w-0 flex-1 truncate">
                              未归类
                              <span className="font-normal text-[var(--app-text-placeholder)]"> ({unassignedSessionsSidebar.length})</span>
                            </span>
                          </button>
                        </div>
                        {renderSidebarSessionBlock(unassignedSessionsSidebar, "__unassigned__")}
                      </div>

                      {projects.map((project) => {
                        const isEditing = editingProjectId === project.id;
                        const projSessions = sessions
                          .filter((s) => s.project_id === project.id && !s.archived_at)
                          .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
                        const count = projSessions.length;
                        const treeKey = project.id;
                        return (
                          <div key={project.id} className="app-project-sidebar-group">
                            {isEditing ? (
                              <input
                                className="app-input w-full rounded-[10px] px-2 py-2 text-[13px]"
                                value={editingProjectName}
                                autoFocus
                                onChange={(e) => setEditingProjectName(e.target.value)}
                                onBlur={submitRenameProject}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") submitRenameProject();
                                  if (e.key === "Escape") {
                                    setEditingProjectId("");
                                    setEditingProjectName("");
                                  }
                                }}
                              />
                            ) : (
                              <div
                                className={`app-project-sidebar-folder group/proj relative flex items-center gap-0.5 rounded-[10px] pr-1 transition-colors ${
                                  activeProjectId === project.id ? "bg-[var(--app-active-bg)]" : "hover:bg-[var(--app-surface-hover)]"
                                }`}
                              >
                                <button
                                  type="button"
                                  className="app-control-button h-7 w-7 shrink-0 p-0"
                                  aria-expanded={isSidebarGroupOpen(treeKey)}
                                  aria-label={`展开或折叠「${project.name}」下的会话`}
                                  onClick={() => toggleSidebarGroup(treeKey)}
                                >
                                  <Icon
                                    name={isSidebarGroupOpen(treeKey) ? "chevronDown" : "chevronRight"}
                                    className="h-4 w-4"
                                  />
                                </button>
                                <button
                                  type="button"
                                  className="flex min-w-0 flex-1 items-center gap-2 px-0.5 py-2 text-left text-[13px] font-medium text-[var(--app-text-primary)]"
                                  onClick={() => openProjectView(project.id)}
                                >
                                  <Icon name="folder" className="h-[18px] w-[18px] shrink-0 text-[var(--app-text-secondary)]" />
                                  <span className="min-w-0 flex-1 truncate">
                                    {project.name}
                                    <span className="font-normal text-[var(--app-text-placeholder)]"> ({count})</span>
                                  </span>
                                </button>
                                <button
                                  type="button"
                                  className={`app-control-button h-7 w-7 shrink-0 p-0 ${
                                    menuProjectId === project.id ? "opacity-100" : "opacity-0 group-hover/proj:opacity-100"
                                  }`}
                                  data-menu-root="1"
                                  aria-label="项目菜单"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setMenuProjectId((prev) => (prev === project.id ? "" : project.id));
                                  }}
                                >
                                  <Icon name="more" className="h-4 w-4" />
                                </button>
                                {menuProjectId === project.id && (
                                  <div
                                    className="app-dropdown-surface absolute right-0 top-[calc(100%-2px)] z-20 min-w-[140px] rounded-lg p-1"
                                    data-menu-root="1"
                                  >
                                    <button
                                      type="button"
                                      className="app-control-button w-full justify-start"
                                      onClick={() => {
                                        createSessionInProject(project.id);
                                        setMenuProjectId("");
                                      }}
                                    >
                                      在此项目中新聊天
                                    </button>
                                    <button
                                      type="button"
                                      className="app-control-button w-full justify-start"
                                      onClick={() => {
                                        setEditingProjectId(project.id);
                                        setEditingProjectName(project.name);
                                        setMenuProjectId("");
                                      }}
                                    >
                                      重命名
                                    </button>
                                    <button
                                      type="button"
                                      className="app-control-button w-full justify-start text-[var(--app-danger)] hover:text-[var(--app-danger-hover)]"
                                      onClick={() => {
                                        setPendingDeleteProjectId(project.id);
                                        setMenuProjectId("");
                                      }}
                                    >
                                      删除项目
                                    </button>
                                  </div>
                                )}
                              </div>
                            )}
                            {!isEditing ? renderSidebarSessionBlock(projSessions, treeKey) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {!projectExpanded && (
                  <button className="app-control-button w-full justify-start" onClick={() => setProjectExpanded(true)}>
                    展开项目
                  </button>
                )}
                <div className="mt-2" />
              </div>
            )}
        </section>
      </aside>

      <main id="main-content" className="flex min-h-screen min-w-0 flex-1 flex-col bg-[var(--app-main-bg)]" tabIndex={-1}>
        <button
          className="app-control-button fixed left-3 top-3 z-20 md:hidden"
          onClick={() => setMobileOpen(true)}
          aria-label="打开导航菜单"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>
        {children}
      </main>

      <ConfirmDialog
        open={pendingDeleteProjectId !== null}
        title="删除项目"
        description="删除项目后，会话会回到未归类。确定删除？"
        danger
        confirmText="删除"
        onCancel={() => setPendingDeleteProjectId(null)}
        onConfirm={() => {
          if (pendingDeleteProjectId) removeCopilotProject(pendingDeleteProjectId);
          setPendingDeleteProjectId(null);
        }}
      />

      <ConfirmDialog
        open={pendingDeleteSessionId !== null}
        title="删除对话"
        description="删除后无法恢复，确定删除该对话？"
        danger
        confirmText="删除"
        onCancel={() => setPendingDeleteSessionId(null)}
        onConfirm={() => {
          if (pendingDeleteSessionId) removeCopilotSession(pendingDeleteSessionId);
          setPendingDeleteSessionId(null);
        }}
      />

      {searchMode && (
        <div
          className="app-search-overlay fixed inset-0 z-40 p-4"
          onClick={cancelSearchMode}
          role="presentation"
        >
          <div
            className="app-modal-surface mx-auto mt-[8vh] w-full max-w-2xl rounded-2xl p-3"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="session-search-title"
          >
            <h2 id="session-search-title" className="sr-only">
              搜索聊天会话
            </h2>
            <div className="app-toolbar rounded-lg border border-app-border bg-app-card px-3 py-2">
              <span className="app-text-secondary">
                <Icon name="search" className="h-4 w-4" />
              </span>
              <input
                ref={sessionSearchInputRef}
                className="app-text-primary app-toolbar-input bg-transparent text-sm outline-none placeholder:text-app-muted"
                placeholder="搜索聊天（标题或内容）"
                value={sessionSearch}
                onChange={(e) => setSessionSearch(e.target.value)}
              />
              <button className="app-control-button app-toolbar-action" onClick={cancelSearchMode}>
                关闭
              </button>
            </div>
            <div className="mt-2 max-h-[56vh] overflow-auto">
              {!normalizedSearch && <p className="app-text-secondary px-2 py-8 text-center text-sm">输入关键词开始搜索</p>}
              {!!normalizedSearch && !searchResults.length && <p className="app-text-secondary px-2 py-8 text-center text-sm">没有找到结果</p>}
              {!!searchResults.length && (
                <div className="space-y-1">
                  {searchResults.map((session) => (
                    <button
                      key={`search-${session.id}`}
                      className="app-list-item w-full rounded-lg border border-transparent px-2 py-2 text-left transition hover:border-app-border hover:bg-app-hover"
                      onClick={() => {
                        setSearchMode(false);
                        setSessionSearch("");
                        setActiveProjectId(session.project_id || "__unassigned__");
                        selectCopilotSession(session.id);
                      }}
                    >
                      <div className="app-list-item-main flex items-center justify-between gap-2">
                        <p className="app-text-primary line-clamp-1 text-sm">{session.title}</p>
                        <span className="app-text-secondary shrink-0 text-[11px]">{formatSessionMeta(session.updated_at)}</span>
                      </div>
                      <p className="app-text-secondary mt-1 line-clamp-2 text-xs">{getSessionPreview(session)}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
