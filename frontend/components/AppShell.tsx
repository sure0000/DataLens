"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ConfirmDialog from "./ConfirmDialog";
import {
  createProject,
  createSession,
  deleteProject,
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

type NavIcon =
  | "domain"
  | "database"
  | "book"
  | "spark"
  | "plus"
  | "search"
  | "chevronLeft"
  | "chevronRight"
  | "brand"
  | "more";

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

function Icon({ name, className = "h-4 w-4" }: { name: NavIcon; className?: string }) {
  const common = { stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (name === "plus") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 5v14M5 12h14" {...common} />
      </svg>
    );
  }
  if (name === "search") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="11" cy="11" r="6" {...common} />
        <path d="M16 16l4 4" {...common} />
      </svg>
    );
  }
  if (name === "chevronLeft") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M15 6l-6 6 6 6" {...common} />
      </svg>
    );
  }
  if (name === "chevronRight") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M9 6l6 6-6 6" {...common} />
      </svg>
    );
  }
  if (name === "brand") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="8" {...common} />
        <circle cx="12" cy="12" r="3.2" {...common} />
      </svg>
    );
  }
  if (name === "more") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="6" cy="12" r="1.3" fill="currentColor" />
        <circle cx="12" cy="12" r="1.3" fill="currentColor" />
        <circle cx="18" cy="12" r="1.3" fill="currentColor" />
      </svg>
    );
  }
  if (name === "domain") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 5h7v6H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 13h7v6H4z" {...common} />
      </svg>
    );
  }
  if (name === "database") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <ellipse cx="12" cy="6" rx="7" ry="3" {...common} />
        <path d="M5 6v6c0 1.66 3.13 3 7 3s7-1.34 7-3V6M5 12v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6" {...common} />
      </svg>
    );
  }
  if (name === "book") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M6 4h5a2 2 0 012 2v14a2 2 0 00-2-2H6V4zM13 4h5v14h-5a2 2 0 00-2 2V6a2 2 0 012-2z" {...common} />
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3l2.1 4.56L19 10l-4.9 2.44L12 17l-2.1-4.56L5 10l4.9-2.44L12 3z" {...common} />
    </svg>
  );
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
    let state = createSession();
    if (activeProjectId !== "all" && activeProjectId !== "__unassigned__" && state.activeSessionId) {
      state = moveSessionToProject(state.activeSessionId, activeProjectId);
    }
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
    setSearchMode(false);
    setSessionSearch("");
    if (!isCopilot) router.push("/copilot");
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
    if (!isCopilot) router.push("/copilot");
    setSearchMode(true);
    setTimeout(() => sessionSearchInputRef.current?.focus(), 0);
  }

  function selectCopilotSession(id: string) {
    const state = setActiveSession(id);
    setSessions(state.sessions);
    setActiveSessionId(state.activeSessionId);
    router.push(`/copilot?session=${encodeURIComponent(id)}`);
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
      if (evt.key === "Escape") {
        setMenuProjectId("");
        if (searchMode) cancelSearchMode();
      }
    };
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, [isCopilot, searchMode]);

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
            className="app-control-button border border-[var(--app-card-border)] bg-white"
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
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isActive(pathname, "/datasources") ? "border-[#c7d2fe] bg-[#eef2ff] text-[#111827]" : ""}`}
              title="数据源"
              aria-label="数据源"
            >
              <Icon name="database" />
            </Link>
            <Link
              href="/"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${pathname === "/" ? "border-[#c7d2fe] bg-[#eef2ff] text-[#111827]" : ""}`}
              title="业务域"
              aria-label="业务域"
            >
              <Icon name="domain" />
            </Link>
            <Link
              href="/knowledge-bases"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isActive(pathname, "/knowledge-bases") ? "border-[#c7d2fe] bg-[#eef2ff] text-[#111827]" : ""}`}
              title="知识库"
              aria-label="知识库"
            >
              <Icon name="book" />
            </Link>
            <Link
              href="/copilot"
              className={`app-control-button flex h-9 w-9 shrink-0 items-center justify-center p-0 no-underline ${isCopilot ? "border-[#c7d2fe] bg-[#eef2ff] text-[#111827]" : ""}`}
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
                <span>知识库</span>
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
                        <button className="app-control-button app-toolbar-action" onClick={createCopilotProject}>
                          确定
                        </button>
                      </div>
                    )}
                    <div className="mt-1 space-y-1">
                      <button
                        className={`app-sidebar-chip w-full rounded-lg px-2 py-1.5 text-left text-xs ${
                          activeProjectId === "all" ? "is-active" : ""
                        }`}
                        onClick={() => openProjectView("all")}
                      >
                        全部会话 ({sessions.length})
                      </button>
                      <button
                        className={`app-sidebar-chip w-full rounded-lg px-2 py-1.5 text-left text-xs ${
                          activeProjectId === "__unassigned__" ? "is-active" : ""
                        }`}
                        onClick={() => openProjectView("__unassigned__")}
                      >
                        未归类 ({sessions.filter((s) => !s.project_id).length})
                      </button>
                      {projects.map((project) => {
                        const isEditing = editingProjectId === project.id;
                        const count = sessions.filter((s) => s.project_id === project.id).length;
                        return (
                          <div key={project.id} className="group relative rounded">
                            {isEditing ? (
                              <input
                                className="app-input !rounded-md !px-2 !py-1 text-xs"
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
                              <button
                                className={`app-sidebar-chip w-full rounded-lg px-2 py-1.5 text-left text-xs ${
                                  activeProjectId === project.id ? "is-active" : ""
                                }`}
                                onClick={() => openProjectView(project.id)}
                              >
                                <span className="line-clamp-1">
                                  {project.name} ({count})
                                </span>
                              </button>
                            )}
                            {!isEditing && (
                              <button
                                className={`app-control-button absolute right-1 top-0 ${menuProjectId === project.id ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                                data-menu-root="1"
                                onClick={() => setMenuProjectId((prev) => (prev === project.id ? "" : project.id))}
                              >
                                <Icon name="more" className="h-4 w-4" />
                              </button>
                            )}
                            {menuProjectId === project.id && (
                              <div
                                className="app-dropdown-surface absolute right-2 top-7 z-20 min-w-[120px] rounded-lg p-1"
                                data-menu-root="1"
                              >
                                <button
                                  className="app-control-button w-full justify-start"
                                  onClick={() => {
                                    createSessionInProject(project.id);
                                    setMenuProjectId("");
                                  }}
                                >
                                  在此项目中新聊天
                                </button>
                                <button
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
            <div className="app-toolbar rounded-lg border border-[#e5e7eb] bg-white px-3 py-2">
              <span className="app-text-secondary">
                <Icon name="search" className="h-4 w-4" />
              </span>
              <input
                ref={sessionSearchInputRef}
                className="app-text-primary app-toolbar-input bg-transparent text-sm outline-none placeholder:text-[#9ca3af]"
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
                      className="app-list-item w-full rounded-lg border border-transparent px-2 py-2 text-left transition hover:border-[var(--app-card-border)] hover:bg-[#f9fafb]"
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
