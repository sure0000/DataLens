"use client";

import { useState, type ReactNode } from "react";
import CopilotExecutionTrace from "../CopilotExecutionTrace";
import {
  type OntologyMapping,
  type PipelineTraceStep,
  type SqlDerivation,
  traceStepsForDerivationPanel
} from "../../lib/chatSessions";
import { stripAutoRepairExplanationNote } from "../../lib/copilotTraceMarkdown";
import OntologyMappingBlock from "./OntologyMappingBlock";
import ChatGptStyleBody from "./ChatGptStyleBody";

const PATTERN_LABEL: Record<string, string> = {
  single_agg: "单表聚合",
  case_when_compare: "CASE WHEN 对比",
  self_join: "自连接对比",
  multi_join: "多表 JOIN",
  time_series: "时间序列"
};

const SQL_ROLE_LABEL: Record<string, string> = {
  aggregate: "聚合",
  filter: "过滤",
  join: "关联",
  group_by: "分组",
  order_by: "排序",
  select: "选取"
};

type Props = {
  ontologyMapping?: OntologyMapping;
  pipelineTrace?: PipelineTraceStep[];
  explanation?: string;
  sqlDerivation?: SqlDerivation;
  referencedColumns?: string[];
  fallbackQuestion?: string;
  defaultExpanded?: boolean;
};

export default function SqlDerivationPanel({
  ontologyMapping,
  pipelineTrace,
  explanation,
  sqlDerivation,
  referencedColumns,
  fallbackQuestion,
  defaultExpanded = true
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showFullTrace, setShowFullTrace] = useState(false);

  const hasMapping =
    !!ontologyMapping &&
    !ontologyMapping.skipped &&
    (!!ontologyMapping.summary?.trim() || !!ontologyMapping.mappings?.length);
  const traceSteps = traceStepsForDerivationPanel(pipelineTrace || [], hasMapping);
  const hasTrace = traceSteps.length > 0;
  const exp = stripAutoRepairExplanationNote((explanation || "").trim());
  const hasDerivationTable = !!sqlDerivation?.ontology_usage?.length;
  const hasReferenced = !!referencedColumns?.length;

  if (!hasMapping && !hasTrace && !exp && !hasDerivationTable) return null;

  const patternLabel = sqlDerivation?.pattern
    ? PATTERN_LABEL[sqlDerivation.pattern] || sqlDerivation.pattern
    : null;

  return (
    <section
      className="mb-3 rounded-lg border border-app-border bg-app-hover/30"
      aria-label="语义到 SQL 推导过程"
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="text-[13px] font-semibold text-app-primary">语义 → SQL 推导过程</span>
        <span className="shrink-0 text-xs text-app-muted">{expanded ? "收起" : "展开"}</span>
      </button>

      {expanded ? (
        <div className="space-y-3 border-t border-app-border px-3 pb-3 pt-2">
          <DerivationStep n={1} title="识别语义（本体指标 / 术语）">
            {hasMapping ? (
              <OntologyMappingBlock mapping={ontologyMapping!} fallbackQuestion={fallbackQuestion} embedded />
            ) : (
              <p className="text-xs text-app-secondary">
                未命中本体知识库中的术语或指标，后续将依赖 Schema 与路由上下文推断 SQL。
              </p>
            )}
          </DerivationStep>

          {hasTrace && traceSteps.some((s) => ["sql_decision", "routing_review", "routing_meta"].includes(s.id)) ? (
            <DerivationStep n={2} title="路由与 SQL 决策">
              <CopilotExecutionTrace
                steps={traceSteps.filter((s) => s.id === "sql_decision" || s.id === "routing_review" || s.id === "routing_meta")}
                compact
                title=""
                variant="plain"
                hideReasoning4Sql
              />
            </DerivationStep>
          ) : null}

          <DerivationStep n={3} title="推导查询逻辑">
            {patternLabel ? (
              <p className="mb-1.5 text-xs text-app-secondary">
                <span className="font-medium text-app-primary">SQL 模式：</span>
                {patternLabel}
              </p>
            ) : null}
            {exp ? <ChatGptStyleBody text={exp} className="text-xs" /> : null}
            {sqlDerivation?.assumptions?.length ? (
              <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-app-muted">
                {sqlDerivation.assumptions.map((a, i) => (
                  <li key={`${i}-${a.slice(0, 24)}`}>{a}</li>
                ))}
              </ul>
            ) : null}
            {hasDerivationTable ? (
              <div className="mt-2 overflow-x-auto rounded border border-app-border">
                <table className="w-full min-w-[280px] border-collapse text-[11px]">
                  <thead>
                    <tr className="border-b border-app-border bg-app-hover">
                      <th className="px-2 py-1 text-left font-medium text-app-secondary">本体资产</th>
                      <th className="px-2 py-1 text-left font-medium text-app-secondary">SQL 角色</th>
                      <th className="px-2 py-1 text-left font-medium text-app-secondary">SQL 片段</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sqlDerivation!.ontology_usage!.map((row, idx) => (
                      <tr key={`${row.ontology_label}-${idx}`} className="border-b border-app-subtle last:border-0">
                        <td className="px-2 py-1.5 align-top text-app-primary">
                          {row.ontology_label || "—"}
                          {row.ontology_kind ? (
                            <span className="ml-1 text-app-muted">({row.ontology_kind})</span>
                          ) : null}
                        </td>
                        <td className="px-2 py-1.5 align-top text-app-secondary">
                          {SQL_ROLE_LABEL[row.sql_role || ""] || row.sql_role || "—"}
                        </td>
                        <td className="px-2 py-1.5 align-top font-mono text-[10px] text-app-primary">
                          {row.sql_fragment || "—"}
                          {row.rationale ? (
                            <p className="mt-0.5 font-sans text-[10px] text-app-muted">{row.rationale}</p>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {hasReferenced && !hasDerivationTable ? (
              <p className="mt-2 text-xs text-app-secondary">
                <span className="font-medium text-app-primary">引用列：</span>
                {referencedColumns!.join("、")}
              </p>
            ) : null}
            {hasTrace ? (
              <div className="mt-2">
                <CopilotExecutionTrace
                  steps={traceSteps.filter((s) => s.id === "reasoning_4" || s.id === "reasoning_7")}
                  compact
                  title=""
                  variant="plain"
                  hideReasoning4Sql
                />
              </div>
            ) : null}
          </DerivationStep>

          {hasTrace && traceSteps.some((s) => !["sql_decision", "routing_review", "routing_meta", "reasoning_4", "reasoning_7"].includes(s.id)) ? (
            <div>
              <button
                type="button"
                className="text-xs text-app-primary underline hover:opacity-80"
                onClick={() => setShowFullTrace((v) => !v)}
              >
                {showFullTrace ? "收起完整推理过程" : "查看完整推理过程"}
              </button>
              {showFullTrace ? (
                <div className="mt-2">
                  <CopilotExecutionTrace
                    steps={traceSteps.filter(
                      (s) => !["sql_decision", "routing_review", "routing_meta", "reasoning_4", "reasoning_7"].includes(s.id)
                    )}
                    compact
                    variant="framed"
                    hideReasoning4Sql
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function DerivationStep({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="relative pl-6">
      <span
        className="absolute left-0 top-0 flex h-5 w-5 items-center justify-center rounded-full bg-app-activeBg text-[10px] font-semibold text-app-primary"
        aria-hidden
      >
        {n}
      </span>
      <h5 className="mb-1.5 text-xs font-semibold text-app-primary">{title}</h5>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
