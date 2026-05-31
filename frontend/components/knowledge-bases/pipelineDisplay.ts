import type { PipelineStepIconStatus } from "../icons";
import type { EvidencePackage } from "./ingestionTypes";
import type { DatabaseImport, SourceCleaningStat } from "./types";

/** 数据源导入：主标题用数据库名，副标题用连接器名称。 */
export function databaseImportDisplayTitle(
  imp: Pick<DatabaseImport, "datasource_name" | "database_names">,
): string {
  const names = (imp.database_names ?? []).map((n) => n.trim()).filter(Boolean);
  if (names.length > 0) return names.join(", ");
  return imp.datasource_name?.trim() || "数据库导入";
}

export function databaseImportDisplaySubtitle(
  imp: Pick<DatabaseImport, "datasource_name" | "database_names">,
): string {
  const ds = imp.datasource_name?.trim();
  if (!ds) return "";
  const count = imp.database_names?.length ?? 0;
  if (count <= 1) return ds;
  return `${ds} · ${count} 个数据库`;
}

/** 与导入登记一致的完整标题（证据包等场景）。 */
export function databaseImportFullTitle(
  imp: Pick<DatabaseImport, "datasource_name" | "database_names">,
): string {
  const ds = imp.datasource_name?.trim() || "数据库导入";
  const names = (imp.database_names ?? []).map((n) => n.trim()).filter(Boolean);
  if (names.length === 0) return ds;
  return `${ds} / ${names.join(", ")}`;
}

export function isPhysicalSchemaPackage(pkg: EvidencePackage): boolean {
  return pkg.connector === "database" || pkg.asset_kind === "physical_schema";
}

export function mapRawStepStatus(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && "status" in raw) {
    const v = (raw as { status?: unknown }).status;
    return typeof v === "string" ? v : "pending";
  }
  return "pending";
}

export function stepIconForStatus(status: string): PipelineStepIconStatus {
  if (status === "done" || status === "completed") return "ok";
  if (status === "failed") return "fail";
  if (status === "running") return "running";
  return "pending";
}

/** 数据库导入流水线仅同步 physical_schema，不含 LLM 语义抽取步骤。 */
export function isDatabaseSchemaSyncPipeline(
  steps: SourceCleaningStat["steps"] | null | undefined,
): boolean {
  if (!steps || typeof steps !== "object") return false;
  const pipelineMeta = steps._pipeline;
  if (
    pipelineMeta &&
    typeof pipelineMeta === "object" &&
    "pipeline_kind" in pipelineMeta &&
    (pipelineMeta as { pipeline_kind?: unknown }).pipeline_kind === "database_schema_sync"
  ) {
    return true;
  }
  const keys = Object.keys(steps).filter((k) => !k.startsWith("_"));
  return keys.every((k) => k === "physical_schema");
}

const SCHEMA_FAILURE_LABELS: Record<string, string> = {
  no_analyzed_tables: "导入库中的表尚未完成 AI 分析",
  no_tables_found: "未找到导入数据源中的表",
  database_import_not_found: "数据库导入记录不存在",
};

function schemaStepFailureReason(raw: unknown): string | undefined {
  const status = mapRawStepStatus(raw);
  if (status !== "failed" && status !== "skipped") return undefined;
  if (raw && typeof raw === "object" && "reason" in raw) {
    const reason = (raw as { reason?: unknown }).reason;
    if (typeof reason === "string" && reason.trim()) {
      return SCHEMA_FAILURE_LABELS[reason.trim()] ?? reason.trim();
    }
  }
  return status === "skipped" ? "已跳过" : "语义清洗失败";
}

/** 物理 Schema 证据包：索引之后的步骤（语义清洗 + 入图）。 */
export function databaseSchemaStepsForPackage(
  sourceStat: SourceCleaningStat | undefined,
): { label: string; icon: PipelineStepIconStatus; reason?: string }[] {
  const rawSchema = sourceStat?.steps?.physical_schema;
  const schemaStatus = mapRawStepStatus(rawSchema);

  const schemaIcon = (): PipelineStepIconStatus => {
    if (sourceStat?.status === "running") {
      if (schemaStatus === "running") return "running";
      if (schemaStatus === "done" || schemaStatus === "completed") return "ok";
      return "pending";
    }
    if (sourceStat?.status === "completed") {
      return stepIconForStatus(schemaStatus === "pending" ? "done" : schemaStatus);
    }
    if (sourceStat?.status === "failed") {
      if (schemaStatus === "failed" || schemaStatus === "skipped") return "fail";
      return "pending";
    }
    return "pending";
  };

  const schema = schemaIcon();
  const writeIcon: PipelineStepIconStatus =
    sourceStat?.status === "completed" && schema === "ok"
      ? "ok"
      : sourceStat?.status === "failed" && schema === "fail"
        ? "fail"
        : "pending";

  const schemaReason = schema === "fail" ? schemaStepFailureReason(rawSchema) : undefined;
  const writeReason =
    writeIcon === "fail"
      ? (sourceStat?.message || sourceStat?.failure_reason || schemaReason)
      : undefined;

  return [
    { label: "语义清洗", icon: schema, reason: schemaReason },
    { label: "入图", icon: writeIcon, reason: writeReason },
  ];
}

export type DatabaseCleaningStatusTone = "running" | "success" | "error" | "muted";

export function databaseCleaningStatusText(
  cleaningStat: SourceCleaningStat | undefined,
  isCleaning: boolean,
): { text: string; tone: DatabaseCleaningStatusTone; failureReason?: string | null } {
  if (isCleaning || cleaningStat?.status === "running") {
    return { text: "清洗中…", tone: "running" };
  }
  if (cleaningStat?.status === "completed") {
    return { text: "清洗完毕", tone: "success" };
  }
  if (cleaningStat?.status === "failed") {
    const raw = (cleaningStat.message || cleaningStat.failure_reason || "").trim();
    const failureReason =
      raw && !["failed", "skipped", "completed", "running", "pending"].includes(raw.toLowerCase())
        ? raw
        : schemaStepFailureReason(cleaningStat.steps?.physical_schema) ?? "语义清洗失败";
    return { text: "清洗失败", tone: "error", failureReason };
  }
  return { text: "未清洗", tone: "muted" };
}

export function databaseSemanticCleanButtonLabel(isCleaning: boolean): string {
  return isCleaning ? "清洗中…" : "语义清洗";
}
