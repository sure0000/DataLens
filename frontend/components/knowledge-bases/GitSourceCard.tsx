"use client";

import type { GitSource } from "./types";
import { gitBranchLabel, gitSyncStatusChip } from "./utils";

interface GitSourceCardProps {
  source: GitSource;
  syncing: boolean;
  onSync: () => void;
  onBrowse: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export default function GitSourceCard({
  source: s,
  syncing,
  onSync,
  onBrowse,
  onEdit,
  onDelete,
}: GitSourceCardProps) {
  const chip = gitSyncStatusChip(s.last_sync_status);

  return (
    <div className="app-card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-sm text-app-primary truncate">{s.name}</p>
          <p className="text-xs text-app-muted mt-0.5">
            {s.provider === "gitlab" ? "GitLab" : "GitHub"} · {s.owner}/{s.repo}
          </p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${chip.className}`}
        >
          {chip.text}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-app-muted">
        <span>分支：{gitBranchLabel(s)}</span>
        {s.path_prefix && <span>路径：{s.path_prefix}</span>}
        <span>限制：{s.max_files} 文件 / {s.max_file_kb} KB</span>
        {s.cron_expression && <span>定时：{s.cron_expression}</span>}
      </div>
      {s.last_error && (
        <p className="text-xs app-text-danger leading-relaxed">{s.last_error}</p>
      )}
      {s.last_sync_at && (
        <p className="text-xs text-app-muted">
          上次同步：{new Date(s.last_sync_at).toLocaleString()}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button
          className={`app-button text-xs ${syncing ? "is-loading" : ""}`}
          type="button"
          disabled={syncing}
          onClick={onSync}
        >
          {syncing ? "同步中…" : "立即同步"}
        </button>
        <button className="app-button-secondary text-xs" type="button" onClick={onBrowse}>
          浏览文件
        </button>
        <button className="app-button-secondary text-xs" type="button" onClick={onEdit}>
          编辑
        </button>
        <button className="app-button-danger text-xs" type="button" onClick={onDelete}>
          删除
        </button>
      </div>
    </div>
  );
}
