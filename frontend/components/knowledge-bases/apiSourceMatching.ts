import type { ApiSource, DocRow, Entry } from "./types";

export function integrationKind(integration: string): string {
  return `${(integration || "").trim().toLowerCase()}_api`;
}

/** 条目是否属于某 API 导入源配置（含历史数据：仅 kind/ref 无 api_source_id）。 */
export function entryMatchesApiSource(entry: Entry, apiSource: ApiSource): boolean {
  const meta = entry.source_meta || {};
  const kind = integrationKind(apiSource.integration);
  if (meta.kind !== kind) return false;
  if (String(meta.api_source_id || "") === String(apiSource.id)) return true;
  const oid = (apiSource.object_id || "").trim();
  if (oid) return String(meta.ref || "") === oid;
  return !meta.api_source_id;
}

export function docMatchesApiSource(
  doc: DocRow,
  apiSource: ApiSource,
  linkedEntryIds: Set<number>,
): boolean {
  if (doc.knowledge_entry_id != null && linkedEntryIds.has(doc.knowledge_entry_id)) {
    return true;
  }
  const meta = doc.source_meta || {};
  const kind = integrationKind(apiSource.integration);
  if (meta.kind !== kind) return false;
  if (String(meta.api_source_id || "") === String(apiSource.id)) return true;
  const oid = (apiSource.object_id || "").trim();
  if (oid) return String(meta.ref || "") === oid;
  return !meta.api_source_id;
}

/** 是否在当前 KB 已绑定或已有导入数据。 */
export function shouldShowApiSourceInKb(
  apiSource: ApiSource,
  entries: Entry[],
  documents: DocRow[],
): boolean {
  const linkedEntries = entries.filter((entry) => entryMatchesApiSource(entry, apiSource));
  if (linkedEntries.length > 0) return true;
  const linkedEntryIds = new Set(linkedEntries.map((entry) => entry.id));
  return documents.some((doc) => docMatchesApiSource(doc, apiSource, linkedEntryIds));
}
