"use client";

import type { DatabaseImport, DocRow, Entry, GitSource, OntologyCounts, SourceCleaningStat } from "./types";
import SourceCard, { type SourceItem } from "./SourceCard";
import { importSourceCleaningKey } from "./sourceCleaningKey";

interface SourceCardGridProps {
  gitSources: GitSource[];
  entries: Entry[];
  documents: DocRow[];
  databaseImports: DatabaseImport[];
  kbId: number;
  gitSyncingId?: number | null;
  onSyncGit?: (id: number) => void;
  onRetryDoc?: (docId: number) => void;
  onManualIndexDoc?: (docId: number) => void;
  onRefresh?: () => void;
  onAddTag?: (source: SourceItem, tag: string) => void;
  onRemoveTag?: (source: SourceItem, tag: string) => void;
  tagLoading?: boolean;
  onSemanticClean?: (source: SourceItem) => void;
  cleaningSourceId?: number | null;
  cleaningStats?: Record<string, SourceCleaningStat> | null;
  ontologyCounts?: OntologyCounts;
}

export default function SourceCardGrid({
  gitSources,
  entries,
  documents,
  databaseImports,
  kbId,
  gitSyncingId,
  onSyncGit,
  onRetryDoc,
  onManualIndexDoc,
  onRefresh,
  onAddTag,
  onRemoveTag,
  tagLoading,
  onSemanticClean,
  cleaningSourceId,
  cleaningStats,
  ontologyCounts,
}: SourceCardGridProps) {
  // Build flat source items list
  const items: SourceItem[] = [];

  for (const gs of gitSources) {
    items.push({ kind: "git", data: gs });
  }

  // Document lookup by entry id
  const docByEntryId: Record<number, DocRow> = {};
  for (const d of documents) {
    if (d.knowledge_entry_id != null) {
      docByEntryId[d.knowledge_entry_id] = d;
    }
  }

  // File / API-imported entries — include any entry with a linked document or known import kind
  const importedKinds = new Set(["file", "notion_api", "confluence_api", "feishu_api", "web"]);
  const importedEntries = entries.filter((e) => {
    const kind = e.source_meta?.kind;
    return docByEntryId[e.id] != null || (kind != null && importedKinds.has(kind));
  });

  for (const entry of importedEntries) {
    const doc = docByEntryId[entry.id];
    const metaKind = entry.source_meta?.kind ?? "";
    if (metaKind === "file" || metaKind === "web" || (!metaKind.includes("_api") && doc)) {
      items.push({ kind: "file", entry, doc });
    } else {
      items.push({ kind: "api_entry", entry, doc });
    }
  }

  const manualEntries = entries.filter((e) => e.source_meta?.kind === "manual");
  for (const entry of manualEntries) {
    items.push({ kind: "manual", entry });
  }

  // Database imports
  for (const di of databaseImports) {
    items.push({ kind: "database", data: di });
  }

  const totalSources = items.length;

  if (totalSources === 0) {
    return (
      <p className="text-sm text-app-muted">
        暂无导入源。通过「数据接入」上传文件、接入数据库、代码库、API 或手动条目来添加。
      </p>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="app-section-title">导入源</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-app-muted">{totalSources} 个源</span>
          {onRefresh && (
            <button className="app-button-secondary text-sm" type="button" onClick={onRefresh}>
              刷新
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => {
          const key =
            item.kind === "git" ? `git-${item.data.id}` :
            item.kind === "api" ? `api-${item.data.id}` :
            item.kind === "database" ? `db-${item.data.id}` :
            item.kind === "api_entry" ? `api-entry-${item.entry.id}` :
            item.kind === "manual" ? `manual-${item.entry.id}` :
            `file-${item.entry.id}`;

          const cleaningKey =
            item.kind === "git" ? importSourceCleaningKey("git", item.data.id) :
            item.kind === "api" ? importSourceCleaningKey("api", item.data.id) :
            item.kind === "database" ? importSourceCleaningKey("database", item.data.id) :
            item.kind === "api_entry" ? importSourceCleaningKey("api_entry", item.entry.id) :
            item.kind === "manual" ? importSourceCleaningKey("manual", item.entry.id) :
            importSourceCleaningKey("file", item.entry.id);

          const cleaningStat = cleaningStats?.[cleaningKey];

          return (
            <SourceCard
              key={key}
              source={item}
              kbId={kbId}
              gitSyncingId={gitSyncingId}
              onSyncGit={onSyncGit}
              onRetryDoc={onRetryDoc}
              onManualIndexDoc={onManualIndexDoc}
              onAddTag={onAddTag}
              onRemoveTag={onRemoveTag}
              tagLoading={tagLoading}
              onSemanticClean={onSemanticClean}
              cleaningSourceId={cleaningSourceId}
              cleaningStat={cleaningStat}
              ontologyCounts={ontologyCounts}
            />
          );
        })}
      </div>
    </section>
  );
}
