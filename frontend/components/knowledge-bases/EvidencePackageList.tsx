"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../../lib/api";
import type { ModelingStatus } from "../ontology/ModelingPipelineStatus";
import type { PipelineStepIconStatus } from "../icons";
import type { EvidencePackage } from "./ingestionTypes";
import { CONNECTOR_LABELS } from "./ingestionTypes";
import {
  databaseSchemaStepsForPackage,
  isPhysicalSchemaPackage,
  mapRawStepStatus,
} from "./pipelineDisplay";
import type { DocRow, SourceCleaningStat } from "./types";
import { evidencePackageCleaningKey } from "./sourceCleaningKey";
import { indexingStepIconForPackage } from "./packageIndexStatus";

function connectorDisplayLabel(pkg: EvidencePackage): string {
  const fromApi = (pkg.connector_label || "").trim();
  const fallback = CONNECTOR_LABELS[pkg.connector as keyof typeof CONNECTOR_LABELS];
  return fromApi || fallback || pkg.connector;
}

function SourceConnectorIcon({ connector }: { connector: string }) {
  const props = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (connector === "git") {
    return (
      <span className="text-orange-500">
        <svg {...props}>
          <path d="M15 22v-4a4.8 4.8 0 00-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.47.28-1.14.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.14-.3 2.35 0 3.5A5.403 5.403 0 004 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
          <path d="M9 18c-4.51 2-5-2-7-2" />
        </svg>
      </span>
    );
  }
  if (connector === "database") {
    return (
      <span className="text-cyan-600">
        <svg {...props}>
          <ellipse cx="12" cy="6" rx="8" ry="3" />
          <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
          <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
        </svg>
      </span>
    );
  }
  if (connector === "api") {
    return (
      <span className="text-app-muted">
        <svg {...props}>
          <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
        </svg>
      </span>
    );
  }
  if (connector === "manual") {
    return (
      <span className="text-app-secondary">
        <svg {...props}>
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
      </span>
    );
  }
  if (connector === "ttl") {
    return (
      <span className="text-app-secondary">
        <svg {...props}>
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
          <line x1="12" y1="22.08" x2="12" y2="12" />
        </svg>
      </span>
    );
  }
  return (
    <span className="app-text-accent">
      <svg {...props}>
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    </span>
  );
}

function ConnectorCell({ pkg }: { pkg: EvidencePackage }) {
  const label = connectorDisplayLabel(pkg);
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-app-border bg-[var(--app-surface)]">
        <SourceConnectorIcon connector={pkg.connector} />
      </span>
      <span className="truncate text-app-primary">{label}</span>
    </div>
  );
}

function formatRegisteredAt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function extractionStepForPackage(
  pkg: EvidencePackage,
  modeling: ModelingStatus | null,
): { label: string; icon: PipelineStepIconStatus } | null {
  if (!modeling?.active_run || modeling.extraction.status !== "running") return null;
  const pkgKey = evidencePackageCleaningKey(pkg);
  if (!pkgKey) return null;
  const { source_type: runType, source_id: runId } = modeling.active_run;
  if (runId == null || !runType) return null;
  if (`${runType}:${runId}` !== pkgKey) return null;
  const runningStep = modeling.extraction.steps.find((s) => s.status === "running");
  if (runningStep) {
    const icon = (["ok", "fail", "running", "skip", "pending", "warning"].includes(runningStep.icon)
      ? runningStep.icon
      : "running") as PipelineStepIconStatus;
    return { label: runningStep.label, icon };
  }
  return { label: "执行中", icon: "running" };
}

const EXTRACTION_STEP_DEFS: { key: string; label: string }[] = [
  { key: "term_extraction", label: "术语" },
  { key: "domain_term_extraction", label: "领域" },
  { key: "metric_caliber", label: "指标" },
  { key: "dimension_extraction", label: "维度" },
  { key: "rule_extraction", label: "规则" },
  { key: "relation_extraction", label: "关系" },
  { key: "hierarchy_building", label: "层级" },
  { key: "data_lineage", label: "血缘" },
  { key: "join_extraction", label: "JOIN" },
  { key: "ontology_write", label: "入图" },
];

