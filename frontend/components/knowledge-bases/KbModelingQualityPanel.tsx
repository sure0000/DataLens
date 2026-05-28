"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import ConfidenceDistribution from "../ontology/ConfidenceDistribution";
import QuarantineList from "../ontology/QuarantineList";
import ShaclDashboard, { type ShaclReport } from "../ontology/ShaclDashboard";
import {
  buildModelingHash,
  parseModelingHash,
  type QualitySubTab,
} from "../../lib/ontologyRoutes";

const QUALITY_SUB_TABS: { id: QualitySubTab; label: string }[] = [
  { id: "todo", label: "待办" },
  { id: "metrics", label: "指标" },
];

function defaultQualitySub(quarantineCount: number): QualitySubTab {
  return quarantineCount > 0 ? "todo" : "metrics";
}

interface KbModelingQualityPanelProps {
  kbId: number;
  shaclReport: ShaclReport | null;
  shaclPassRate: number | null | undefined;
  quarantineTotal: number;
  confidenceItems: Array<{ confidence?: number; name?: string }>;
  metricsLoading: boolean;
  onQuarantineResolve: () => void;
  onQuarantineTotalChange: (total: number) => void;
  onRequestMetrics: () => void;
}

export default function KbModelingQualityPanel({
  kbId,
  shaclReport,
  shaclPassRate,
  quarantineTotal,
  confidenceItems,
  metricsLoading,
  onQuarantineResolve,
  onQuarantineTotalChange,
  onRequestMetrics,
}: KbModelingQualityPanelProps) {
  const [qualitySub, setQualitySub] = useState<QualitySubTab>(() => defaultQualitySub(quarantineTotal));

  const lowConfidenceCount = useMemo(
    () => confidenceItems.filter((i) => (i.confidence ?? 100) < 50).length,
    [confidenceItems],
  );

  const syncFromHash = useCallback(() => {
    if (typeof window === "undefined") return;
    const parsed = parseModelingHash(window.location.hash);
    if (parsed.tab !== "quality") return;
    if (parsed.qualitySub) {
      setQualitySub(parsed.qualitySub);
    } else {
      setQualitySub(defaultQualitySub(quarantineTotal));
    }
    if (parsed.scrollQuarantine) {
      requestAnimationFrame(() => {
        document.getElementById("quarantine")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }, [quarantineTotal]);

  useEffect(() => {
    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, [syncFromHash]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (quarantineTotal <= 0) return;
    const parsed = parseModelingHash(window.location.hash);
    if (parsed.tab === "quality" && !parsed.qualitySub) {
      setQualitySub("todo");
    }
  }, [quarantineTotal]);

  useEffect(() => {
    if (qualitySub === "metrics") {
      onRequestMetrics();
    }
  }, [qualitySub, onRequestMetrics]);

  const setSubTab = useCallback((sub: QualitySubTab) => {
    setQualitySub(sub);
    if (typeof window !== "undefined") {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${buildModelingHash({ tab: "quality", qualitySub: sub })}`,
      );
    }
  }, []);

  const passDisplay =
    shaclPassRate != null
      ? `${Math.round(shaclPassRate)}%`
      : shaclReport && shaclReport.totalAssertions > 0
        ? `${Math.round((shaclReport.passed / shaclReport.totalAssertions) * 100)}%`
        : "—";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <button
          type="button"
          className="app-card app-card-interactive p-3 text-left"
          onClick={() => setSubTab("metrics")}
        >
          <p className="text-[11px] text-app-muted">SHACL 通过率</p>
          <p className="text-lg font-semibold text-app-primary tabular-nums">{passDisplay}</p>
        </button>
        <button
          type="button"
          className={`app-card app-card-interactive p-3 text-left ${
            quarantineTotal > 0 ? "border-amber-500/40" : ""
          }`}
          onClick={() => setSubTab("todo")}
        >
          <p className="text-[11px] text-app-muted">隔离待办</p>
          <p className="text-lg font-semibold text-app-primary tabular-nums">{quarantineTotal}</p>
        </button>
        <button
          type="button"
          className="app-card app-card-interactive p-3 text-left"
          onClick={() => setSubTab("metrics")}
        >
          <p className="text-[11px] text-app-muted">低置信 (&lt;50)</p>
          <p className="text-lg font-semibold text-app-primary tabular-nums">
            {metricsLoading && confidenceItems.length === 0 ? "…" : lowConfidenceCount}
          </p>
        </button>
      </div>

      <div className="flex gap-1 border-b border-app-border pb-2" role="tablist" aria-label="质量与隔离">
        {QUALITY_SUB_TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={qualitySub === id}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              qualitySub === id
                ? "bg-app-activeBg text-app-chipText"
                : "text-app-muted hover:bg-app-hover hover:text-app-primary"
            }`}
            onClick={() => setSubTab(id)}
          >
            {label}
            {id === "todo" && quarantineTotal > 0 && (
              <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                {quarantineTotal}
              </span>
            )}
          </button>
        ))}
      </div>

      {qualitySub === "todo" && (
        <div id="quarantine" className="app-card scroll-mt-24 p-4">
          <h3 className="app-section-title mb-3">隔离区</h3>
          <QuarantineList
            kbId={kbId}
            onResolve={onQuarantineResolve}
            onTotalChange={onQuarantineTotalChange}
          />
        </div>
      )}

      {qualitySub === "metrics" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="app-card p-4">
            <h3 className="app-section-title mb-3">SHACL 校验</h3>
            <ShaclDashboard report={shaclReport} compact />
          </div>
          <div className="app-card p-4">
            <h3 className="app-section-title mb-3">置信度分布</h3>
            {metricsLoading && confidenceItems.length === 0 ? (
              <p className="text-sm text-app-muted py-4">加载置信度数据…</p>
            ) : (
              <ConfidenceDistribution items={confidenceItems} title="提取质量" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
