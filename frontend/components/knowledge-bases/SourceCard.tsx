"use client";

import Link from "next/link";
import type { ApiSource, DatabaseImport, DocRow, Entry, GitSource, OntologyCounts, SourceCleaningStat } from "./types";
import { chipSuccess } from "../../lib/themeClasses";
import {
  canSemanticCleanSource,
  semanticCleanDisabledReason,
} from "./documentIndexPolicy";
import { isSourceActivelyCleaning } from "./sourceCleaningKey";
import { indexSummaryLabel, summarizeDocs } from "./sourceIndexPolicy";
import { docStatusChip, gitSyncStatusChip } from "./utils";

export type SourceItem =
  | { kind: "git"; data: GitSource; relatedDocs?: DocRow[]; entryCount?: number }
  | { kind: "api"; data: ApiSource; relatedDocs?: DocRow[]; relatedEntries?: Entry[] }
  | { kind: "file"; entry: Entry; doc?: DocRow }
  | { kind: "api_entry"; entry: Entry; doc?: DocRow }
  | { kind: "manual"; entry: Entry; doc?: DocRow }
  | { kind: "database"; data: DatabaseImport };

interface SourceCardProps {
  source: SourceItem;
  kbId: number;
  onSemanticClean?: (source: SourceItem) => void;
  cleaningSourceKey?: string | null;
  itemCleaningKey: string;
  cleaningStat?: SourceCleaningStat;
  ontologyCounts?: OntologyCounts;
}

function formatCleaningDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()} ${d.toLocaleTimeString("zh-CN", { hour12: false })}`;
}

function SemanticCleanButton({
  source,
  itemCleaningKey,
  cleaningSourceKey,
  cleaningStat,
  onSemanticClean,
  className = "app-button-secondary text-[11px] h-7 px-2.5",
}: {
  source: SourceItem;
  itemCleaningKey: string;
  cleaningSourceKey?: string | null;
  cleaningStat?: SourceCleaningStat;
  onSemanticClean?: (source: SourceItem) => void;
  className?: string;
}) {
  const isCleaning = isSourceActivelyCleaning(itemCleaningKey, cleaningSourceKey, cleaningStat);
  const canClean = canSemanticCleanSource(source);
  const cleanReason = semanticCleanDisabledReason(source);

  return (
    <button
      className={`${className} ${isCleaning ? "is-loading" : ""}`}
      type="button"
      disabled={isCleaning || !canClean}
      title={!canClean && cleanReason ? cleanReason : undefined}
      onClick={(e) => {
        e.preventDefault();
        onSemanticClean?.(source);
      }}
    >
      {isCleaning ? "清洗中…" : "语义清洗"}
    </button>
  );
}

function CleaningInfo({
  cleaningStat,
  isCleaning,
}: {
  cleaningStat?: SourceCleaningStat;
  isCleaning: boolean;
}) {
  if (isCleaning) {
    return <p className="mt-1 text-[11px] text-blue-600 font-medium">清洗中…</p>;
  }

  const hasStat = cleaningStat && (cleaningStat.status === "completed" || cleaningStat.status === "failed");

  if (hasStat) {
    const parts: string[] = [];
    if (cleaningStat?.status === "completed") {
      parts.push(`清洗完毕 ${cleaningStat.completed_at ? formatCleaningDate(cleaningStat.completed_at) : ""}`);
    } else if (cleaningStat?.status === "failed") {
      parts.push(`清洗失败 ${cleaningStat.completed_at ? formatCleaningDate(cleaningStat.completed_at) : ""}`);
      const reason = cleaningStat.message || cleaningStat.failure_reason;
      if (reason) parts.push(reason);
    }
    return <p className="mt-1 text-[11px] text-app-muted">{parts.join(" · ")}</p>;
  }

  return <p className="mt-1 text-[11px] text-app-muted">未清洗</p>;
}

export default function SourceCard({
  source,
  kbId,
  onSemanticClean,
  cleaningSourceKey,
  itemCleaningKey,
  cleaningStat,
  ontologyCounts,
}: SourceCardProps) {
  const isCleaning = isSourceActivelyCleaning(itemCleaningKey, cleaningSourceKey, cleaningStat);

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
            <p className="mt-1 text-[11px] app-text-danger line-clamp-2 leading-snug break-words">{s.last_error}</p>
          )}
          {(() => {
            const label = indexSummaryLabel(
              summarizeDocs(source.relatedDocs ?? [], source.entryCount ?? 0),
            );
            return label ? (
              <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">{label}</p>
            ) : null;
          })()}
          <CleaningInfo cleaningStat={cleaningStat} isCleaning={isCleaning} />
        </Link>
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          <SemanticCleanButton
            source={source}
            itemCleaningKey={itemCleaningKey}
            cleaningSourceKey={cleaningSourceKey}
            cleaningStat={cleaningStat}
            onSemanticClean={onSemanticClean}
          />
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
      s.integration === "notion" ? "text-app-secondary" :
      s.integration === "confluence" ? "app-text-info" :
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
            <p className="mt-1 text-[11px] app-text-danger line-clamp-2 leading-snug break-words">{s.last_error}</p>
          )}
          {(() => {
            const label = indexSummaryLabel(
              summarizeDocs(source.relatedDocs ?? [], source.relatedEntries?.length ?? 0),
            );
            return label ? (
              <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">{label}</p>
            ) : null;
          })()}
          <CleaningInfo cleaningStat={cleaningStat} isCleaning={isCleaning} />
        </Link>
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          <SemanticCleanButton
            source={source}
            itemCleaningKey={itemCleaningKey}
            cleaningSourceKey={cleaningSourceKey}
            cleaningStat={cleaningStat}
            onSemanticClean={onSemanticClean}
          />
        </div>
      </article>
    );
  }

  // API-imported entry (e.g. Notion, Confluence, 飞书)
  if (source.kind === "api_entry") {
    const { entry, doc } = source;
    const chip = doc ? docStatusChip(doc.status) : { text: "已导入", className: chipSuccess };
    const metaKind = entry.source_meta?.kind || "";
    const integrationLabel =
      metaKind === "notion_api" ? "Notion" :
      metaKind === "confluence_api" ? "Confluence" :
      metaKind === "feishu_api" ? "飞书" : metaKind.replace("_api", "");
    const integrationColor =
      metaKind === "notion_api" ? "text-app-secondary" :
      metaKind === "confluence_api" ? "app-text-info" :
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
          {doc?.status === "failed" && doc.error_message && (
            <p className="mt-1 text-[11px] app-text-danger line-clamp-2 leading-snug break-words">{doc.error_message}</p>
          )}
          <CleaningInfo cleaningStat={cleaningStat} isCleaning={isCleaning} />
        </Link>
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          <SemanticCleanButton
            source={source}
            itemCleaningKey={itemCleaningKey}
            cleaningSourceKey={cleaningSourceKey}
            cleaningStat={cleaningStat}
            onSemanticClean={onSemanticClean}
          />
        </div>
      </article>
    );
  }

  // Manual entry
  if (source.kind === "manual") {
    const { entry, doc } = source;
    const chip = { text: "手动", className: chipSuccess };

    return (
      <article className="app-card app-card-interactive group flex flex-col gap-2 p-3 overflow-hidden">
        <Link
          href={`/knowledge-bases/${kbId}/sources/${entry.id}?type=manual`}
          className="no-underline flex-1 min-w-0"
        >
          <div className="flex items-start gap-2">
            <span className="shrink-0 mt-0.5 text-app-secondary">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-[13px] text-app-primary truncate leading-snug">{entry.title}</p>
              <p className="text-[11px] text-app-muted mt-0.5 truncate leading-snug">手动条目</p>
            </div>
            <span className={`inline-flex shrink-0 items-center rounded-full border px-1.5 py-0 text-[10px] font-medium leading-5 ${chip.className}`}>
              {chip.text}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">
            {new Date(entry.created_at).toLocaleString()}
          </p>
          {doc && (
            <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">
              {docStatusChip(doc.status).text}
              {doc.char_count != null ? ` · ${doc.char_count.toLocaleString()} 字符` : ""}
            </p>
          )}
          <CleaningInfo cleaningStat={cleaningStat} isCleaning={isCleaning} />
        </Link>
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          <SemanticCleanButton
            source={source}
            itemCleaningKey={itemCleaningKey}
            cleaningSourceKey={cleaningSourceKey}
            cleaningStat={cleaningStat}
            onSemanticClean={onSemanticClean}
          />
        </div>
      </article>
    );
  }

  // Database import
  if (source.kind === "database") {
    const s = source.data;
    const dbCount = s.database_names.length;
    const dbList = s.database_names.join(", ");
    return (
      <article className="app-card app-card-interactive group flex flex-col gap-2 p-3 overflow-hidden">
        <Link
          href={`/knowledge-bases/${kbId}/sources/${s.id}?type=database`}
          className="no-underline flex-1 min-w-0"
        >
          <div className="flex items-start gap-2">
            <span className="shrink-0 mt-0.5 text-cyan-600">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <ellipse cx="12" cy="6" rx="8" ry="3" />
                <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
                <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-[13px] text-app-primary truncate leading-snug">
                {s.datasource_name}
              </p>
              <p className="text-[11px] text-app-muted mt-0.5 truncate leading-snug">
                {dbCount} 个数据库：{dbList}
              </p>
            </div>
          </div>
          <p className="mt-1.5 text-[11px] text-app-muted truncate leading-snug">
            导入于 {new Date(s.created_at).toLocaleString()}
          </p>
          {s.last_error && (
            <p className="mt-1 text-[11px] app-text-danger line-clamp-2 leading-snug break-words">{s.last_error}</p>
          )}
          <CleaningInfo cleaningStat={cleaningStat} isCleaning={isCleaning} />
        </Link>
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
          <SemanticCleanButton
            source={source}
            itemCleaningKey={itemCleaningKey}
            cleaningSourceKey={cleaningSourceKey}
            cleaningStat={cleaningStat}
            onSemanticClean={onSemanticClean}
          />
        </div>
      </article>
    );
  }

  // File upload
  const { entry, doc } = source;
  const chip = doc ? docStatusChip(doc.status) : { text: "已导入", className: chipSuccess };
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
          <span className="shrink-0 mt-0.5 app-text-accent">
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
        {doc?.status === "failed" && doc.error_message && (
          <p className="mt-1 text-[11px] app-text-danger line-clamp-2 leading-snug break-words">{doc.error_message}</p>
        )}
        <CleaningInfo cleaningStat={cleaningStat} isCleaning={isCleaning} />
      </Link>
      <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.preventDefault()}>
        <SemanticCleanButton
          source={source}
          itemCleaningKey={itemCleaningKey}
          cleaningSourceKey={cleaningSourceKey}
          cleaningStat={cleaningStat}
          onSemanticClean={onSemanticClean}
        />
      </div>
    </article>
  );
}
