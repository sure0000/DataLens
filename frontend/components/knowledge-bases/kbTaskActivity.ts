import type { DocRow, Entry, SourceCleaningStat } from "./types";
import type { EvidencePackage } from "./ingestionTypes";
import { resolvePackageDocuments } from "./packageIndexStatus";

/** 后台 worker 正在处理的文档状态（不含 pending，避免僵死 pending 触发无限轮询） */
export const DOCUMENT_WORKER_ACTIVE_STATUSES = new Set([
  "extracting",
  "cleaning",
  "chunking",
  "embedding",
  "ontology_assertion",
]);

export function isDocumentIndexingWorkerActive(doc?: DocRow): boolean {
  return !!doc?.status && DOCUMENT_WORKER_ACTIVE_STATUSES.has(doc.status);
}

export function documentWorkerActiveFingerprint(documents: DocRow[]): string {
  return documents
    .filter((d) => isDocumentIndexingWorkerActive(d))
    .map((d) => `${d.id}:${d.status}`)
    .sort()
    .join("|");
}

export function cleaningStatsRunningFingerprint(
  stats: Record<string, SourceCleaningStat> | null | undefined,
): string {
  if (!stats) return "";
  return Object.entries(stats)
    .filter(([, s]) => s.status === "running")
    .map(([k]) => k)
    .sort()
    .join(",");
}

function rawStepStatusToken(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && "status" in raw) {
    const st = (raw as { status?: unknown }).status;
    const done = (raw as { chunk_done?: unknown }).chunk_done;
    const total = (raw as { chunk_total?: unknown }).chunk_total;
    const base = typeof st === "string" ? st : "pending";
    if (done != null && total != null) return `${base}@${done}/${total}`;
    return base;
  }
  return "pending";
}

function cleaningStatStepsFingerprint(steps: SourceCleaningStat["steps"]): string {
  if (!steps || typeof steps !== "object") return "";
  return Object.entries(steps)
    .filter(([key]) => !key.startsWith("_"))
    .map(([key, raw]) => `${key}:${rawStepStatusToken(raw)}`)
    .sort()
    .join(";")
}

/** 清洗 stats 全量指纹（含各步骤进度，running 时步骤变化也会触发局部更新） */
export function cleaningStatsSnapshotFingerprint(
  stats: Record<string, SourceCleaningStat> | null | undefined,
): string {
  if (!stats) return "";
  return Object.entries(stats)
    .map(([k, s]) => `${k}:${s.status}:${cleaningStatStepsFingerprint(s.steps)}`)
    .sort()
    .join("|");
}

/** 轮询触发：worker 中文档 + 近期 pending（导入后索引尚未开始时） */
export function documentIndexingPollFingerprint(documents: DocRow[]): string {
  const now = Date.now();
  const recentPendingMs = 30 * 60 * 1000;
  return documents
    .filter((d) => {
      if (isDocumentIndexingWorkerActive(d)) return true;
      if (d.status !== "pending") return false;
      const created = Date.parse(d.created_at);
      return Number.isFinite(created) && now - created < recentPendingMs;
    })
    .map((d) => `${d.id}:${d.status}`)
    .sort()
    .join("|");
}

export function entriesDocumentsSnapshotFingerprint(
  entries: Entry[],
  documents: DocRow[],
): string {
  const docFp = documents
    .map((d) => `${d.id}:${d.status ?? ""}`)
    .sort()
    .join("|");
  const entryFp = entries
    .map((e) => String(e.id))
    .sort()
    .join(",");
  return `${entryFp}#${docFp}`;
}

/** 是否存在需要轮询的后台任务（worker 中文档 + 近期 pending + 清洗 running） */
export function kbHasActiveBackgroundTasks(opts: {
  documents: DocRow[];
  cleaningStats: Record<string, SourceCleaningStat> | null | undefined;
}): boolean {
  return (
    documentIndexingPollFingerprint(opts.documents).length > 0 ||
    cleaningStatsRunningFingerprint(opts.cleaningStats).length > 0
  );
}

/** 建模状态指纹（抽取步骤进度变化时触发局部更新） */
export function modelingStatusFingerprint(status: {
  pipeline_phase?: string;
  active_run?: { source_type?: string | null; source_id?: number | null } | null;
  extraction?: {
    status?: string | null;
    progress_percent?: number;
    steps?: { key: string; icon?: string; status?: string }[];
  };
} | null | undefined): string {
  if (!status) return "";
  const run = status.active_run;
  const runFp =
    run?.source_type != null && run.source_id != null
      ? `${run.source_type}:${run.source_id}`
      : "";
  const stepsFp = (status.extraction?.steps ?? [])
    .map((s) => `${s.key}:${s.icon ?? s.status ?? ""}`)
    .join(";");
  return `${status.pipeline_phase ?? ""}|${runFp}|${status.extraction?.status ?? ""}|${status.extraction?.progress_percent ?? 0}|${stepsFp}`;
}

export function packageHasActiveWorkerIndexing(
  pkg: EvidencePackage,
  documents: DocRow[],
): boolean {
  const linked = resolvePackageDocuments(pkg, documents);
  return linked.some((d) => isDocumentIndexingWorkerActive(d));
}
