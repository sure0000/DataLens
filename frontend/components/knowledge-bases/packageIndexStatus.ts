import type { DocRow } from "./types";
import type { EvidencePackage } from "./ingestionTypes";
import type { PipelineStepIconStatus } from "../icons";
import { isDocumentIndexingInProgress } from "./documentIndexPolicy";

/** 将证据包关联到当前 KB 文档列表（与后端 _hydrate_package_document_stats 规则对齐） */
export function resolvePackageDocuments(
  pkg: EvidencePackage,
  documents: DocRow[],
): DocRow[] {
  const ref = pkg.source_ref ?? {};
  const matched = new Map<number, DocRow>();

  const linkedDocId =
    pkg.linked_document_id ??
    (typeof ref.document_id === "number" ? ref.document_id : undefined);
  if (linkedDocId != null) {
    const byId = documents.find((d) => d.id === linkedDocId);
    if (byId) matched.set(byId.id, byId);
  }

  const entryIds = new Set<number>();
  if (typeof ref.entry_id === "number") entryIds.add(ref.entry_id);
  for (const eid of pkg.linked_entry_ids ?? []) {
    if (typeof eid === "number") entryIds.add(eid);
  }

  for (const d of documents) {
    if (d.knowledge_entry_id != null && entryIds.has(d.knowledge_entry_id)) {
      matched.set(d.id, d);
    }
  }

  return [...matched.values()];
}

function indexingStepIconFromCounts(
  pkg: EvidencePackage,
  total: number,
  indexed: number,
  failed: number,
): PipelineStepIconStatus {
  const inProgress = Math.max(0, total - indexed - failed);
  if (total > 0 && indexed >= total) return "ok";
  if (total > 0 && indexed === 0 && failed > 0 && inProgress === 0) return "fail";
  if (inProgress > 0) return "running";
  if (pkg.processing_state === "ready_for_extraction" || pkg.processing_state === "indexed") {
    return "ok";
  }
  if (pkg.processing_state === "normalized") return "running";
  if (total > 0 && indexed > 0 && indexed < total) return "running";
  return "pending";
}

/** 优先用实时 documents 计算索引步骤，避免证据包 API 计数滞后 */
export function indexingStepIconForPackage(
  pkg: EvidencePackage,
  documents: DocRow[],
): PipelineStepIconStatus {
  // 代码库清洗直接读取 git_file 条目正文，不依赖文档分块索引。
  if (pkg.connector === "git") {
    if (pkg.processing_state === "ready_for_extraction" || pkg.processing_state === "indexed") {
      return "ok";
    }
    if (pkg.processing_state === "normalized") {
      return "ok";
    }
    return "pending";
  }

  const linked = resolvePackageDocuments(pkg, documents);
  if (linked.length > 0) {
    const indexed = linked.filter((d) => d.status === "indexed").length;
    const failed = linked.filter((d) => d.status === "failed").length;
    const inProgress = linked.filter((d) => isDocumentIndexingInProgress(d)).length;
    const total = linked.length;
    if (inProgress > 0) return "running";
    return indexingStepIconFromCounts(pkg, total, indexed, failed);
  }

  const total = pkg.document_count ?? 0;
  const indexed = pkg.indexed_document_count ?? 0;
  const failed = pkg.failed_document_count ?? 0;
  return indexingStepIconFromCounts(pkg, total, indexed, failed);
}

export function documentStatusFingerprint(documents: DocRow[]): string {
  return documents
    .map((d) => `${d.id}:${d.status ?? ""}`)
    .sort()
    .join("|");
}