function progressPercentFromSourceSteps(
  steps: SourceCleaningStat["steps"],
): number | null {
  if (!steps) return null;
  let done = 0;
  for (const { key } of EXTRACTION_STEP_DEFS) {
    const status = mapRawStepStatus(steps[key]);
    if (status === "done" || status === "completed" || status === "skipped") {
      done += 1;
    }
  }
  return EXTRACTION_STEP_DEFS.length > 0
    ? Math.round((done / EXTRACTION_STEP_DEFS.length) * 100)
    : null;
}

function modelingProgressForPackage(
  pkg: EvidencePackage,
  sourceStat: SourceCleaningStat | undefined,
  modeling: ModelingStatus | null,
): number | null {
  if (sourceStat?.status === "running") {
    const fromSteps = progressPercentFromSourceSteps(sourceStat.steps);
    if (fromSteps != null) return fromSteps;
  }
  if (!modeling?.active_run || modeling.pipeline_phase !== "extracting") return null;
  const pkgKey = evidencePackageCleaningKey(pkg);
  if (!pkgKey) return null;
  const { source_type: runType, source_id: runId } = modeling.active_run;
  if (runId == null || !runType) return null;
  const runKey = `${runType}:${runId}`;
  if (runKey !== pkgKey) return null;
  return modeling.extraction.progress_percent;
}

