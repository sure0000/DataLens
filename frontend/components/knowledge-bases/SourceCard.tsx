"use client";

import Link from "next/link";
import { useState } from "react";
import type { ApiSource, DocRow, Entry, GitSource } from "./types";
import { docStatusChip, gitSyncStatusChip } from "./utils";

export type SourceItem =
  | { kind: "git"; data: GitSource }
  | { kind: "api"; data: ApiSource }
  | { kind: "file"; entry: Entry; doc?: DocRow }
  | { kind: "api_entry"; entry: Entry; doc?: DocRow };

interface SourceCardProps {
  source: SourceItem;
  kbId: number;
  gitSyncingId?: number | null;
  onSyncGit?: (id: number) => void;
  onRetryDoc?: (docId: number) => void;
  onAddTag?: (source: SourceItem, tag: string) => void;
  onRemoveTag?: (source: SourceItem, tag: string) => void;
  tagLoading?: boolean;
}

function getTags(source: SourceItem): string[] {
  if (source.kind === "git") return source.data.tags ?? [];
  if (source.kind === "api") return source.data.tags ?? [];
  if (source.kind === "api_entry") return source.entry.tags ?? [];
  return source.entry.tags ?? [];
}

function TagRow({
  tags,
  tagLoading,
  onAddTag,
  onRemoveTag,
  source,
}: {
  tags: string[];
  tagLoading?: boolean;
  onAddTag?: (source: SourceItem, tag: string) => void;
  onRemoveTag?: (source: SourceItem, tag: string) => void;
  source: SourceItem;
}) {
  const [addTagOpen, setAddTagOpen] = useState(false);
  const [tagInput, setTagInput] = useState("");

  function handleAddTag() {
    const t = tagInput.trim();
    if (!t) { setAddTagOpen(false); setTagInput(""); return; }
    onAddTag?.(source, t);
    setTagInput("");
    setAddTagOpen(false);
  }

  return (
    <div className="flex flex-wrap items-center gap-1" onClick={(e) => e.preventDefault()}>
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-0.5 rounded-full border border-violet-200 bg-violet-50 px-1.5 py-0 text-[10px] font-medium text-violet-700 leading-5"
        >
          {tag}
          <button
            type="button"
            className="text-violet-400 hover:text-violet-700 leading-none"
            disabled={tagLoading}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemoveTag?.(source, tag); }}
            aria-label={`删除标签 ${tag}`}
          >
            ×
          </button>
        </span>
      ))}
      {addTagOpen ? (
        <input
          className="w-16 rounded border border-violet-300 px-1 py-0 text-[10px] outline-none focus:border-violet-500 leading-5"
          placeholder="标签名"
          value={tagInput}
          autoFocus
          disabled={tagLoading}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleAddTag(); if (e.key === "Escape") { setAddTagOpen(false); setTagInput(""); } }}
          onBlur={() => { setAddTagOpen(false); setTagInput(""); }}
        />
      ) : (
        <button
          type="button"
          className={`inline-flex items-center rounded-full border border-dashed border-app-muted px-1.5 py-0 text-[10px] text-app-muted hover:border-violet-400 hover:text-violet-600 leading-5 ${tagLoading ? "opacity-50" : ""}`}
          disabled={tagLoading}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); setAddTagOpen(true); }}
        >
          + 标签
        </button>
      )}
    </div>
  );
}

