import type { EvidencePackage } from "./ingestionTypes";

/** 与后端 PipelineRun 的 `source_type:source_id` 键一致（见 source-cleaning-stats）。 */
export function sourceCleaningKey(
  sourceId: number,
  sourceType: "git" | "api" | "database" | "manual" | "file",
): string {
  return `source:${sourceType}:${sourceId}`;
}

/** 解析 source_ref 中的数值 id（API/DB 可能返回 number 或 string）。 */
export function parseRefSourceId(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return null;
}

/** 从证据包 source_ref / 合成 id 解析对应的清洗状态键。 */
export function evidencePackageCleaningKey(pkg: EvidencePackage): string | null {
  const ref = pkg.source_ref ?? {};

  if (pkg.connector === "database") {
    const importId = parseRefSourceId(ref.import_id);
    if (importId != null) {
      return sourceCleaningKey(importId, "database");
    }
    const m = /^db-(\d+)$/.exec(pkg.id);
    if (m) return sourceCleaningKey(Number(m[1]), "database");
    return null;
  }

  if (pkg.connector === "git") {
    const gitSourceId = parseRefSourceId(ref.git_source_id);
    if (gitSourceId != null) {
      return sourceCleaningKey(gitSourceId, "git");
    }
    const m = /^git-(\d+)/.exec(pkg.id);
    if (m) return sourceCleaningKey(Number(m[1]), "git");
    return null;
  }

  if (pkg.connector === "api") {
    const apiSourceId = parseRefSourceId(ref.source_id ?? ref.api_source_id);
    if (apiSourceId != null) {
      return sourceCleaningKey(apiSourceId, "api");
    }
    return null;
  }

  const entryId = parseRefSourceId(ref.entry_id);
  if (pkg.connector === "manual" && entryId != null) {
    return sourceCleaningKey(entryId, "manual");
  }

  if (entryId != null) {
    const kind = String(ref.kind ?? "").toLowerCase();
    if (kind === "manual") {
      return sourceCleaningKey(entryId, "manual");
    }
    if (kind === "notion" || kind === "confluence" || kind === "feishu" || kind === "api") {
      const apiSourceId = parseRefSourceId(ref.source_id ?? ref.api_source_id);
      if (apiSourceId != null) {
        return sourceCleaningKey(apiSourceId, "api");
      }
    }
    return sourceCleaningKey(entryId, "file");
  }

  return null;
}

/** 导入源卡片用的清洗键（与 handleSemanticClean / PipelineRun 一致）。 */
export function importSourceCleaningKey(
  kind: "git" | "api" | "database" | "file" | "manual" | "api_entry",
  sourceId: number,
): string {
  const type = kind === "api_entry" ? "api" : kind;
  return sourceCleaningKey(sourceId, type);
}

/** 与 PipelineRun.source_type + source_id 及 source-cleaning-stats 的键一致。 */
export function pipelineRunCleaningKey(
  sourceType: string | null | undefined,
  sourceId: number | null | undefined,
): string | null {
  if (!sourceType || sourceId == null) return null;
  const t = sourceType.startsWith("source:") ? sourceType : `source:${sourceType}`;
  return `${t}:${sourceId}`;
}

/** 导入源卡片是否处于「清洗中」（本地触发 + 后端 running 状态）。 */
export function isSourceActivelyCleaning(
  itemCleaningKey: string,
  activeCleaningKey: string | null | undefined,
  cleaningStat?: { status?: string } | null,
): boolean {
  if (activeCleaningKey === itemCleaningKey) return true;
  return cleaningStat?.status === "running";
}
