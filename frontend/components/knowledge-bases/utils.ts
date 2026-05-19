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
  const lastSteps = (lastRun?.steps ?? {}) as Record<string, { status?: string; count?: number }>;
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

  // Step 2: 术语提取
  const termStep = lastSteps["term_extraction"];
  const termCount = stats.term_count;
  const termDone = typeof termStep?.count === "number" ? termStep.count : termCount;
  const termStatus: "done" | "progress" | "waiting" | "skipped" =
    termStep?.status === "done" ? "done" :
    termStep?.status === "failed" ? "done" :
    !lastRun ? "waiting" :
    lastRun.status === "running" ? (termStep ? "progress" : "waiting") :
    lastRun.status === "completed" ? "done" : "waiting";

  steps.push({
    id: "term-extraction",
    label: "术语提取",
    description: termStatus === "done" ? `${termDone} 个术语已识别` : "AI 识别业务术语（GMV、留存率等）",
    status: termStatus,
    isExclusive: false,
    totalCount: termStatus === "done" ? termDone : undefined,
    doneCount: termStatus === "done" ? termDone : undefined,
  });

  // Step 3: 指标口径
  const metricStep = lastSteps["metric_caliber"];
  const metricCount = stats.metric_count;
  const metricDone = typeof metricStep?.count === "number" ? metricStep.count : metricCount;
  const metricStatus: "done" | "progress" | "waiting" | "skipped" =
    metricStep?.status === "done" ? "done" :
    metricStep?.status === "failed" ? "done" :
    !lastRun ? "waiting" :
    lastRun.status === "running" ? (metricStep ? "progress" : "waiting") :
    lastRun.status === "completed" ? "done" : "waiting";

  steps.push({
    id: "metric-caliber",
    label: "指标口径",
    description: metricStatus === "done" ? `${metricDone} 个指标已定义` : "AI 提取计算公式与统计口径",
    status: metricStatus,
    isExclusive: false,
    totalCount: metricStatus === "done" ? metricDone : undefined,
    doneCount: metricStatus === "done" ? metricDone : undefined,
  });

  // Step 4: 数据血缘
  const lineageStep = lastSteps["data_lineage"];
  const lineageDone = stats.lineage_stats?.done ?? 0;
  const lineageSkipped = lineageStep?.status === "skipped";
  const lineageStatus: "done" | "progress" | "waiting" | "skipped" = hasGitSource
    ? (lineageDone > 0 ? "done" :
       lineageStep?.status === "done" ? "done" :
       lineageSkipped ? "skipped" :
       !lastRun ? "waiting" :
       lastRun.status === "running" ? (lineageStep ? "progress" : "waiting") :
       lastRun.status === "completed" ? (lineageStep ? "done" : "skipped") : "waiting")
    : "skipped";

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

  return steps;
}
