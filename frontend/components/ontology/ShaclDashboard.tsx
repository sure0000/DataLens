"use client";

import { Icon } from "../AppIcons";
import { QualityStatIcon } from "../icons";

export interface ShaclViolation {
  focusNode: string;
  constraintType: string;
  severity: string;
  message: string;
  affectedProperty?: string;
}

export interface ShaclReport {
  conforms: boolean;
  totalAssertions: number;
  passed: number;
  violations: ShaclViolation[];
  warnings?: ShaclViolation[];
}

interface ShaclDashboardProps {
  report: ShaclReport | null;
  compact?: boolean;
}

const CONSTRAINT_LABELS: Record<string, string> = {
  "http://www.w3.org/ns/shacl#MinCountConstraintComponent": "必填属性",
  "http://www.w3.org/ns/shacl#DatatypeConstraintComponent": "类型约束",
  "http://www.w3.org/ns/shacl#ClassConstraintComponent": "类型约束",
  "http://www.w3.org/ns/shacl#PatternConstraintComponent": "格式校验",
  "http://www.w3.org/ns/shacl#NodeKindConstraintComponent": "节点类型",
};

function shortConstraint(iri: string): string {
  return CONSTRAINT_LABELS[iri] || iri.split("#").pop() || iri;
}

export default function ShaclDashboard({ report, compact = false }: ShaclDashboardProps) {
  if (!report) {
    return (
      <div className="app-card p-6 text-center text-sm text-app-muted">
        <Icon name="shield" className="h-8 w-8 mx-auto mb-2 opacity-40" />
        暂未执行 SHACL 校验。导入三元组时将自动触发校验。
      </div>
    );
  }

  const passRate =
    report.totalAssertions > 0
      ? Math.round((report.passed / report.totalAssertions) * 100)
      : 100;

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className={`grid gap-3 ${compact ? "grid-cols-2" : "sm:grid-cols-3"}`}>
        <StatCard
          label="校验通过率"
          value={`${passRate}%`}
          tone={report.conforms ? "success" : "danger"}
        />
        <StatCard
          label="通过"
          value={String(report.passed)}
          tone="success"
        />
        <StatCard
          label="违规"
          value={String(report.violations.length)}
          tone={report.violations.length > 0 ? "danger" : "success"}
        />
      </div>

      {/* Violations list */}
      {report.violations.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-app-primary flex items-center gap-1.5">
            <QualityStatIcon tone="danger" className="h-3.5 w-3.5" />
            违规详情
          </h4>

          <div className="space-y-1">
            {report.violations.map((v, i) => (
              <div
                key={i}
                className="app-card border border-red-500/20 bg-red-500/5 px-3 py-2.5"
              >
                <div className="flex items-start gap-2">
                  <span className="shrink-0 mt-0.5 text-[10px] font-medium text-red-500 bg-red-500/10 rounded px-1.5 py-0.5">
                    {shortConstraint(v.constraintType)}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm text-app-primary">{v.message}</p>
                    <p className="text-[11px] text-app-muted mt-0.5">
                      <code className="text-app-link">{v.focusNode}</code>
                      {v.affectedProperty && (
                        <>
                          {" → "}
                          <code className="text-app-muted">{v.affectedProperty}</code>
                        </>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {report.warnings && report.warnings.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-app-primary flex items-center gap-1.5">
            <QualityStatIcon tone="warning" className="h-3.5 w-3.5" />
            警告
          </h4>
          <div className="space-y-1">
            {report.warnings.map((w, i) => (
              <div
                key={i}
                className="app-card border border-amber-500/20 bg-amber-500/5 px-3 py-2"
              >
                <p className="text-sm text-app-primary">{w.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "danger" | "muted";
}) {
  const iconTone = tone === "muted" ? "muted" : tone;

  return (
    <div className="app-card p-3 flex items-center gap-3">
      <QualityStatIcon tone={iconTone} className="h-5 w-5" />
      <div>
        <p className="text-lg font-bold text-app-primary">{value}</p>
        <p className="text-[11px] text-app-muted">{label}</p>
      </div>
    </div>
  );
}
