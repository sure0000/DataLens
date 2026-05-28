import type { EvidencePackage } from "./ingestionTypes";

/** 与后端 PipelineRun 的 `source_type:source_id` 键一致（见 source-cleaning-stats）。 */
export function sourceCleaningKey(
  sourceId: number,
  sourceType: "git" | "api" | "database" | "manual" | "file",
): string {
  return `source:${sourceType}:${sourceId}`;
}

/** 从证据包 source_ref / 合成 id 解析对应的清洗状态键。 */
export function evidencePackageCleaningKey(pkg: EvidencePackage): string | null {
  const ref = pkg.source_ref ?? {};

  if (pkg.connector === "database") {
    if (typeof ref.import_id === "number") {
      return sourceCleaningKey(ref.import_id, "database");
    }
    const m = /^db-(\d+)$/.exec(pkg.id);
    if (m) return sourceCleaningKey(Number(m[1]), "database");
    return null;
  }

  if (pkg.connector === "git") {
    if (typeof ref.git_source_id === "number") {
      return sourceCleaningKey(ref.git_source_id, "git");
    }
    const m = /^git-(\d+)-/.exec(pkg.id);
    if (m) return sourceCleaningKey(Number(m[1]), "git");
    return null;
  }

  if (pkg.connector === "api") {
    if (typeof ref.source_id === "number") {
      return sourceCleaningKey(ref.source_id, "api");
    }
    return null;
  }

  if (pkg.connector === "manual" && typeof ref.entry_id === "number") {
    return sourceCleaningKey(ref.entry_id, "manual");
  }

  if (typeof ref.entry_id === "number") {
    const kind = String(ref.kind ?? "").toLowerCase();
    if (kind === "manual") {
      return sourceCleaningKey(ref.entry_id, "manual");
    }
    if (kind === "notion" || kind === "confluence" || kind === "feishu" || kind === "api") {
      if (typeof ref.source_id === "number") {
        return sourceCleaningKey(ref.source_id, "api");
      }
    }
    return sourceCleaningKey(ref.entry_id, "file");
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
