"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import type { ModelingStatus } from "../ontology/ModelingPipelineStatus";
import type { PipelineStepIconStatus } from "../icons";
import type { EvidencePackage } from "./ingestionTypes";
import { CONNECTOR_LABELS } from "./ingestionTypes";
import type { SourceCleaningStat } from "./types";
import { evidencePackageCleaningKey } from "./sourceCleaningKey";

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

function modelingProgressForPackage(
  pkg: EvidencePackage,
  modeling: ModelingStatus | null,
): number | null {
  if (!modeling?.active_run || modeling.pipeline_phase !== "extracting") return null;
  const pkgKey = evidencePackageCleaningKey(pkg);
  if (!pkgKey) return null;
  const { source_type: runType, source_id: runId } = modeling.active_run;
  if (runId == null || !runType) return null;
  const runKey = `${runType}:${runId}`;
  if (runKey !== pkgKey) return null;
  return modeling.extraction.progress_percent;
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
  { key: "metric_caliber", label: "指标" },
  { key: "dimension_extraction", label: "维度" },
  { key: "rule_extraction", label: "规则" },
  { key: "relation_extraction", label: "关系" },
  { key: "hierarchy_building", label: "层级" },
  { key: "data_lineage", label: "血缘" },
  { key: "join_extraction", label: "JOIN" },
];

function mapRawStepStatus(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && "status" in raw) {
    const v = (raw as { status?: unknown }).status;
    return typeof v === "string" ? v : "pending";
  }
  return "pending";
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
};

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

function indexingStepIcon(pkg: EvidencePackage): PipelineStepIconStatus {
  const total = pkg.document_count ?? 0;
  const indexed = pkg.indexed_document_count ?? 0;
  if (total > 0 && indexed >= total) return "ok";
  if (pkg.processing_state === "ready_for_extraction" || pkg.processing_state === "indexed") return "ok";
  if (total > 0 && indexed > 0 && indexed < total) return "running";
  return "pending";
}

