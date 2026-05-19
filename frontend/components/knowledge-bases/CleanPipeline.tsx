"use client";

import PipelineStep, { type PipelineStepData } from "./PipelineStep";

interface CleanPipelineProps {
  steps: PipelineStepData[];
}

export default function CleanPipeline({ steps }: CleanPipelineProps) {
  if (steps.length === 0) {
    return (
      <section className="mt-6 app-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">🔄</span>
          <h2 className="app-section-title">Pipeline</h2>
        </div>
        <p className="text-sm text-app-muted">暂无清洗数据。导入文档或代码源后，流水线将自动开始处理。</p>
      </section>
    );
  }

  return (
    <section className="mt-6 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔄</span>
          <h2 className="app-section-title">
            Pipeline
            <span className="ml-2 text-xs font-normal text-app-muted">
              本知识库支持 {steps.length} 个清洗环节
            </span>
          </h2>
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-3">
        {steps.map((step, i) => (
          <div key={step.id} className="flex items-center gap-3">
            <PipelineStep step={step} />
            {i < steps.length - 1 && (
              <svg
                className="h-5 w-5 shrink-0 text-app-muted"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="9 18 15 12 9 6" />
              </svg>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