export default function SourceCard({
  source,
  kbId,
  gitSyncingId,
  onSyncGit,
  onRetryDoc,
  onAddTag,
  onRemoveTag,
  tagLoading,
}: SourceCardProps) {
  const tags = getTags(source);
  const sharedTagRow = (
    <TagRow tags={tags} tagLoading={tagLoading} onAddTag={onAddTag} onRemoveTag={onRemoveTag} source={source} />
  );

  if (source.kind === "git") {
    const s = source.data;
    const chip = gitSyncStatusChip(s.last_sync_status);
    const metaParts: string[] = [];
    metaParts.push(`分支：${s.uses_default_branch || !s.branch ? "默认分支" : s.branch}`);
    if (s.path_prefix) metaParts.push(s.path_prefix);
    if (s.last_sync_at) metaParts.push(new Date(s.last_sync_at).toLocaleString());

    return (
      <article className="app-card app-card-interactive group flex flex-col gap-2 p-3 overflow-hidden">
        <Link
          href={`/knowledge-bases/${kbId}/sources/${s.id}?type=git`}
          className="no-underline flex-1 min-w-0"
        >
          <div className="flex items-start gap-2">
            <span className="shrink-0 mt-0.5 text-orange-500">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 22v-4a4.8 4.8 0 00-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.47.28-1.14.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.14-.3 2.35 0 3.5A5.403 5.403 0 004 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
                <path d="M9 18c-4.51 2-5-2-7-2" />
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-[13px] text-app-primary truncate leading-snug">{s.name}</p>
              <p className="text-[11px] text-app-muted mt-0.5 truncate leading-snug">
                {s.provider === "gitlab" ? "GitLab" : "GitHub"} · {s.owner}/{s.repo}
              </p>
            </div>
            <span className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0 text-[10px] font-medium leading-5 ${chip.className}`}>
              {chip.text}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">{metaParts.join(" · ")}</p>
          {s.last_error && (
            <p className="mt-1 text-[11px] text-rose-600 line-clamp-2 leading-snug break-words">{s.last_error}</p>
          )}
        </Link>
        {tags.length > 0 && sharedTagRow}
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          <button
            className={`app-button text-[11px] h-7 px-2.5 ${gitSyncingId === s.id ? "is-loading" : ""}`}
            type="button"
            disabled={gitSyncingId === s.id}
            onClick={(e) => { e.preventDefault(); onSyncGit?.(s.id); }}
          >
            {gitSyncingId === s.id ? "同步中…" : "同步"}
          </button>
          {tags.length === 0 && sharedTagRow}
        </div>
      </article>
    );
  }

  if (source.kind === "api") {
    const s = source.data;
    const chip = gitSyncStatusChip(s.last_sync_status);
    const integrationLabel =
      s.integration === "notion" ? "Notion" :
      s.integration === "confluence" ? "Confluence" :
      s.integration === "feishu" ? "飞书" : s.integration;
    const integrationColor =
      s.integration === "notion" ? "text-gray-700" :
      s.integration === "confluence" ? "text-blue-600" :
      s.integration === "feishu" ? "text-sky-600" : "text-app-muted";

    return (
      <article className="app-card app-card-interactive group flex flex-col gap-2 p-3 overflow-hidden">
        <Link
          href={`/knowledge-bases/${kbId}/sources/${s.id}?type=api`}
          className="no-underline flex-1 min-w-0"
        >
          <div className="flex items-start gap-2">
            <span className={`shrink-0 mt-0.5 ${integrationColor}`}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-[13px] text-app-primary truncate leading-snug">{s.name}</p>
              <p className="text-[11px] text-app-muted mt-0.5 truncate leading-snug">{integrationLabel} · {s.object_id}</p>
            </div>
            <span className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0 text-[10px] font-medium leading-5 ${chip.className}`}>
              {chip.text}
            </span>
          </div>
          {s.last_sync_at && (
            <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">
              {new Date(s.last_sync_at).toLocaleString()}
            </p>
          )}
          {s.last_error && (
            <p className="mt-1 text-[11px] text-rose-600 line-clamp-2 leading-snug break-words">{s.last_error}</p>
          )}
        </Link>
        {tags.length > 0 && sharedTagRow}
      </article>
    );
  }

  // API-imported entry (e.g. Notion, Confluence, 飞书)
  if (source.kind === "api_entry") {
    const { entry, doc } = source;
    const chip = doc ? docStatusChip(doc.status) : { text: "已导入", className: "border-emerald-200 bg-emerald-50 text-emerald-800" };
    const metaKind = entry.source_meta?.kind || "";
    const integrationLabel =
      metaKind === "notion_api" ? "Notion" :
      metaKind === "confluence_api" ? "Confluence" :
      metaKind === "feishu_api" ? "飞书" : metaKind.replace("_api", "");
    const integrationColor =
      metaKind === "notion_api" ? "text-gray-700" :
      metaKind === "confluence_api" ? "text-blue-600" :
      metaKind === "feishu_api" ? "text-sky-600" : "text-app-muted";

    const metaParts: string[] = [];
    if (doc?.char_count != null) metaParts.push(`${(doc.char_count ?? 0).toLocaleString()} 字符`);
    metaParts.push(new Date(entry.created_at).toLocaleString());

    return (
      <article className="app-card app-card-interactive group flex flex-col gap-2 p-3 overflow-hidden">
        <Link
          href={`/knowledge-bases/${kbId}/sources/${entry.id}?type=api`}
          className="no-underline flex-1 min-w-0"
        >
          <div className="flex items-start gap-2">
            <span className={`shrink-0 mt-0.5 ${integrationColor}`}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-[13px] text-app-primary truncate leading-snug">{entry.title}</p>
              <p className="text-[11px] text-app-muted mt-0.5 truncate leading-snug">
                {integrationLabel} · {entry.source_meta?.ref || entry.source_meta?.label || "导入"}
              </p>
            </div>
            <span className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0 text-[10px] font-medium leading-5 ${chip.className}`}>
              {chip.text}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">{metaParts.join(" · ")}</p>
        </Link>
        {tags.length > 0 && sharedTagRow}
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          {doc?.status === "failed" && (
            <button className="app-button text-[11px] h-7 px-2.5" type="button" onClick={(e) => { e.preventDefault(); onRetryDoc?.(doc.id); }}>
              重试
            </button>
          )}
          {tags.length === 0 && sharedTagRow}
        </div>
      </article>
    );
  }

  // File upload
  const { entry, doc } = source;
  const chip = doc ? docStatusChip(doc.status) : { text: "已导入", className: "border-emerald-200 bg-emerald-50 text-emerald-800" };
  const rawLabel = entry.source_meta?.label;
  const label = (rawLabel && rawLabel !== "上传文件") ? rawLabel : (entry.source_meta?.ref || entry.source_meta?.kind || "文件");

  const fileMetaParts: string[] = [];
  if (doc?.char_count != null) fileMetaParts.push(`${(doc.char_count ?? 0).toLocaleString()} 字符`);
  fileMetaParts.push(new Date(entry.created_at).toLocaleString());

  return (
    <article className="app-card app-card-interactive group flex flex-col gap-2 p-3 overflow-hidden">
      <Link
        href={`/knowledge-bases/${kbId}/sources/${entry.id}?type=file`}
        className="no-underline flex-1 min-w-0"
      >
        <div className="flex items-start gap-2">
          <span className="shrink-0 mt-0.5 text-indigo-400">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-[13px] text-app-primary truncate leading-snug">{entry.title}</p>
            <p className="text-[11px] text-app-muted mt-0.5 truncate leading-snug">{label}</p>
          </div>
          <span className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0 text-[10px] font-medium leading-5 ${chip.className}`}>
            {chip.text}
          </span>
        </div>
        <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">{fileMetaParts.join(" · ")}</p>
      </Link>
      {tags.length > 0 && sharedTagRow}
      <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
        {doc?.status === "failed" && (
          <button className="app-button text-[11px] h-7 px-2.5" type="button" onClick={(e) => { e.preventDefault(); onRetryDoc?.(doc.id); }}>
            重试
          </button>
        )}
        {tags.length === 0 && sharedTagRow}
      </div>
    </article>
  );
}
