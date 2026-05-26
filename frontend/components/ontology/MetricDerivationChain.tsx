"use client";

import { ArrowRight, Database, FunctionSquare, Layers } from "lucide-react";

export interface DerivationStep {
  iri: string;
  label: string;
  stepType: "metric" | "table" | "transformation" | "intermediate";
  detail?: string;
}

interface MetricDerivationChainProps {
  steps: DerivationStep[];
  metricLabel?: string;
}

const stepIcons = {
  metric: FunctionSquare,
  table: Database,
  transformation: ArrowRight,
  intermediate: Layers,
};

const stepTones = {
  metric: "border-amber-500/30 bg-amber-500/5",
  table: "border-emerald-500/30 bg-emerald-500/5",
  transformation: "border-indigo-500/30 bg-indigo-500/5",
  intermediate: "border-app-muted/20 bg-app-surface-subtle",
};

export default function MetricDerivationChain({
  steps,
  metricLabel,
}: MetricDerivationChainProps) {
  if (steps.length === 0) {
    return (
      <p className="text-sm text-app-muted px-3 py-4">
        暂无派生链数据。指标派生链展示指标从源表到最终计算口径的数据流向。
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {metricLabel && (
        <h4 className="text-sm font-semibold text-app-primary px-1">
          派生链：{metricLabel}
        </h4>
      )}

      <div className="flex flex-wrap items-start gap-2">
        {steps.map((step, i) => {
          const tone =
            stepTones[step.stepType] || stepTones.intermediate;
          const Icon =
            stepIcons[step.stepType] || stepIcons.intermediate;

          return (
            <div key={step.iri || i} className="flex items-center gap-2">
              {/* Connector arrow */}
              {i > 0 && (
                <ArrowRight className="h-4 w-4 shrink-0 text-app-muted/50" />
              )}

              {/* Step card */}
              <div
                className={`shrink-0 rounded-xl border px-4 py-3 min-w-[120px] max-w-[200px] ${tone}`}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <Icon className="h-3.5 w-3.5 text-app-muted" aria-hidden />
                  <span className="text-[10px] uppercase tracking-wider text-app-muted">
                    {stepTypeLabel(step.stepType)}
                  </span>
                </div>
                <p className="text-sm font-medium text-app-primary truncate">
                  {step.label}
                </p>
                {step.detail && (
                  <p className="text-[11px] text-app-muted line-clamp-2 mt-0.5">
                    {step.detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function stepTypeLabel(t: DerivationStep["stepType"]): string {
  switch (t) {
    case "metric":
      return "指标";
    case "table":
      return "源表";
    case "transformation":
      return "转换";
    case "intermediate":
      return "中间表";
  }
}
