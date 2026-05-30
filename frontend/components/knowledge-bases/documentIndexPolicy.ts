import type { DocRow, Entry } from "./types";
import { MAX_AUTO_INDEX_ATTEMPTS } from "./types";
import type { SourceItem } from "./SourceCard";
import {
  canSemanticCleanSourceItem,
  semanticCleanDisabledReasonForSource,
} from "./sourceIndexPolicy";

const IN_PROGRESS_STATUSES = new Set([
  "pending",
  "extracting",
  "cleaning",
  "chunking",
  "embedding",
  "ontology_assertion",
]);

export function isDocumentIndexingInProgress(doc?: DocRow): boolean {
  return !!doc?.status && IN_PROGRESS_STATUSES.has(doc.status);
}

/**
 * 是否仍有文档索引任务在执行。
 * 仅依据文档 status 的中间态判断；「有条目无文档」等静态缺口不触发轮询。
 */
export function kbHasActiveDocumentIndexing(
  documents: DocRow[],
  _entries?: Entry[],
): boolean {
  return documents.some((d) => isDocumentIndexingInProgress(d));
}

export function canRetryDocumentIndex(doc?: DocRow): boolean {
  if (!doc) return false;
  const attempts = doc.index_attempts ?? 0;
  if (doc.status === "pending") {
    return true;
  }
  return doc.status === "failed" && attempts < MAX_AUTO_INDEX_ATTEMPTS;
}

export function canManualDocumentIndex(doc?: DocRow): boolean {
  if (!doc) return false;
  return (
    doc.status === "failed" &&
    (doc.index_attempts ?? 0) >= MAX_AUTO_INDEX_ATTEMPTS
  );
}

/** 文档类源是否尚未完成索引（用于展示索引相关操作） */
export function needsDocumentIndexing(doc?: DocRow): boolean {
  if (!doc) return true;
  return doc.status !== "indexed";
}

export function canSemanticCleanSource(source: SourceItem): boolean {
  return canSemanticCleanSourceItem(source);
}

export function semanticCleanDisabledReason(source: SourceItem): string | null {
  return semanticCleanDisabledReasonForSource(source);
}
