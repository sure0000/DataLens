"use client";

import type { DocRow, Entry, GitSource } from "./types";
import SourceCard, { type SourceItem } from "./SourceCard";

interface SourceCardGridProps {
  gitSources: GitSource[];
  entries: Entry[];
  documents: DocRow[];
  kbId: number;
  gitSyncingId?: number | null;
  onSyncGit?: (id: number) => void;
  onRetryDoc?: (docId: number) => void;
  onRefresh?: () => void;
  onAddTag?: (source: SourceItem, tag: string) => void;
  onRemoveTag?: (source: SourceItem, tag: string) => void;
  tagLoading?: boolean;
}

export default function SourceCardGrid({
  gitSources,
  entries,
  documents,
  kbId,
  gitSyncingId,
  onSyncGit,
  onRetryDoc,
  onRefresh,
  onAddTag,
  onRemoveTag,
  tagLoading,
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

  // File entries and API-imported entries — each gets a card
  const importedKinds = new Set(["file", "notion_api", "confluence_api", "feishu_api"]);
  const importedEntries = entries.filter((e) => {
    const kind = e.source_meta?.kind;
    return kind != null && importedKinds.has(kind);
  });

  for (const entry of importedEntries) {
    const doc = docByEntryId[entry.id];
    const metaKind = entry.source_meta?.kind;
    if (metaKind === "file") {
      items.push({ kind: "file", entry, doc });
    } else {
      items.push({ kind: "api_entry", entry, doc });
    }
  }

  const totalSources = items.length;

  if (totalSources === 0) {
    return (
      <p className="text-sm text-app-muted">
        暂无导入源。通过「导入」上传文件或接入代码/API 源来添加。
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
            item.kind === "api_entry" ? `api-entry-${item.entry.id}` :
            `file-${item.entry.id}`;
          return (
            <SourceCard
              key={key}
              source={item}
              kbId={kbId}
              gitSyncingId={gitSyncingId}
              onSyncGit={onSyncGit}
              onRetryDoc={onRetryDoc}
              onAddTag={onAddTag}
              onRemoveTag={onRemoveTag}
              tagLoading={tagLoading}
            />
          );
        })}
      </div>
    </section>
  );
}
