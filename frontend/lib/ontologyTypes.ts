/** 本体建模模块共享类型 */

export type KnowledgeBaseOption = {
  id: number;
  name: string;
  description: string;
  created_at: string;
};

export type OntologyEntityOrigin = {
  knowledge_base_id: number;
  knowledge_base_name: string;
  source_label?: string;
  source_type?: string;
  evidence_package_display_id?: string;
};

export type OntologyTerm = {
  id: number;
  iri?: string;
  name: string;
  type: string;
  definition: string;
  synonyms?: string[];
  related_fields: string[];
  concept_id: string | null;
  confidence: number;
  status: string;
  origin?: OntologyEntityOrigin;
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
  origin?: OntologyEntityOrigin;
};

export type OntologyDimension = {
  id: number;
  iri?: string;
  name: string;
  definition: string;
  dim_type: string;
  confidence: number;
  status: string;
  origin?: OntologyEntityOrigin;
};

export type OntologyRule = {
  id: number;
  iri?: string;
  name: string;
  rule_expression: string;
  rule_type: string;
  confidence: number;
  status: string;
  origin?: OntologyEntityOrigin;
};

export type GraphNode = {
  id: string;
  type: string;
  label: string;
  status?: string;
  knowledge_base_id?: number;
  knowledge_base_name?: string;
};
export type GraphEdge = {
  id: string;
  type: string;
  source: string;
  target: string;
  knowledge_base_id?: number;
};

export type DomainKbOntologySummary = {
  knowledge_base_id: number;
  knowledge_base_name: string;
  term_count: number;
  metric_count: number;
  physical_table_count: number;
  relation_edge_count: number;
  triple_count: number;
  quarantine_count: number;
  shacl_pass_rate?: number | null;
  pipeline_status?: string | null;
  last_cleaning_at?: string | null;
};

export type DomainOntologyOverview = {
  ok: boolean;
  domain_id: number;
  domain_name: string;
  knowledge_base_count: number;
  knowledge_bases: DomainKbOntologySummary[];
  totals: {
    term_count: number;
    metric_count: number;
    physical_table_count: number;
    relation_edge_count: number;
    triple_count: number;
    quarantine_count: number;
  };
};

export type DomainPhysicalTable = {
  iri: string;
  platform_id: string;
  summary: string;
  origin: OntologyEntityOrigin;
};

export type DomainOntologyLayerSummary = {
  label: string;
  description: string;
  total: number;
  ontology_class: string;
  criteria?: Record<string, string | number | boolean | string[]>;
};

export type DomainOntologyLayersSummary = {
  ok: boolean;
  domain_id: number;
  knowledge_base_count: number;
  layers: Record<string, DomainOntologyLayerSummary>;
};

export type DomainLayerItem = Record<string, string> & {
  origin?: OntologyEntityOrigin;
};

export type DomainOntologyLayerDetail = {
  ok: boolean;
  domain_id: number;
  layer_key: string;
  label: string;
  description: string;
  ontology_class: string;
  criteria?: Record<string, string | number | boolean | string[]>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  items: DomainLayerItem[];
};

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

export type OntologyTab = "overview" | "semantics" | "assets" | "graph";

export type RdfEntity = {
  iri: string;
  label: string;
  definition?: string;
  formula?: string;
  status?: string;
  synonyms?: string[];
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

/** 本体实体类型的可读标签（用于 entityType 列展示） */
export const ENTITY_TYPE_LABELS: Record<string, string> = {
  "dl:BusinessTerm": "业务术语",
  "dl:Metric": "度量指标",
  "dl:Dimension": "分析维度",
  "dl:BusinessConcept": "业务概念",
  "dl:BusinessRule": "业务规则",
};

/** 关系谓词的可读标签（用于关系层 p 列展示） */
export const PREDICATE_LABELS: Record<string, string> = {
  "dl:dependsOn": "依赖于",
  "dl:derivedFrom": "派生自",
  "dl:relatedTo": "关联于",
  "dl:joinableWith": "可关联",
  "dl:transformsFrom": "转换自",
  "dl:computedFromTable": "计算自表",
  "skos:related": "相关",
  "skos:broader": "上位概念",
  "skos:narrower": "下位概念",
};

/** 常见属性谓词的可读标签（用于属性层 p 列展示） */
export const ATTRIBUTE_PREDICATE_LABELS: Record<string, string> = {
  "dl:businessSummary": "业务描述",
  "dl:semanticDescription": "语义说明",
  "dl:sampleValue": "样例值",
  "dl:confidence": "置信度",
  "dl:approvalStatus": "审核状态",
  "dl:formula": "计算公式",
  "dl:caliber": "口径说明",
  "dl:ruleExpression": "规则表达式",
  "dl:ruleType": "规则类型",
  "dl:dimensionType": "维度类型",
  "rdf:type": "类型",
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
