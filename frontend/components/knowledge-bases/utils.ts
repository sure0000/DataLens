import type {
  BusinessTerm,
  DocRow,
  DocStatus,
  GitSource,
  MetricDef,
  OutputCardData,
  PipelineStats,
} from "./types";

/** 分支标签 */
export function gitBranchLabel(s: GitSource): string {
  const b = s.branch != null ? String(s.branch) : "";
  if (s.uses_default_branch || !b.trim()) return "默认分支";
  return b;
}

/** 文本截断 */
export function snippetText(raw: unknown, maxLen: number): string {
  const t = typeof raw === "string" ? raw : raw != null ? String(raw) : "";
  const s = t.trim();
  if (!s) return "";
  if (s.length <= maxLen) return s;
  return `${s.slice(0, maxLen)}…`;
}

/** Git 同步状态 chip */
export function gitSyncStatusChip(
  status: string | null | undefined
): { text: string; className: string } {
  const raw = (status || "").trim();
  const s = raw.toLowerCase();
  if (s === "success") {
    return { text: "成功", className: "border-emerald-200 bg-emerald-50 text-emerald-800" };
  }
  if (s === "error") {
    return { text: "失败", className: "border-rose-200 bg-rose-50 text-rose-800" };
  }
  if (raw) {
    return { text: raw, className: "border-app-border bg-white text-app-secondary" };
  }
  return { text: "尚未同步", className: "border-app-border bg-app-hover text-app-muted" };
}

/** 文档状态 chip */
export function docStatusChip(
  status: DocStatus
): { text: string; className: string } {
  const map: Record<DocStatus, { text: string; className: string }> = {
    pending: {
      text: "等待中",
      className: "border-app-border bg-app-hover text-app-muted",
    },
    extracting: {
      text: "提取中",
      className: "border-blue-200 bg-blue-50 text-blue-700",
    },
    cleaning: {
      text: "清洗中",
      className: "border-blue-200 bg-blue-50 text-blue-700",
    },
    chunking: {
      text: "分块中",
      className: "border-blue-200 bg-blue-50 text-blue-700",
    },
    embedding: {
      text: "向量化中",
      className: "border-indigo-200 bg-indigo-50 text-indigo-700",
    },
    indexed: {
      text: "已索引",
      className: "border-emerald-200 bg-emerald-50 text-emerald-800",
    },
    failed: {
      text: "失败",
      className: "border-rose-200 bg-rose-50 text-rose-800",
    },
  };
  return (
    map[status] ?? {
      text: status,
      className: "border-app-border bg-white text-app-secondary",
    }
  );
}

/** 从聚合统计构建产出摘要卡片 */
export function computeOutputCards(
  stats: PipelineStats | null,
  terms: BusinessTerm[],
  metrics: MetricDef[]
): OutputCardData[] {
  const cards: OutputCardData[] = [];

  const approvedTerms = terms.filter((t) => t.status === "approved");
  if (stats && stats.term_count > 0) {
    cards.push({
      id: "terms",
      label: `术语 (${stats.term_count})`,
      icon: "terms",
      previews: approvedTerms.slice(0, 3).map((t) => ({
        text: t.name,
        subtext: t.type,
        confidence: t.confidence,
      })),
      totalCount: stats.term_count,
    });
  }

  const approvedMetrics = metrics.filter((m) => m.status === "approved");
  if (stats && stats.metric_count > 0) {
    cards.push({
      id: "metrics",
      label: `指标 (${stats.metric_count})`,
      icon: "metrics",
      previews: approvedMetrics.slice(0, 3).map((m) => ({
        text: m.name,
        confidence: m.confidence,
      })),
      totalCount: stats.metric_count,
    });
  }

  return cards;
}

/** 根据知识库来源计算支持的流水线步骤 */
export function computePipelineSteps(
  stats: PipelineStats | null,
  hasGitSource: boolean
): {
  id: string;
  label: string;
  description: string;
  status: "done" | "progress" | "waiting";
  isExclusive: boolean;
  totalCount?: number;
  doneCount?: number;
}[] {
  if (!stats) return [];

  const steps = [];

  // 术语提取
  const termDone = stats.terms_by_status?.["approved"] ?? 0;
  const termTotal = stats.term_count;
  steps.push({
    id: "term_extraction",
    label: "术语提取",
    description: "从文档中提取业务术语",
    status: (termTotal > 0 ? "done" : stats.total_documents > 0 ? "progress" : "waiting") as "done" | "progress" | "waiting",
    isExclusive: false,
    totalCount: termTotal,
    doneCount: termDone,
  });

  // 指标口径
  const metricDone = stats.metrics_by_status?.["approved"] ?? 0;
  const metricTotal = stats.metric_count;
  steps.push({
    id: "metric_caliber",
    label: "指标口径",
    description: "从文档中提取指标计算口径",
    status: (metricTotal > 0 ? "done" : stats.indexed_documents > 0 ? "progress" : "waiting") as "done" | "progress" | "waiting",
    isExclusive: false,
    totalCount: metricTotal,
    doneCount: metricDone,
  });

  // 表理解（仅 Git 源 / 数据库源）
  if (hasGitSource) {
    const indexed = stats.documents_by_status?.["indexed"] ?? 0;
    steps.push({
      id: "table_understanding",
      label: "表理解",
      description: "解析代码中的表结构和字段语义",
      status: (indexed > 0 ? "done" : "waiting") as "done" | "progress" | "waiting",
      isExclusive: false,
      totalCount: indexed,
      doneCount: indexed,
    });

    // 数据血缘（仅代码库）
    const lineageDone = stats.lineage_stats?.done ?? 0;
    const lineageTotal =
      (stats.lineage_stats?.done ?? 0) +
      (stats.lineage_stats?.processing ?? 0) +
      (stats.lineage_stats?.pending ?? 0);
    steps.push({
      id: "data_lineage",
      label: "数据血缘",
      description: "从代码中解析表间依赖关系（代码库专属）",
      status: (lineageDone > 0 ? "done" : lineageTotal > 0 ? "progress" : "waiting") as "done" | "progress" | "waiting",
      isExclusive: true,
      totalCount: lineageTotal,
      doneCount: lineageDone,
    });
  }

  // 文档流水线状态
  const indexedDocs = stats.documents_by_status?.["indexed"] ?? 0;
  const totalDocs = stats.total_documents;
  if (totalDocs > 0) {
    steps.push({
      id: "document_processing",
      label: "文档处理",
      description: "文档清洗、分块、向量化",
      status: (indexedDocs >= totalDocs ? "done" : "progress") as "done" | "progress" | "waiting",
      isExclusive: false,
      totalCount: totalDocs,
      doneCount: indexedDocs,
    });
  }

  return steps;
}
