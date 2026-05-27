import {
  chipError,
  chipInfo,
  chipNeutral,
  chipProgress,
  chipSuccess,
} from "../../lib/themeClasses";
import type {
  BusinessTerm,
  DocRow,
  DocStatus,
  GitSource,
  LineageData,
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
    return { text: "成功", className: chipSuccess };
  }
  if (s === "error") {
    return { text: "失败", className: chipError };
  }
  if (raw) {
    return { text: raw, className: `${chipNeutral} text-app-secondary` };
  }
  return { text: "尚未同步", className: `${chipNeutral} text-app-muted` };
}

/** 文档状态 chip */
export function docStatusChip(
  status: DocStatus
): { text: string; className: string } {
  const map: Record<DocStatus, { text: string; className: string }> = {
    pending: {
      text: "等待中",
      className: `${chipNeutral} text-app-muted`,
    },
    extracting: {
      text: "提取中",
      className: chipProgress,
    },
    cleaning: {
      text: "清洗中",
      className: chipProgress,
    },
    chunking: {
      text: "分块中",
      className: chipProgress,
    },
    embedding: {
      text: "向量化中",
      className: chipInfo,
    },
    ontology_assertion: {
      text: "结构化中",
      className: chipProgress,
    },
    indexed: {
      text: "已索引",
      className: chipSuccess,
    },
    failed: {
      text: "失败",
      className: chipError,
    },
  };
  return (
    map[status] ?? {
      text: status,
      className: `${chipNeutral} text-app-secondary`,
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

  // Ontology / RDF output
  const rdf = stats?.rdf_stats;
  if (rdf && (rdf.triple_count ?? 0) > 0) {
    cards.push({
      id: "ontology",
      label: `本体建模 (${rdf.triple_count} 三元组)`,
      icon: "ontology",
      previews: [
        ...(rdf.term_count ? [{ text: `${rdf.term_count} 个业务术语`, subtext: "术语" }] : []),
        ...(rdf.metric_count ? [{ text: `${rdf.metric_count} 个指标口径`, subtext: "指标" }] : []),
        ...(rdf.physical_table_count ? [{ text: `${rdf.physical_table_count} 张物理表`, subtext: "表结构" }] : []),
      ].slice(0, 3),
      totalCount: rdf.triple_count ?? 0,
    });
  }

  return cards;
}

/** 从血缘边列表计算状态统计 */
export function computeLineageStats(edges: { status: string }[]): {
  done: number;
  processing: number;
  pending: number;
} {
  return {
    done: edges.filter((e) => e.status === "done").length,
    processing: edges.filter((e) => e.status === "processing").length,
    pending: edges.filter((e) => e.status === "pending").length,
  };
}

/** 按 Git 源过滤血缘图，并重算 layers / stats */
export function filterLineageByGitSource(lineage: LineageData, gitSourceId: number): LineageData {
  const edges = lineage.edges.filter((e) => e.git_source_id === gitSourceId);
  const tableNames = new Set<string>();
  for (const e of edges) {
    tableNames.add(e.source_table);
    tableNames.add(e.target_table);
  }
  const layers = lineage.layers
    .map((layer) => ({
      ...layer,
      nodes: layer.nodes.filter((n) => tableNames.has(n.name)),
    }))
    .filter((layer) => layer.nodes.length > 0);
  return { layers, edges, stats: computeLineageStats(edges) };
}

type PipelineStepStatus = "done" | "progress" | "waiting" | "skipped";

function resolveSemanticStepStatus(
  step: { status?: string } | undefined,
  count: number,
  lastRun: PipelineStats["last_pipeline_run"],
): PipelineStepStatus {
  if (count > 0) return "done";
  if (step?.status === "done" || step?.status === "failed") return "done";
  if (!lastRun) return "waiting";
  if (lastRun.status === "running") return step ? "progress" : "waiting";
  if (lastRun.status === "completed" || lastRun.status === "failed") return "done";
  return "waiting";
}

/** 根据知识库来源计算支持的流水线步骤 */
export function computePipelineSteps(
  stats: PipelineStats | null,
  hasGitSource: boolean,
): {
  id: string;
  label: string;
  description: string;
  status: "done" | "progress" | "waiting" | "skipped";
  isExclusive: boolean;
  totalCount?: number;
  doneCount?: number;
}[] {
  if (!stats) return [];

  const lastRun = stats.last_pipeline_run;
  const lastSteps = (lastRun?.steps ?? {}) as Record<
    string,
    { status?: string; count?: number; written?: number }
  >;
  const steps: {
    id: string;
    label: string;
    description: string;
    status: "done" | "progress" | "waiting" | "skipped";
    isExclusive: boolean;
    totalCount?: number;
    doneCount?: number;
  }[] = [];

  // Step 1: 文档清洗 — always shown
  const docTotal = stats.total_documents;
  const docDone = stats.indexed_documents;
  const docFailed = stats.documents_by_status?.["failed"] ?? 0;
  const docPending = stats.documents_by_status?.["pending"] ?? 0;

  let docStatus: "done" | "progress" | "waiting" | "skipped" = "waiting";
  if (docTotal > 0) {
    if (docDone >= docTotal) docStatus = "done";
    else if (docPending > 0 || docTotal - docDone - docFailed - docPending > 0) docStatus = "progress";
    else if (docFailed > 0) docStatus = "done";
    else docStatus = "progress";
  }

  steps.push({
    id: "doc-cleaning",
    label: "文档清洗",
    description: docTotal === 0 ? "导入文件或 API 数据后自动开始" : `${docDone} / ${docTotal} 篇文档已索引`,
    status: docTotal === 0 ? "waiting" : docStatus,
    isExclusive: false,
    totalCount: docTotal,
    doneCount: docDone,
  });

  // Step 2: 术语提取 — 计数始终使用 stats（源详情页会传入过滤后的计数）
  const termStep = lastSteps["term_extraction"];
  const termCount = stats.term_count;
  const termStatus = resolveSemanticStepStatus(termStep, termCount, lastRun);

  steps.push({
    id: "term-extraction",
    label: "术语提取",
    description: termStatus === "done" ? `${termCount} 个术语已识别` : "AI 识别业务术语（GMV、留存率等）",
    status: termStatus,
    isExclusive: false,
    totalCount: termStatus === "done" ? termCount : undefined,
    doneCount: termStatus === "done" ? termCount : undefined,
  });

  // Step 3: 指标口径
  const metricStep = lastSteps["metric_caliber"];
  const metricCount = stats.metric_count;
  const metricStatus = resolveSemanticStepStatus(metricStep, metricCount, lastRun);

  steps.push({
    id: "metric-caliber",
    label: "指标口径",
    description: metricStatus === "done" ? `${metricCount} 个指标已定义` : "AI 提取计算公式与统计口径",
    status: metricStatus,
    isExclusive: false,
    totalCount: metricStatus === "done" ? metricCount : undefined,
    doneCount: metricStatus === "done" ? metricCount : undefined,
  });

  // Step 4: 数据血缘
  const lineageStep = lastSteps["data_lineage"];
  const lineageDone = stats.lineage_stats?.done ?? 0;
  const lineageTotal =
    lineageDone +
    (stats.lineage_stats?.processing ?? 0) +
    (stats.lineage_stats?.pending ?? 0);
  const lineageSkipped = lineageStep?.status === "skipped";
  const lineageStatus: PipelineStepStatus = !hasGitSource
    ? "skipped"
    : lineageDone > 0
    ? "done"
    : lineageStep?.status === "done"
    ? "done"
    : lineageSkipped
    ? "skipped"
    : !lastRun
    ? "waiting"
    : lastRun.status === "running"
    ? lineageStep
      ? "progress"
      : "waiting"
    : lastRun.status === "completed" || lastRun.status === "failed"
    ? lineageTotal > 0 || lineageStep
      ? "done"
      : "skipped"
    : "waiting";

  steps.push({
    id: "data-lineage",
    label: "数据血缘",
    description: lineageStatus === "done" ? `${lineageDone} 条依赖关系` :
      lineageStatus === "skipped" ? (hasGitSource ? "未检测到表间依赖" : "仅代码源支持") :
      "AI 分析表间依赖与数据流",
    status: lineageStatus,
    isExclusive: false,
    totalCount: lineageStatus === "done" ? lineageDone : undefined,
    doneCount: lineageStatus === "done" ? lineageDone : undefined,
  });

  // Step 5: 本体建模 — 同步术语/指标/血缘到 Fuseki RDF
  const ontologyStep = lastSteps["ontology_modeling"];
  const rdfTriples = stats.rdf_stats?.triple_count ?? 0;
  const ontologyWritten = typeof ontologyStep?.count === "number" ? ontologyStep.count : ontologyStep?.written;
  let ontologyStatus: PipelineStepStatus = "waiting";
  if (ontologyStep?.status === "skipped") {
    ontologyStatus = "skipped";
  } else if (ontologyStep?.status === "failed") {
    ontologyStatus = "done";
  } else if (rdfTriples > 0 || ontologyStep?.status === "done") {
    ontologyStatus = "done";
  } else if (lastRun?.status === "running" && ontologyStep) {
    ontologyStatus = "progress";
  } else if (lastRun?.status === "completed" || lastRun?.status === "failed") {
    ontologyStatus = ontologyStep ? "done" : "waiting";
  }

  const ontologyDesc =
    ontologyStatus === "done" && rdfTriples > 0
      ? `${rdfTriples} 条 RDF 三元组 · ${stats.rdf_stats?.storage_backend || "Fuseki"}`
      : ontologyStatus === "skipped"
        ? "本体层未启用"
        : ontologyStatus === "progress"
          ? "正在写入 Fuseki…"
          : "将术语、指标与表结构同步到 RDF 图数据库";

  steps.push({
    id: "ontology-modeling",
    label: "本体建模",
    description: ontologyDesc,
    status: ontologyStatus,
    isExclusive: false,
    totalCount: ontologyStatus === "done" && rdfTriples > 0 ? rdfTriples : undefined,
    doneCount:
      ontologyStatus === "done" && typeof ontologyWritten === "number"
        ? ontologyWritten
        : ontologyStatus === "done" && rdfTriples > 0
          ? rdfTriples
          : undefined,
  });

  return steps;
}
