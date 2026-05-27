"use client";

import { PipelineStepIcon, type PipelineStepIconStatus } from "../icons";

export type ModelingStep = {
  key: string;
  label: string;
  status: string;
  icon: string;
  triples?: number;
  reason?: string;
};

export type ModelingStatus = {
  ok: boolean;
  kb_id: number;
  pipeline_phase: string;
  active_run?: {
    source_type: string | null;
    source_id: number | null;
  } | null;
  indexing: {
    total_documents: number;
    indexed_documents: number;
    complete: boolean;
  };
  extraction: {
    run_id: number | null;
    status: string | null;
    progress_percent: number;
    steps: ModelingStep[];
    started_at?: string | null;
    completed_at?: string | null;
  };
  layers_summary: Record<string, number>;
  quality: {
    shacl_pass_rate: number | null;
    quarantine_count: number;
    rdf_triple_count: number;
  };
};

function StepIcon({ icon }: { icon: string }) {
  const status = (["ok", "fail", "running", "skip", "pending", "warning"].includes(icon)
    ? icon
    : "pending") as PipelineStepIconStatus;
  return <PipelineStepIcon status={status} />;
}

const PHASE_LABELS: Record<string, string> = {
  idle: "待运行",
  extracting: "抽取中",
  completed: "已完成",
  failed: "失败",
};

const RUN_MODELING_HINT =
  "对已索引文档块后台执行 8 步抽取（术语、指标、维度、规则、关系、层级；Git 源另含血缘与 JOIN），" +
  "经清洗与 SHACL 校验后写入 RDF。不重新导入或分块索引；需已配置 LLM 且存在 quality_score ≥ 0.4 的文档块。";

export default function ModelingPipelineStatus({
  status,
  loading,
  compact,
  onRunModeling,
  runningModeling,
}: {
  status: ModelingStatus | null;
  loading?: boolean;
  compact?: boolean;
  onRunModeling?: () => void;
  runningModeling?: boolean;
}) {
  if (loading) {
    return <div className="app-card p-6 text-sm text-app-muted">加载建模流水线…</div>;
  }
  if (!status) {
    return (
      <div className="app-card p-6 text-sm text-app-muted">
        暂无建模状态。导入文档并触发「语义清洗」后将显示 8 步抽取进度。
      </div>
    );
  }

  const idx = status.indexing;
  const ext = status.extraction;
  const q = status.quality;

  return (
    <div className="space-y-4">
      {onRunModeling && (
        <div className="flex items-start gap-3">
          <button
            type="button"
            className={`app-button shrink-0 text-sm ${runningModeling ? "is-loading" : ""}`}
            disabled={runningModeling || ext.status === "running"}
            onClick={onRunModeling}
          >
            {runningModeling || ext.status === "running" ? "建模运行中…" : "运行完整建模"}
          </button>
          <p className="min-w-0 flex-1 text-xs leading-relaxed text-app-muted">
            {RUN_MODELING_HINT}
          </p>
        </div>
      )}
      {/* Pipeline flow */}
      <div className="app-card p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-app-muted">
          <span className="inline-flex items-center gap-1">
            分块索引 {idx.indexed_documents}/{idx.total_documents}
            {idx.complete ? <PipelineStepIcon status="ok" className="h-3.5 w-3.5" /> : null}
          </span>
          <span>→</span>
          <span className={ext.status === "running" ? "text-indigo-600 font-medium" : ""}>
            抽取 {ext.status === "running" ? `${ext.progress_percent}%` : PHASE_LABELS[status.pipeline_phase] || ext.status || "—"}
          </span>
          <span>→</span>
          <span>清洗 / SHACL</span>
          <span>→</span>
          <span className="inline-flex items-center gap-1">
            入图
            <PipelineStepIcon
              status={q.rdf_triple_count > 0 ? "ok" : "pending"}
              className="h-3.5 w-3.5"
            />
          </span>
        </div>
        {ext.status === "running" && (
          <div className="mt-3 h-2 rounded-full bg-app-hover overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all duration-500"
              style={{ width: `${Math.min(100, ext.progress_percent)}%` }}
            />
          </div>
        )}
      </div>

      {/* Summary cards */}
      {!compact && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MiniStat label="词汇层" value={status.layers_summary.vocabulary ?? 0} />
          <MiniStat label="规则层" value={status.layers_summary.rule ?? 0} />
          <MiniStat
            label="SHACL"
            value={q.shacl_pass_rate != null ? `${q.shacl_pass_rate}%` : "—"}
          />
          <MiniStat label="隔离区" value={q.quarantine_count} warn={q.quarantine_count > 0} />
        </div>
      )}

      {/* 8-step extraction */}
      <div className="app-card p-4">
        <h4 className="text-sm font-medium text-app-primary mb-3">抽取步骤</h4>
        <div className="flex flex-wrap gap-2">
          {ext.steps
            .filter((s) => s.key !== "ontology_write")
            .map((step) => (
              <span
                key={step.key}
                className="inline-flex items-center gap-1 rounded-lg border border-app-border px-2 py-1 text-xs text-app-secondary"
                title={step.reason || step.status}
              >
                <StepIcon icon={step.icon} />
                {step.label}
              </span>
            ))}
        </div>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  warn,
}: {
  label: string;
  value: number | string;
  warn?: boolean;
}) {
  return (
    <div className="app-card px-3 py-2">
      <p className="text-[11px] text-app-muted">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${warn ? "text-amber-600" : "text-app-primary"}`}>
        {value}
      </p>
    </div>
  );
}
