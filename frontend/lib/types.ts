/** 跨页面共享的类型别名与字面量联合。 */

/** Toast / 通知消息色调 */
export type ToastTone = "success" | "error" | "info";

/** 知识条目来源类型 */
export type SourceType = "file" | "git" | "notion" | "confluence" | "feishu" | "manual";

/** 语义角色分类 */
export type SemanticRole =
  | "table_overview"
  | "column_glossary"
  | "business_metric"
  | "query_pattern"
  | "join_guide"
  | "data_quality"
  | "general_reference";

/** 流水线状态 */
export type PipelineStatus = "pending" | "extracting" | "cleaning" | "chunking" | "embedding" | "indexed" | "failed";

/** 审核状态 */
export type ReviewStatus = "pending_review" | "approved" | "rejected";

/** 血缘状态 */
export type LineageStatus = "done" | "processing" | "pending";

/** Git 提供商 */
export type GitProvider = "github" | "gitlab";

/** API 集成平台 */
export type ApiIntegrationType = "notion" | "confluence" | "feishu";
