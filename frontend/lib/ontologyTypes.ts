/** 本体建模模块共享类型 */

export type KnowledgeBaseOption = {
  id: number;
  name: string;
  description: string;
  created_at: string;
};

export type OntologyTerm = {
  id: number;
  iri?: string;
  name: string;
  type: string;
  definition: string;
  related_fields: string[];
  concept_id: string | null;
  confidence: number;
  status: string;
};

export type OntologyMetric = {
  id: number;
  iri?: string;
  name: string;
  formula: string;
  caliber: string | null;
  bound_table_refs: string[];
  concept_id: string | null;
  confidence: number;
  status: string;
};

export type OntologyDimension = {
  id: number;
  iri?: string;
  name: string;
  definition: string;
  dim_type: string;
  confidence: number;
  status: string;
};

export type OntologyRule = {
  id: number;
  iri?: string;
  name: string;
  rule_expression: string;
  rule_type: string;
  confidence: number;
  status: string;
};

export type GraphNode = { id: string; type: string; label: string; status?: string };
export type GraphEdge = { id: string; type: string; source: string; target: string };

export type OntologyStoreInfo = {
  triple_count?: number;
  storage_backend?: string;
  local_store_path?: string;
  tbox_loaded?: boolean;
  fuseki_enabled?: boolean;
  fuseki_live?: boolean;
};

export type SyncResult = {
  ok: boolean;
  written?: number;
  candidates?: number;
  quarantined?: number;
  shacl_blocked?: boolean;
  stats?: {
    input?: number;
    production?: number;
    quarantine_tbox?: number;
  };
};

export type OntologyTab = "overview" | "semantics" | "assets" | "graph" | "expert";

export type RdfEntity = {
  iri: string;
  label: string;
  definition?: string;
  formula?: string;
  status?: string;
};

export type RdfPhysicalTable = {
  iri: string;
  platform_id: string;
  summary: string;
};

export type KbRdfView = {
  graph_iri: string;
  quarantine_graph_iri: string;
  production: {
    triple_count: number;
    term_count: number;
    metric_count: number;
    physical_table_count: number;
    terms: RdfEntity[];
    metrics: RdfEntity[];
    physical_tables: RdfPhysicalTable[];
  };
  quarantine: {
    triple_count: number;
    assertion_count: number;
  };
};

export const TERM_TYPE_LABELS: Record<string, string> = {
  metric: "度量",
  enum: "枚举",
  time: "时间",
  dimension: "维度",
  other: "其他",
};

export type OntologyProvenance = {
  chunks: { iri: string; content_preview?: string | null }[];
  documents: { id: number; title: string; status: string }[];
  evidence_packages: { display_id: string; title: string }[];
  has_provenance?: boolean;
};

export const STATUS_LABELS: Record<string, { label: string; tone: "success" | "warn" | "muted" | "danger" }> = {
  approved: { label: "已发布", tone: "success" },
  linked: { label: "已关联", tone: "warn" },
  shacl_passed: { label: "SHACL 通过", tone: "warn" },
  pending_review: { label: "待审核", tone: "warn" },
  draft: { label: "草稿", tone: "muted" },
  rejected: { label: "已拒绝", tone: "danger" },
};

export const RELATION_TYPE_LABELS: Record<string, string> = {
  term_column: "术语 → 字段",
  metric_table: "指标 → 表",
  table_join: "表关联",
  concept_alias: "概念别名",
  lineage: "数据血缘",
};

export const ONTOLOGY_KB_STORAGE_KEY = "ontology_selected_kb_id";
