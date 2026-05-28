import type { ApiSource, DocRow, Entry, GitSource } from "./types";
import { entryMatchesApiSource } from "./apiSourceMatching";
import type { SourceItem } from "./SourceCard";
import {
  isDocumentIndexingInProgress,
} from "./documentIndexPolicy";

export type SourceIndexSummary = {
  totalEntries: number;
  docCount: number;
  indexedCount: number;
  failedCount: number;
  inProgressCount: number;
  pendingIndexCount: number;
};

export function docsForGitSource(
  gitSource: GitSource,
  entries: Entry[],
  documents: DocRow[],
): DocRow[] {
  const entryIds = new Set(
    entries
      .filter(
        (e) =>
          e.source_meta?.kind === "git_file" &&
          String(e.source_meta?.git_source_id) === String(gitSource.id),
      )
      .map((e) => e.id),
  );
  return documents.filter((d) => d.knowledge_entry_id != null && entryIds.has(d.knowledge_entry_id));
}

export function docsForApiSource(
  apiSource: ApiSource,
  entries: Entry[],
  documents: DocRow[],
): { entries: Entry[]; docs: DocRow[] } {
  const matchedEntries = entries.filter((e) => entryMatchesApiSource(e, apiSource));
  const entryIds = new Set(matchedEntries.map((e) => e.id));
  const docs = documents.filter(
    (d) => d.knowledge_entry_id != null && entryIds.has(d.knowledge_entry_id),
  );
  return { entries: matchedEntries, docs };
}

export function summarizeDocs(docs: DocRow[], entryCount: number): SourceIndexSummary {
  let indexedCount = 0;
  let failedCount = 0;
  let inProgressCount = 0;
  for (const d of docs) {
    if (d.status === "indexed") indexedCount += 1;
    else if (d.status === "failed") failedCount += 1;
    else if (isDocumentIndexingInProgress(d)) inProgressCount += 1;
  }
  return {
    totalEntries: entryCount,
    docCount: docs.length,
    indexedCount,
    failedCount,
    inProgressCount,
    pendingIndexCount: Math.max(0, entryCount - docs.length),
  };
}

export function indexSummaryLabel(summary: SourceIndexSummary): string | null {
  const parts: string[] = [];
  if (summary.totalEntries > 0) parts.push(`${summary.totalEntries} 条目`);
  if (summary.indexedCount > 0) parts.push(`${summary.indexedCount} 已索引`);
  if (summary.inProgressCount > 0) parts.push(`${summary.inProgressCount} 索引中`);
  if (summary.pendingIndexCount > 0) parts.push(`${summary.pendingIndexCount} 待建索引`);
  if (summary.failedCount > 0) parts.push(`${summary.failedCount} 失败`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function aggregateCanSemanticClean(summary: SourceIndexSummary): boolean {
  return summary.indexedCount > 0;
}

export function aggregateSemanticCleanDisabledReason(summary: SourceIndexSummary): string | null {
  if (summary.totalEntries === 0) {
    return "暂无关联条目，请先导入";
  }
  if (summary.indexedCount > 0) return null;
  if (summary.pendingIndexCount > 0 && summary.docCount === 0) {
    return "条目已导入但尚无文档索引，请在详情页「设置 → 重新索引」";
  }
  if (summary.inProgressCount > 0) {
    return "文档索引进行中，请稍候";
  }
  if (summary.failedCount > 0) {
    return "部分文档索引失败，请先在详情页重试或重新索引";
  }
  return "尚无已完成索引的文档";
}

export function getSourceIndexContext(source: SourceItem): {
  summary?: SourceIndexSummary;
  primaryDoc?: DocRow;
} {
  if (source.kind === "git") {
    const summary = summarizeDocs(source.relatedDocs ?? [], source.entryCount ?? 0);
    return { summary };
  }
  if (source.kind === "api") {
    const summary = summarizeDocs(source.relatedDocs ?? [], source.relatedEntries?.length ?? 0);
    return { summary };
  }
  if (source.kind === "file" || source.kind === "api_entry" || source.kind === "manual") {
    return { primaryDoc: source.doc };
  }
  return {};
}

export function canSemanticCleanSourceItem(source: SourceItem): boolean {
  void source;
  return true;
}

export function semanticCleanDisabledReasonForSource(source: SourceItem): string | null {
  void source;
  return null;
}