function extractionStepIconsForPackage(
  pkg: EvidencePackage,
  sourceStat: SourceCleaningStat | undefined,
  modeling: ModelingStatus | null,
): { label: string; icon: PipelineStepIconStatus; reason?: string }[] {
  if (sourceStat?.status === "completed") {
    return EXTRACTION_STEP_DEFS.map((s) => ({ label: s.label, icon: "ok", reason: undefined }));
  }

  const runningPkgKey = evidencePackageCleaningKey(pkg);
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

function mergedStatusChip(
  pkg: EvidencePackage,
  cleaningStats: Record<string, SourceCleaningStat> | null,
  modeling: ModelingStatus | null,
): {
  detail?: string;
  steps: { label: string; icon: PipelineStepIconStatus; reason?: string }[];
} {
  const cleanKey = evidencePackageCleaningKey(pkg);
  const sourceStat = cleanKey && cleaningStats ? cleaningStats[cleanKey] : undefined;
  const extractionSteps = extractionStepIconsForPackage(pkg, sourceStat, modeling);
  const steps = [{ label: "索引", icon: indexingStepIcon(pkg), reason: undefined }, ...extractionSteps];

  if (sourceStat?.status === "running") {
    const pct = modelingProgressForPackage(pkg, modeling);
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

const EvidencePackageRow = memo(function EvidencePackageRow({
  pkg,
  statusDetail,
  statusSteps,
}: {
  pkg: EvidencePackage;
  statusDetail?: string;
  statusSteps: { label: string; icon: PipelineStepIconStatus; reason?: string }[];
}) {
  const [stepTooltip, setStepTooltip] = useState<{
    label: string;
    reason: string;
    x: number;
    y: number;
  } | null>(null);
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
      const maxWidth = Math.min(460, window.innerWidth * 0.8);
      const pad = 12;
      const half = maxWidth / 2;
      const centerX = rect.left + rect.width / 2;
      const clampedX = Math.min(
        Math.max(centerX, pad + half),
        Math.max(pad + half, window.innerWidth - pad - half),
      );
      const top = rect.bottom + 8;
      setStepTooltip({ label, reason, x: clampedX, y: top });
    },
    [clearCloseTimer],
  );

  useEffect(() => () => clearCloseTimer(), [clearCloseTimer]);

  return (
    <tr className="hover:bg-app-hover">
      <td className="px-3 py-2 font-mono text-xs text-app-muted whitespace-nowrap">{pkg.display_id}</td>
      <td className="px-3 py-2 text-app-primary max-w-[240px] truncate" title={pkg.title}>
        {pkg.title}
      </td>
      <td className="px-3 py-2 max-w-[180px]">
        <ConnectorCell pkg={pkg} />
      </td>
      <td className="px-3 py-2 max-w-[180px]">
        <span className="truncate text-app-primary">{pkg.asset_label}</span>
      </td>
      <td className="px-3 py-2">
        {statusSteps.length > 0 && (
          <div className="flex flex-wrap items-start gap-2">
            {statusSteps.map((s) => (
              <span
                key={s.label}
                className="inline-flex flex-col items-center gap-0.5"
                aria-label={
                  s.icon === "fail" && s.reason
                    ? `${s.label}：失败，${s.reason}`
                    : `${s.label}：${stepStateText(s.icon)}`
                }
                onMouseEnter={
                  s.icon === "fail" && s.reason
                    ? (e) => openFailTooltip(e, s.label, s.reason as string)
                    : undefined
                }
                onMouseLeave={s.icon === "fail" && s.reason ? closeTooltipSoon : undefined}
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
        {stepTooltip && (
          <div
            className="fixed z-[9999] w-[min(460px,80vw)] rounded-md border border-red-200 bg-white p-2 text-[11px] leading-relaxed text-red-700 shadow-lg select-text"
            style={{ left: stepTooltip.x, top: stepTooltip.y, transform: "translateX(-50%)" }}
            onMouseEnter={clearCloseTimer}
            onMouseLeave={closeTooltipSoon}
          >
            <p className="mb-1 font-medium text-red-800">{stepTooltip.label} 失败日志</p>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px]">
              {stepTooltip.reason}
            </pre>
          </div>
        )}
        {statusDetail && (
          <p className="mt-1 max-w-xs text-[11px] leading-snug text-app-muted line-clamp-2" title={statusDetail}>
            {statusDetail}
          </p>
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
}: {
  kbId: number;
  cleaningStats?: Record<string, SourceCleaningStat> | null;
}) {
  function packageOrderId(pkg: EvidencePackage): number {
    if (typeof pkg.db_id === "number") return pkg.db_id;
    const display = (pkg.display_id || "").trim();
    const m = /^EP-(\d+)$/.exec(display);
    return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER;
  }

  const [packages, setPackages] = useState<EvidencePackage[]>([]);
  const [localCleaningStats, setLocalCleaningStats] = useState<Record<string, SourceCleaningStat> | null>(null);
  const [modeling, setModeling] = useState<ModelingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const cleaningStats = cleaningStatsProp ?? localCleaningStats;
  const statsFromParent = cleaningStatsProp != null;

  const loadPackages = useCallback(async () => {
    setLoading(true);
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
      setLoading(false);
    }
  }, [kbId]);

  const refreshModeling = useCallback(async () => {
    const modelingRes = await api<ModelingStatus>(
      `/api/ontology/knowledge-bases/${kbId}/modeling/status`,
    ).catch(() => null);
    setModeling(modelingRes);
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
      await refreshModeling();
      if (!statsFromParent) {
        await refreshLocalCleaningStats();
      }
    })();
    // 仅 kb 切换时重拉列表；清洗状态由 props / 轮询单独更新
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const anySourceRunning =
    cleaningStats != null && Object.values(cleaningStats).some((s) => s.status === "running");

  useEffect(() => {
    if (!anySourceRunning) return;
    const t = setInterval(() => {
      void refreshModeling();
      if (!statsFromParent) {
        void refreshLocalCleaningStats();
      }
    }, 5000);
    return () => clearInterval(t);
  }, [kbId, anySourceRunning, statsFromParent, refreshModeling, refreshLocalCleaningStats]);

  if (loading) {
    return <p className="text-sm text-app-muted">加载证据包…</p>;
  }

  if (packages.length === 0) {
    return (
      <p className="text-sm text-app-muted">
        暂无证据包。点击「数据接入」导入企业数据，系统将自动登记为证据包。
      </p>
    );
  }

  return (
    <div className="overflow-x-auto overflow-y-visible rounded-xl border border-app-border bg-[var(--app-card-bg)]">
      <table className="app-table text-sm">
        <thead>
          <tr>
            <th className="px-3 py-2 text-left">证据包</th>
            <th className="px-3 py-2 text-left">标题</th>
            <th className="px-3 py-2 text-left">连接器</th>
            <th className="px-3 py-2 text-left">资产类型</th>
            <th className="px-3 py-2 text-left">状态</th>
            <th className="px-3 py-2 text-left whitespace-nowrap">登记时间</th>
          </tr>
        </thead>
        <tbody>
          {packages.map((pkg) => {
            const status = mergedStatusChip(pkg, cleaningStats, modeling);
            return (
              <EvidencePackageRow
                key={pkg.id}
                pkg={pkg}
                statusDetail={status.detail}
                statusSteps={status.steps}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
