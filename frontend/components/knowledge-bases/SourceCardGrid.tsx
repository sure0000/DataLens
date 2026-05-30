"use client";

import type { ApiSource, DatabaseImport, DocRow, Entry, GitSource, OntologyCounts, SourceCleaningStat } from "./types";
import SourceCard, { type SourceItem } from "./SourceCard";
import { docsForApiSource, docsForGitSource } from "./sourceIndexPolicy";
import { importSourceCleaningKey } from "./sourceCleaningKey";

interface SourceCardGridProps {
  gitSources: GitSource[];
  apiSources?: ApiSource[];
  entries: Entry[];
  documents: DocRow[];
  databaseImports: DatabaseImport[];
  kbId: number;
  onRefresh?: () => void;
  onSemanticClean?: (source: SourceItem) => void;
  cleaningSourceKey?: string | null;
  cleaningStats?: Record<string, SourceCleaningStat> | null;
  ontologyCounts?: OntologyCounts;
}

export default function SourceCardGrid({
  gitSources,
  apiSources = [],
  entries,
  documents,
  databaseImports,
  kbId,
  onRefresh,
  onSemanticClean,
  cleaningSourceKey,
  cleaningStats,
  ontologyCounts,
}: SourceCardGridProps) {
  function apiEntrySourceId(entry: Entry): number | null {
    const raw = entry.source_meta?.api_source_id;
    const parsed =
      typeof raw === "number" || typeof raw === "string" ? Number(raw) : Number.NaN;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  // Build flat source items list
  const items: SourceItem[] = [];

  for (const gs of gitSources) {
    const gitEntries = entries.filter(
      (e) =>
        e.source_meta?.kind === "git_file" &&
        String(e.source_meta?.git_source_id) === String(gs.id),
    );
    items.push({
      kind: "git",
      data: gs,
      relatedDocs: docsForGitSource(gs, entries, documents),
      entryCount: gitEntries.length,
    });
  }

  for (const as of apiSources) {
    const { entries: relatedEntries, docs: relatedDocs } = docsForApiSource(as, entries, documents);
    items.push({ kind: "api", data: as, relatedEntries, relatedDocs });
  }

  // Document lookup by entry id
  const docByEntryId: Record<number, DocRow> = {};
  for (const d of documents) {
    if (d.knowledge_entry_id != null) {
      docByEntryId[d.knowledge_entry_id] = d;
    }
  }

  // File / API-imported entries
  // Exclude git_file and manual: codebase indexed files should not appear
  // as standalone cards in the source list.
  const importedKinds = new Set(["file", "notion_api", "confluence_api", "feishu_api", "web"]);
  const importedEntries = entries.filter((e) => {
    const kind = String(e.source_meta?.kind || "");
    if (kind === "git_file" || kind === "manual") return false;
    if (kind && importedKinds.has(kind)) return true;
    // Legacy fallback: entries with linked docs but without explicit kind
    // are still treated as file cards.
    return docByEntryId[e.id] != null && !kind;
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
    items.push({ kind: "manual", entry, doc: docByEntryId[entry.id] });
  }

  // Database imports
  for (const di of databaseImports) {
    items.push({ kind: "database", data: di });
  }

  const totalSources = items.length;

  if (totalSources === 0) {
    return (
      <p className="text-sm text-app-muted">
        暂无导入源。通过「本体清洗」上传文件、接入数据库、代码库、API 或手动条目来添加。
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
          const apiEntryId = item.kind === "api_entry" ? apiEntrySourceId(item.entry) : null;
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
            item.kind === "api_entry"
              ? importSourceCleaningKey(
                  apiEntryId != null ? "api" : "file",
                  apiEntryId ?? item.entry.id,
                ) :
            item.kind === "manual" ? importSourceCleaningKey("manual", item.entry.id) :
            importSourceCleaningKey("file", item.entry.id);

          const cleaningStat = cleaningStats?.[cleaningKey];

          return (
            <SourceCard
              key={key}
              source={item}
              kbId={kbId}
              onSemanticClean={onSemanticClean}
              cleaningSourceKey={cleaningSourceKey}
              itemCleaningKey={cleaningKey}
              cleaningStat={cleaningStat}
              ontologyCounts={ontologyCounts}
            />
          );
        })}
      </div>
    </section>
  );
}