function stepReasonFromRaw(raw: unknown): string | undefined {
  if (raw && typeof raw === "object" && "reason" in raw) {
    const v = (raw as { reason?: unknown }).reason;
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return undefined;
}

const FAILURE_REASON_LABELS: Record<string, string> = {
  no_eligible_chunks: "没有可抽取的文档分块（需完成索引且质量分>=0.4）",
  no_document_chunks: "无文档分块，已跳过术语/指标类抽取",
  no_llm_available: "未配置可用的大模型",
  no_analyzed_tables: "导入库中的表尚未完成 AI 分析",
  no_tables_found: "未找到导入数据源中的表",
  database_import_not_found: "数据库导入记录不存在",
  partial_step_failures: "部分抽取步骤失败",
  pipeline_timeout: "抽取超时（超过执行上限）",
  pipeline_stale: "流水线长时间无进展，已自动中止",
  stale_run: "步骤未执行（流水线提前中止）",
  server_restart: "服务重启导致流水线中断",
  timeout: "抽取超时",
  unexpected_error: "流水线异常终止",
  already_running: "已有正在运行的抽取任务",
  shacl_blocked: "入图被 SHACL 校验拦截",
  no_triples_written: "入图未写入任何三元组",
  no_triples:
    "抽取已完成但未产生可入图三元组。请确认仓库含表间依赖或 JOIN 类逻辑（SQL/dbt/Python/Spark 等），且单文件正文≥50 字符；可在流水线步骤中查看 _git_diagnostics",
  no_git_entries: "该 Git 源暂无已同步文件",
  failed: "抽取流水线失败",
  json_query_error: "导入源筛选条件解析失败（JSON 字段查询异常）",
};

function resolvePipelineFailureMessage(
  sourceStat: SourceCleaningStat | undefined,
): string | undefined {
  const raw = (sourceStat?.failure_reason || sourceStat?.message || "").trim();
  if (!raw) return undefined;
  const lower = raw.toLowerCase();
  if (lower === "failed" || raw === "抽取流水线失败") {
    return FAILURE_REASON_LABELS.failed;
  }
  if (["skipped", "completed", "running", "pending"].includes(lower)) {
    return undefined;
  }
  if (
    lower.includes("astext") &&
    (lower.includes("binaryexpression") || lower.includes("comparator"))
  ) {
    return FAILURE_REASON_LABELS.json_query_error;
  }
  if (raw.includes("Fuseki") || raw.includes("fuseki")) {
    return raw;
  }
  return humanizeReasonCode(raw) ?? raw;
}

function humanizeReasonCode(code: string | undefined): string | undefined {
  if (!code) return undefined;
  return FAILURE_REASON_LABELS[code] ?? code;
}

function buildStepFailureDetail(raw: unknown, fallbackReason?: string): string | undefined {
  if (!raw || typeof raw !== "object") {
    return fallbackReason;
  }

  const step = raw as Record<string, unknown>;
  const lines: string[] = [];

  const reasonCode = typeof step.reason === "string" ? step.reason : undefined;
  const reasonHuman = humanizeReasonCode(reasonCode);
  if (reasonHuman) {
    lines.push(`原因：${reasonHuman}`);
  }

  const message = typeof step.message === "string" ? step.message.trim() : "";
  if (message) {
    lines.push(`信息：${message}`);
  }

  const triples = typeof step.triples === "number" ? step.triples : undefined;
  const total = typeof step.total === "number" ? step.total : undefined;
  const written = typeof step.written === "number" ? step.written : undefined;
  const quarantined = typeof step.quarantined === "number" ? step.quarantined : undefined;
  const candidates = typeof step.candidates === "number" ? step.candidates : undefined;
  if (triples != null) lines.push(`抽取三元组：${triples}`);
  if (total != null) lines.push(`写入总量：${total}`);
  if (written != null) lines.push(`实际写入：${written}`);
  if (candidates != null) lines.push(`候选三元组：${candidates}`);
  if (quarantined != null) lines.push(`隔离数量：${quarantined}`);

  const shacl = step.shacl;
  if (shacl && typeof shacl === "object") {
    const report = shacl as Record<string, unknown>;
    const conforms = report.conforms;
    if (typeof conforms === "boolean") {
      lines.push(`SHACL conforms：${conforms ? "true" : "false"}`);
    }
    const violations = report.violations;
    if (Array.isArray(violations) && violations.length > 0) {
      const msgs = violations
        .map((v) => (v && typeof v === "object" ? (v as Record<string, unknown>).message : undefined))
        .filter((m): m is string => typeof m === "string" && m.trim().length > 0)
        .slice(0, 3);
      if (msgs.length > 0) {
        lines.push("SHACL 违规：");
        msgs.forEach((m, idx) => lines.push(`${idx + 1}. ${m}`));
      }
    }
  }

  const fallbackHuman = humanizeReasonCode(fallbackReason);
  if (lines.length === 0 && fallbackHuman) {
    lines.push(`原因：${fallbackHuman}`);
  }

  return lines.length > 0 ? lines.join("\n") : undefined;
}

function stepIconForStatus(status: string): PipelineStepIconStatus {
  if (status === "done" || status === "completed") return "ok";
  if (status === "failed") return "fail";
  if (status === "running") return "running";
  return "pending";
}

function stepDotClass(icon: PipelineStepIconStatus): string {
  if (icon === "ok") return "bg-emerald-500";
  if (icon === "fail") return "bg-red-500";
  if (icon === "running") return "bg-indigo-500";
  return "bg-slate-300";
}

function stepStateText(icon: PipelineStepIconStatus): string {
  if (icon === "ok") return "成功";
  if (icon === "fail") return "失败";
  if (icon === "running") return "进行中";
  return "未执行";
}

function extractionStepIconsForPackage(
  pkg: EvidencePackage,
  sourceStat: SourceCleaningStat | undefined,
  modeling: ModelingStatus | null,
): { label: string; icon: PipelineStepIconStatus; reason?: string }[] {
  if (sourceStat?.status === "completed") {
    const rawSteps = sourceStat.steps ?? null;
    return EXTRACTION_STEP_DEFS.map(({ key, label }) => {
      const rawStep = rawSteps ? rawSteps[key] : undefined;
      const icon = rawSteps ? stepIconForStatus(mapRawStepStatus(rawStep)) : "ok";
      const reason = buildStepFailureDetail(rawStep, undefined);
      return { label, icon, reason: icon === "fail" ? reason : undefined };
    });
  }

  if (sourceStat?.status === "failed") {
    const pipelineReason = resolvePipelineFailureMessage(sourceStat);
    const rawSteps = sourceStat.steps ?? null;
    const mapped = EXTRACTION_STEP_DEFS.map(({ key, label }) => {
      const rawStep = rawSteps ? rawSteps[key] : undefined;
      const icon = rawSteps ? stepIconForStatus(mapRawStepStatus(rawStep)) : "pending";
      const reason = buildStepFailureDetail(rawStep, pipelineReason);
      return { label, icon, reason: icon === "fail" ? reason : undefined };
    });
    const writeFailed = rawSteps && mapRawStepStatus(rawSteps.ontology_write) === "failed";
    if (pipelineReason && !mapped.some((s) => s.icon === "fail") && !writeFailed) {
      mapped[mapped.length - 1] = {
        ...mapped[mapped.length - 1],
        icon: "fail",
        reason: pipelineReason,
      };
    }
    return mapped;
  }

  const runningPkgKey = evidencePackageCleaningKey(pkg);

  if (sourceStat?.status === "running" && sourceStat.steps) {
    const rawSteps = sourceStat.steps;
    return EXTRACTION_STEP_DEFS.map(({ key, label }) => {
      const rawStep = rawSteps[key];
      const icon = stepIconForStatus(mapRawStepStatus(rawStep));
      const fallbackReason =
        sourceStat.status === "failed"
          ? (sourceStat.message || sourceStat.failure_reason || "").trim() || undefined
          : undefined;
      const reason = buildStepFailureDetail(rawStep, fallbackReason);
      return { label, icon, reason: icon === "fail" ? reason : undefined };
    });
  }

  const isActiveRunningSource =
    sourceStat?.status === "running" &&
    runningPkgKey &&
    modeling?.active_run?.source_type &&
    modeling.active_run.source_id != null &&
    `${modeling.active_run.source_type}:${modeling.active_run.source_id}` === runningPkgKey;

  if (isActiveRunningSource && modeling?.extraction?.steps) {
    const byKey = new Map(modeling.extraction.steps.map((s) => [s.key, s]));
    return EXTRACTION_STEP_DEFS.map(({ key, label }) => {
      const step = byKey.get(key);
      const icon = (step?.icon && ["ok", "fail", "running", "skip", "pending", "warning"].includes(step.icon)
        ? step.icon
        : "pending") as PipelineStepIconStatus;
      return { label, icon: icon === "skip" ? "pending" : icon, reason: undefined };
    });
  }

  const rawSteps = sourceStat?.steps ?? null;
  const fallbackReason =
    sourceStat?.status === "failed"
      ? (sourceStat.message || sourceStat.failure_reason || "").trim() || undefined
      : undefined;
  return EXTRACTION_STEP_DEFS.map(({ key, label }) => {
    const rawStep = rawSteps ? rawSteps[key] : undefined;
    const icon = rawSteps ? stepIconForStatus(mapRawStepStatus(rawStep)) : "pending";
    const reason = buildStepFailureDetail(rawStep, fallbackReason);
    return { label, icon, reason: icon === "fail" ? reason : undefined };
  });
}

function gitDiagnosticsFromSteps(steps: SourceCleaningStat["steps"] | undefined): Record<string, unknown> | null {
  if (!steps || typeof steps !== "object") return null;
  const raw = (steps as Record<string, unknown>)["_git_diagnostics"];
  return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
}

function formatGitDiagnostics(diag: Record<string, unknown>): string {
  const lines: string[] = [];
  const add = (label: string, val: unknown) => {
    if (val == null) return;
    if (typeof val === "object") {
      lines.push(`${label}：${JSON.stringify(val)}`);
    } else {
      lines.push(`${label}：${String(val)}`);
    }
  };
  add("总条目", diag.total_entries);
  add("已处理", diag.processed_entries);
  add("正文达标", diag.eligible_body_ge_min);
  add("扩展名分布", diag.by_ext);
  add("规则命中", diag.regex_hits);
  add("单表引用", diag.single_table_refs);
  add("样例路径", diag.sample_paths);
  return lines.join("\n");
}

function mergedStatusChip(
  pkg: EvidencePackage,
  cleaningStats: Record<string, SourceCleaningStat> | null,
  modeling: ModelingStatus | null,
  documents: DocRow[],
): {
  detail?: string;
  gitDiagnostics?: Record<string, unknown> | null;
  steps: { label: string; icon: PipelineStepIconStatus; reason?: string }[];
} {
  const cleanKey = evidencePackageCleaningKey(pkg);
  const sourceStat = cleanKey && cleaningStats ? cleaningStats[cleanKey] : undefined;
  const extractionSteps = isPhysicalSchemaPackage(pkg)
    ? databaseSchemaStepsForPackage(sourceStat)
    : extractionStepIconsForPackage(pkg, sourceStat, modeling);
  const steps = [
    { label: "索引", icon: indexingStepIconForPackage(pkg, documents), reason: undefined },
    ...extractionSteps,
  ];

  if (sourceStat?.status === "running") {
    if (isPhysicalSchemaPackage(pkg)) {
      return { detail: "清洗中…", steps };
    }
    const pct = modelingProgressForPackage(pkg, sourceStat, modeling);
    const activeStep = extractionStepForPackage(pkg, modeling);
    return {
      detail: activeStep
        ? `${pct != null ? `进度 ${pct}% · ` : ""}当前步骤：${activeStep.label}`
        : pct != null
          ? `进度 ${pct}%`
          : undefined,
      steps,
    };
  }
  if (sourceStat?.status === "completed") {
    return { steps };
  }
  if (sourceStat?.status === "failed") {
    return {
      detail: resolvePipelineFailureMessage(sourceStat),
      gitDiagnostics: gitDiagnosticsFromSteps(sourceStat.steps),
      steps,
    };
  }

  if (pkg.processing_state === "registered") {
    return { steps };
  }
  if (pkg.processing_state === "normalized") {
    return { steps };
  }
  if (pkg.processing_state === "ready_for_extraction" || pkg.processing_state === "indexed") {
    return { steps };
  }
  return { steps };
}

const FAIL_LOG_TOOLTIP_EST_HEIGHT = 260;
const FAIL_LOG_VIEWPORT_PAD = 12;
const FAIL_LOG_GAP = 8;

type FailLogTooltipState = {
  label: string;
  reason: string;
  x: number;
  y: number;
  placement: "above" | "below";
  maxHeight: number;
};

function computeFailLogTooltipPosition(rect: DOMRect): Omit<FailLogTooltipState, "label" | "reason"> {
  const maxWidth = Math.min(460, window.innerWidth * 0.8);
  const half = maxWidth / 2;
  const pad = FAIL_LOG_VIEWPORT_PAD;
  const centerX = rect.left + rect.width / 2;
  const clampedX = Math.min(
    Math.max(centerX, pad + half),
    Math.max(pad + half, window.innerWidth - pad - half),
  );
  const spaceBelow = window.innerHeight - rect.bottom - FAIL_LOG_GAP - pad;
  const spaceAbove = rect.top - FAIL_LOG_GAP - pad;
  const placeAbove =
    spaceBelow < FAIL_LOG_TOOLTIP_EST_HEIGHT && spaceAbove >= spaceBelow;

  if (placeAbove) {
    return {
      x: clampedX,
      y: rect.top - FAIL_LOG_GAP,
      placement: "above",
      maxHeight: Math.max(96, Math.min(280, spaceAbove)),
    };
  }
  return {
    x: clampedX,
    y: rect.bottom + FAIL_LOG_GAP,
    placement: "below",
    maxHeight: Math.max(96, Math.min(280, spaceBelow)),
  };
}

const EvidencePackageRow = memo(function EvidencePackageRow({
  pkg,
  statusDetail,
  gitDiagnostics,
  statusSteps,
}: {
  pkg: EvidencePackage;
  statusDetail?: string;
  gitDiagnostics?: Record<string, unknown> | null;
  statusSteps: { label: string; icon: PipelineStepIconStatus; reason?: string }[];
}) {
  const [showGitDiag, setShowGitDiag] = useState(false);
  const [stepTooltip, setStepTooltip] = useState<FailLogTooltipState | null>(null);
  const [pinnedLog, setPinnedLog] = useState<{ label: string; reason: string } | null>(null);
  const pinnedLogRef = useRef<HTMLDivElement | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearCloseTimer = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const closeTooltipSoon = useCallback(() => {
    clearCloseTimer();
    closeTimerRef.current = setTimeout(() => {
      setStepTooltip(null);
    }, 120);
  }, [clearCloseTimer]);

  const openFailTooltip = useCallback(
    (event: React.MouseEvent<HTMLElement>, label: string, reason: string) => {
      clearCloseTimer();
      const rect = event.currentTarget.getBoundingClientRect();
      setStepTooltip({ label, reason, ...computeFailLogTooltipPosition(rect) });
    },
    [clearCloseTimer],
  );

  const togglePinnedLog = useCallback((label: string, reason: string) => {
    clearCloseTimer();
    setStepTooltip(null);
    setPinnedLog((prev) => (prev?.label === label ? null : { label, reason }));
  }, [clearCloseTimer]);

  useEffect(() => () => clearCloseTimer(), [clearCloseTimer]);

  useEffect(() => {
    if (!pinnedLog) return;
    const el = pinnedLogRef.current;
    if (!el) return;
    const t = window.setTimeout(() => {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, 0);
    return () => window.clearTimeout(t);
  }, [pinnedLog]);

  return (
    <tr className="hover:bg-app-hover">
      <td className="px-3 py-2 font-mono text-xs text-app-muted whitespace-nowrap">{pkg.display_id}</td>
      <td className="px-3 py-2 text-app-primary max-w-[240px] truncate" title={pkg.title}>
        {pkg.title}
      </td>
      <td className="px-3 py-2 max-w-[180px]">
        <ConnectorCell pkg={pkg} />
      </td>
      <td className="px-3 py-2">
        {statusSteps.length > 0 && (
          <div className="flex flex-wrap items-start gap-2">
            {statusSteps.map((s) => (
              <span
                key={s.label}
                className={`inline-flex flex-col items-center gap-0.5 ${
                  s.icon === "fail" && s.reason ? "cursor-pointer" : ""
                }`}
                aria-label={
                  s.icon === "fail" && s.reason
                    ? `${s.label}：失败，${s.reason}`
                    : `${s.label}：${stepStateText(s.icon)}`
                }
                title={
                  s.icon === "fail" && s.reason
                    ? `${s.reason}\n（点击查看完整日志）`
                    : undefined
                }
                onMouseEnter={
                  s.icon === "fail" && s.reason && !pinnedLog
                    ? (e) => openFailTooltip(e, s.label, s.reason as string)
                    : undefined
                }
                onMouseLeave={s.icon === "fail" && s.reason && !pinnedLog ? closeTooltipSoon : undefined}
                onClick={
                  s.icon === "fail" && s.reason
                    ? (e) => {
                        e.stopPropagation();
                        togglePinnedLog(s.label, s.reason as string);
                      }
                    : undefined
                }
              >
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${stepDotClass(s.icon)}`} />
                <span className="text-[10px] leading-none text-app-muted">{s.label}</span>
                <span className="sr-only">
                  {s.icon === "fail" && s.reason
                    ? `${s.label}：失败，${s.reason}`
                    : `${s.label}：${stepStateText(s.icon)}`}
                </span>
              </span>
            ))}
          </div>
        )}
        {pinnedLog && (
          <div
            ref={pinnedLogRef}
            className="mt-2 w-full min-w-[12rem] max-w-[min(520px,100%)] rounded-md border border-red-200 bg-red-50 p-2 text-[11px] leading-relaxed text-red-800 shadow-sm"
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <p className="font-medium text-red-900">{pinnedLog.label} 失败日志</p>
              <button
                type="button"
                className="shrink-0 text-[10px] text-red-600 hover:text-red-800 underline"
                onClick={() => setPinnedLog(null)}
              >
                收起
              </button>
            </div>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] text-red-700 select-text">
              {pinnedLog.reason}
            </pre>
          </div>
        )}
        {stepTooltip &&
          !pinnedLog &&
          typeof document !== "undefined" &&
          createPortal(
            <div
              role="tooltip"
              className="fixed z-[9999] w-[min(460px,80vw)] rounded-md border border-red-200 bg-white p-2 text-[11px] leading-relaxed text-red-700 shadow-lg select-text pointer-events-auto"
              style={{
                left: stepTooltip.x,
                top: stepTooltip.y,
                maxHeight: stepTooltip.maxHeight,
                transform:
                  stepTooltip.placement === "above"
                    ? "translate(-50%, -100%)"
                    : "translateX(-50%)",
              }}
              onMouseEnter={clearCloseTimer}
              onMouseLeave={closeTooltipSoon}
            >
              <p className="mb-1 font-medium text-red-800">{stepTooltip.label} 失败日志</p>
              <pre
                className="overflow-auto whitespace-pre-wrap break-words font-mono text-[11px]"
                style={{ maxHeight: Math.max(64, stepTooltip.maxHeight - 36) }}
              >
                {stepTooltip.reason}
              </pre>
              <p className="mt-1 text-[10px] text-red-500/80">点击圆点可在行内固定查看</p>
            </div>,
            document.body,
          )}
        {statusDetail && (
          <p className="mt-1 max-w-xs text-[11px] leading-snug text-app-muted line-clamp-2" title={statusDetail}>
            {statusDetail}
          </p>
        )}
        {gitDiagnostics && (
          <div className="mt-1 max-w-xs">
            <button
              type="button"
              className="text-[10px] text-app-muted underline hover:text-app-primary"
              onClick={() => setShowGitDiag((v) => !v)}
            >
              {showGitDiag ? "收起 Git 诊断" : "查看 _git_diagnostics"}
            </button>
            {showGitDiag && (
              <pre className="mt-1 max-h-32 overflow-auto rounded border border-app-border bg-[var(--app-surface)] p-1.5 text-[10px] leading-snug text-app-secondary whitespace-pre-wrap">
                {formatGitDiagnostics(gitDiagnostics)}
              </pre>
            )}
          </div>
        )}
      </td>
      <td className="px-3 py-2 whitespace-nowrap text-xs text-app-secondary">
        {formatRegisteredAt(pkg.created_at)}
      </td>
    </tr>
  );
});

export default function EvidencePackageList({
  kbId,
  cleaningStats: cleaningStatsProp = null,
  documents = [],
  modeling: modelingProp = undefined,
  refreshSeq = 0,
}: {
  kbId: number;
  cleaningStats?: Record<string, SourceCleaningStat> | null;
  documents?: DocRow[];
  /** 父组件轮询提供的建模状态；传入后不再单独拉取 */
  modeling?: ModelingStatus | null;
  /** 父组件递增以触发证据包列表静默刷新（不整表 loading） */
  refreshSeq?: number;
}) {
  function packageOrderId(pkg: EvidencePackage): number {
    if (typeof pkg.db_id === "number") return pkg.db_id;
    const display = (pkg.display_id || "").trim();
    const m = /^EP-(\d+)$/.exec(display);
    return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER;
  }

  const [packages, setPackages] = useState<EvidencePackage[]>([]);
  const [localCleaningStats, setLocalCleaningStats] = useState<Record<string, SourceCleaningStat> | null>(null);
  const [localModeling, setLocalModeling] = useState<ModelingStatus | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const cleaningStats = cleaningStatsProp ?? localCleaningStats;
  const modeling = modelingProp !== undefined ? modelingProp : localModeling;
  const statsFromParent = cleaningStatsProp != null;
  const modelingFromParent = modelingProp !== undefined;
  const loadPackages = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setInitialLoading(true);
    try {
      const pkgRes = await api<{ packages: EvidencePackage[] }>(
        `/api/knowledge-bases/${kbId}/ingestion/packages`,
      );
      const sorted = [...(pkgRes.packages ?? [])].sort(
        (a, b) => packageOrderId(a) - packageOrderId(b),
      );
      setPackages(sorted);
    } catch {
      setPackages([]);
    } finally {
      if (!opts?.silent) setInitialLoading(false);
    }
  }, [kbId]);

  const refreshModeling = useCallback(async () => {
    const modelingRes = await api<ModelingStatus>(
      `/api/ontology/knowledge-bases/${kbId}/modeling/status`,
    ).catch(() => null);
    setLocalModeling(modelingRes);
  }, [kbId]);

  const refreshLocalCleaningStats = useCallback(async () => {
    const statsRes = await api<{ stats: Record<string, SourceCleaningStat> }>(
      `/api/knowledge-bases/${kbId}/source-cleaning-stats`,
    ).catch(() => ({ stats: {} }));
    setLocalCleaningStats(statsRes.stats ?? {});
  }, [kbId]);

  useEffect(() => {
    void (async () => {
      await loadPackages();
      if (!modelingFromParent) {
        await refreshModeling();
      }
      if (!statsFromParent) {
        await refreshLocalCleaningStats();
      }
    })();
    // 仅 kb 切换时重拉列表；清洗/建模状态由 props / 父级轮询单独更新
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    if (refreshSeq <= 0) return;
    void loadPackages({ silent: true });
    if (!modelingFromParent) {
      void refreshModeling();
    }
  }, [refreshSeq, loadPackages, refreshModeling, modelingFromParent]);

  if (initialLoading) {
    return <p className="text-sm text-app-muted">加载证据包…</p>;
  }

  if (packages.length === 0) {
    return (
      <p className="text-sm text-app-muted">
        暂无证据包。点击「导入数据」导入企业数据，系统将自动登记为证据包。
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-app-border bg-[var(--app-card-bg)]">
      <table className="app-table text-sm">
        <thead>
          <tr>
            <th className="px-3 py-2 text-left">证据包</th>
            <th className="px-3 py-2 text-left">标题</th>
            <th className="px-3 py-2 text-left">连接器</th>
            <th className="px-3 py-2 text-left">状态</th>
            <th className="px-3 py-2 text-left whitespace-nowrap">登记时间</th>
          </tr>
        </thead>
        <tbody>
          {packages.map((pkg) => {
            const status = mergedStatusChip(pkg, cleaningStats, modeling, documents);
            return (
              <EvidencePackageRow
                key={pkg.id}
                pkg={pkg}
                statusDetail={status.detail}
                gitDiagnostics={status.gitDiagnostics}
                statusSteps={status.steps}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
