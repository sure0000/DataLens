/** 导入层 — 证据包与语义资产类型（对齐 本体三层架构与UI优化.md） */

export type AssetKind =
  | "semantic_doc"
  | "physical_schema"
  | "processing_code"
  | "relation_lineage"
  | "governance"
  | "ttl_bundle";

export type ConnectorKind = "file" | "api" | "git" | "database" | "manual" | "ttl";

export type EvidencePackage = {
  id: string;
  db_id?: number;
  persistent?: boolean;
  kb_id: number;
  display_id: string;
  asset_kind: AssetKind;
  asset_label: string;
  connector: ConnectorKind;
  connector_label: string;
  title: string;
  source_ref: Record<string, unknown>;
  processing_state: string;
  linked_entry_ids?: number[];
  linked_document_id?: number;
  document_count?: number;
  indexed_document_count?: number;
  failed_document_count?: number;
  created_at?: string | null;
};

export const ASSET_KIND_OPTIONS: {
  kind: AssetKind;
  title: string;
  desc: string;
  icon: string;
}[] = [
  { kind: "semantic_doc", title: "业务语义", desc: "术语、指标、制度、Wiki、报表说明", icon: "📄" },
  { kind: "physical_schema", title: "物理 Schema", desc: "库表、列、COMMENT、数据目录", icon: "🗄" },
  { kind: "processing_code", title: "加工逻辑", desc: "SQL、dbt、ETL、ORM 定义", icon: "⚙️" },
  { kind: "relation_lineage", title: "关系血缘", desc: "JOIN、表级血缘、维度层级", icon: "🔗" },
  { kind: "governance", title: "治理上下文", desc: "业务域、组织、敏感级（多需配置）", icon: "🏢" },
  { kind: "ttl_bundle", title: "结构化本体", desc: "已整理的 TTL/RDF 包", icon: "📦" },
];

export const CONNECTORS_BY_ASSET: Record<AssetKind, ConnectorKind[]> = {
  semantic_doc: ["file", "api", "manual"],
  physical_schema: ["database"],
  processing_code: ["git"],
  relation_lineage: ["git", "file"],
  governance: ["manual"],
  ttl_bundle: ["ttl"],
};

export const ASSETS_BY_CONNECTOR: Record<ConnectorKind, AssetKind[]> = {
  file: ["semantic_doc", "relation_lineage"],
  api: ["semantic_doc"],
  git: ["processing_code", "relation_lineage"],
  database: ["physical_schema"],
  manual: ["semantic_doc", "governance"],
  ttl: ["ttl_bundle"],
};

export const CONNECTOR_LABELS: Record<ConnectorKind, string> = {
  file: "文件上传",
  api: "官方 API",
  git: "代码库同步",
  database: "数据源引用",
  manual: "手动条目",
  ttl: "TTL 文件",
};

export function defaultAssetKindsForConnector(connector: ConnectorKind): AssetKind[] {
  return ASSETS_BY_CONNECTOR[connector] ?? [];
}

export function assetKindLabelsForConnector(connector: ConnectorKind): string[] {
  const kinds = new Set(defaultAssetKindsForConnector(connector));
  return ASSET_KIND_OPTIONS.filter((a) => kinds.has(a.kind)).map((a) => a.title);
}

export const PROCESSING_STATE_LABELS: Record<string, string> = {
  registered: "已登记",
  normalized: "已规范化",
  indexed: "已索引",
  ready_for_extraction: "待抽取",
};
