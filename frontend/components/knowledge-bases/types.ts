/** 与后端 GET /api/knowledge-bases 响应对齐 */
export type KB = {
  id: number;
  name: string;
  description: string;
  created_at: string;
};

/** 与后端知识条目响应对齐 */
export type Entry = {
  id: number;
  knowledge_base_id: number;
  title: string;
  summary?: string;
  body: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
  source_url?: string | null;
  source_meta?: Record<string, string>;
  tags?: string[];
};

/** 与后端 Git 源响应对齐 */
export type GitSource = {
  id: number;
  knowledge_base_id: number;
  name: string;
  provider: string;
  api_base?: string | null;
  owner: string;
  repo: string;
  branch: string;
  uses_default_branch?: boolean;
  path_prefix: string;
  has_token: boolean;
  token?: string;
  include_globs: string;
  max_file_kb: number;
  max_files: number;
  cron_expression?: string | null;
  enabled: boolean;
  tags?: string[];
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

/** 与后端 API 源响应对齐 */
export type ApiSource = {
  id: number;
  knowledge_base_id: number | null;
  name: string;
  integration: string;
  object_id: string;
  extra: Record<string, string>;
  has_key: boolean;
  enabled: boolean;
  tags?: string[];
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

/** 检索命中结果 */
export type Hit = {
  entry_id: number;
  title: string;
  summary?: string;
  snippet: string;
  rrf_score?: number;
  vector_rank?: number;
  bm25_rank?: number;
};

/** 文档处理状态 */
export type DocStatus =
  | "pending"
  | "extracting"
  | "cleaning"
  | "chunking"
  | "embedding"
  | "indexed"
  | "failed";

/** 与后端 GET .../documents 响应对齐 */
export type DocRow = {
  id: number;
  title: string;
  source_type: string;
  source_meta: Record<string, string>;
  char_count: number | null;
  status: DocStatus;
  error_message: string | null;
  stage_timings: Record<string, number>;
  knowledge_entry_id: number | null;
  created_at: string;
  updated_at: string;
};

/** 分块 */
export type ChunkRow = {
  id: number;
  chunk_index: number;
  content: string;
  quality_score: number | null;
  char_start: number | null;
  char_end: number | null;
};

// ── V2 语义层类型 ──────────────────────────────────────────────

/** 业务术语 */
export type BusinessTerm = {
  id: number;
  knowledge_base_id: number;
  name: string;
  type: "metric" | "enum" | "time" | "dimension" | "other";
  definition: string;
  source_entry_id: number | null;
  related_fields: string[];
  confidence: number;
  status: "pending_review" | "approved" | "rejected";
  created_at: string | null;
  updated_at: string | null;
};

/** 指标口径 */
export type MetricDef = {
  id: number;
  knowledge_base_id: number;
  name: string;
  formula: string;
  caliber: string | null;
  source_entry_id: number | null;
  related_terms: string[];
  confidence: number;
  status: "pending_review" | "approved" | "rejected";
  created_at: string | null;
  updated_at: string | null;
};

/** 血缘边 */
export type LineageEdge = {
  id: number;
  knowledge_base_id: number;
  git_source_id: number | null;
  source_table: string;
  target_table: string;
  source_field: string | null;
  target_field: string | null;
  layer: string;
  transform_logic: string | null;
  status: "done" | "processing" | "pending";
  created_at: string | null;
  updated_at: string | null;
};

/** 血缘图层 */
export type LineageLayer = {
  name: string;
  nodes: { id: string; name: string; layer: string; status: string }[];
};

/** 血缘图数据 */
export type LineageData = {
  layers: LineageLayer[];
  edges: LineageEdge[];
  stats: { done: number; processing: number; pending: number };
};

/** 流水线步骤状态 */
export type PipelineStepStatus = "done" | "progress" | "waiting" | "skipped";

/** 单个流水线步骤 */
export interface PipelineStepData {
  id: string;
  label: string;
  description: string;
  status: PipelineStepStatus;
  isExclusive: boolean;
  totalCount?: number;
  doneCount?: number;
  previews: { status: "ok" | "warn" | "wait"; text: string }[];
}

/** 聚合统计 */
export interface PipelineStats {
  term_count: number;
  metric_count: number;
  terms_by_status: Record<string, number>;
  metrics_by_status: Record<string, number>;
  documents_by_status: Record<string, number>;
  total_documents: number;
  indexed_documents: number;
  git_sources: {
    id: number;
    name: string;
    provider: string;
    last_sync_status: string | null;
    last_sync_at: string | null;
    tags: string[];
  }[];
  lineage_stats: { done: number; processing: number; pending: number };
  rdf_stats?: {
    triple_count?: number;
    term_count?: number;
    metric_count?: number;
    physical_table_count?: number;
    quarantine_count?: number;
    storage_backend?: string;
    fuseki_live?: boolean;
  } | null;
  last_pipeline_run: {
    id: number;
    status: string;
    steps: Record<string, { status?: string; count?: number; written?: number }> | null;
    started_at: string | null;
    completed_at: string | null;
  } | null;
}

/** 产出摘要卡片 */
export interface OutputCardData {
  id: string;
  label: string;
  icon: string;
  previews: { text: string; subtext?: string; confidence?: number }[];
  totalCount: number;
}
