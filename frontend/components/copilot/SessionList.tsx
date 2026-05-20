"use client";

import type { ChatSession } from "../../lib/chatSessions";

interface SessionListProps {
  sessions: ChatSession[];
  getPreview: (s: ChatSession) => string;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function SessionList({ sessions, getPreview, onOpen, onDelete }: SessionListProps) {
  return (
    <div className="divide-y divide-[var(--app-card-border)] rounded-xl bg-[var(--app-card-bg)]">
      {sessions.map((session) => (
        <div
          key={session.id}
          className="flex w-full items-stretch gap-1 px-2 py-2 transition hover:bg-app-hover sm:px-3 sm:py-3"
        >
          <button
            type="button"
            className="min-w-0 flex-1 px-1 py-1 text-left sm:px-2"
            onClick={() => onOpen(session.id)}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="line-clamp-1 text-[18px] font-semibold text-app-primary sm:text-[20px]">{session.title}</p>
                <p className="mt-0.5 line-clamp-1 text-[13px] text-app-secondary sm:text-[14px]">{getPreview(session)}</p>
              </div>
              <span className="shrink-0 pt-1 text-[13px] text-app-muted sm:text-[14px]">
                {new Date(session.updated_at).toLocaleDateString("zh-CN")}
              </span>
            </div>
          </button>
          <button
            type="button"
            className="shrink-0 self-center rounded-md px-2 py-1.5 text-xs text-[var(--app-danger)] hover:bg-[var(--app-surface-hover)]"
            onClick={() => onDelete(session.id)}
          >
            删除
          </button>
        </div>
      ))}
      {!sessions.length && <p className="px-3 py-10 text-center text-sm text-app-muted">该项目还没有历史对话</p>}
    </div>
  );
}
