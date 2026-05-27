"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { type ModelingStatus } from "../ontology/ModelingPipelineStatus";
import { type ShaclReport } from "../ontology/ShaclDashboard";
import { api, ApiError, formatApiError } from "../../lib/api";
import {
  buildModelingHash,
  parseModelingHash,
  type ModelingSectionTab,
} from "../../lib/ontologyRoutes";
import type { OntologyMetric, OntologyTerm } from "../../lib/ontologyTypes";
import type { OntologyCleaningResults } from "./types";
import KbModelingQualityPanel from "./KbModelingQualityPanel";
import OntologyCleanResultCards from "./OntologyCleanResultCards";

const MODELING_TABS: { id: ModelingSectionTab; label: string }[] = [
  { id: "layers", label: "五层结果" },
  { id: "quality", label: "质量与隔离" },
];

function defaultModelingTab(
  _cleaningResults: OntologyCleaningResults | null,
): ModelingSectionTab {
  return "layers";
}

export default function KbModelingQualitySection({
  kbId,
  cleaningResults,
  cleaningResultsLoading,
  onPipelineChange,
}: {
  kbId: number;
  cleaningResults: OntologyCleaningResults | null;
  cleaningResultsLoading: boolean;
  onPipelineChange?: () => void;
}) {
  const [modelingTab, setModelingTab] = useState<ModelingSectionTab>(() =>
    defaultModelingTab(cleaningResults),
  );
  const [selectedLayer, setSelectedLayer] = useState<string | null>(null);
  const [modelingStatus, setModelingStatus] = useState<ModelingStatus | null>(null);
  const [quarantineTotal, setQuarantineTotal] = useState(0);
  const [confidenceItems, setConfidenceItems] = useState<{ confidence?: number; name?: string }[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metricsLoaded, setMetricsLoaded] = useState(false);

  useEffect(() => {
    setMetricsLoaded(false);
    setConfidenceItems([]);
    setQuarantineTotal(0);
  }, [kbId]);

  const syncHashToState = useCallback(() => {
    if (typeof window === "undefined") return;
    const parsed = parseModelingHash(window.location.hash);
    setModelingTab(parsed.tab);
    if (parsed.layer) setSelectedLayer(parsed.layer);
  }, []);

  useEffect(() => {
    syncHashToState();
    window.addEventListener("hashchange", syncHashToState);
    return () => window.removeEventListener("hashchange", syncHashToState);
  }, [syncHashToState]);

  useEffect(() => {
    if (!cleaningResultsLoading && cleaningResults && typeof window !== "undefined") {
      const hash = window.location.hash;
      const parsed = parseModelingHash(hash);
      if (!hash.includes("tab=") && !hash.includes("layer=")) {
        setModelingTab(defaultModelingTab(cleaningResults));
      } else {
        setModelingTab(parsed.tab);
      }
    }
  }, [cleaningResults, cleaningResultsLoading]);

  const loadStatus = useCallback(async () => {
    setError(null);
    try {
      const statusRes = await api<ModelingStatus>(
        `/api/ontology/knowledge-bases/${kbId}/modeling/status`,
      ).catch(() => null);
      setModelingStatus(statusRes);
      const qCount = statusRes?.quality?.quarantine_count;
      if (qCount != null) {
        setQuarantineTotal(qCount);
      }
    } catch (e: unknown) {
      setError(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载失败");
    }
  }, [kbId]);

  const loadMetrics = useCallback(async () => {
    if (metricsLoaded) return;
    setMetricsLoading(true);
    try {
      const [termsRes, metricsRes] = await Promise.all([
        api<{ terms: OntologyTerm[] }>(`/api/ontology/knowledge-bases/${kbId}/terms`).catch(() => ({
          terms: [],
        })),
        api<{ metrics: OntologyMetric[] }>(`/api/ontology/knowledge-bases/${kbId}/metrics`).catch(
          () => ({ metrics: [] }),
        ),
      ]);
      setConfidenceItems(
        [...(termsRes.terms ?? []), ...(metricsRes.metrics ?? [])].map((t) => ({
          confidence: t.confidence,
          name: t.name,
        })),
      );
      setMetricsLoaded(true);
    } finally {
      setMetricsLoading(false);
    }
  }, [kbId, metricsLoaded]);

  useEffect(() => {
    if (modelingTab === "quality") {
      void loadStatus();
    }
    if (modelingTab === "quality") {
      void loadMetrics();
    }
  }, [modelingTab, loadStatus, loadMetrics]);

  const setTab = useCallback(
    (tab: ModelingSectionTab) => {
      setModelingTab(tab);
      if (typeof window !== "undefined") {
        const parsed = parseModelingHash(window.location.hash);
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}${buildModelingHash({
            tab,
            layer: tab === "layers" ? selectedLayer : null,
            qualitySub: tab === "quality" ? parsed.qualitySub ?? undefined : undefined,
            quarantine: tab === "quality" && parsed.scrollQuarantine,
          })}`,
        );
      }
    },
    [selectedLayer],
  );

  const handleQuarantineResolve = useCallback(async () => {
    await loadStatus();
    onPipelineChange?.();
  }, [loadStatus, onPipelineChange]);

  const passRate = modelingStatus?.quality?.shacl_pass_rate;
  const syntheticShacl: ShaclReport | null =
    passRate != null
      ? {
          conforms: passRate >= 100 && quarantineTotal === 0,
          totalAssertions: 100,
          passed: Math.round(passRate),
          violations: quarantineTotal
            ? [
                {
                  focusNode: "—",
                  constraintType: "quarantine",
                  severity: "Violation",
                  message: `${quarantineTotal} 条隔离断言`,
                },
              ]
            : [],
        }
      : null;

  const quarantineBadge = useMemo(
    () => (quarantineTotal > 0 ? quarantineTotal : null),
    [quarantineTotal],
  );

  if (error) {
    return <p className="text-sm text-app-danger">{error}</p>;
  }

  return (
    <div className="space-y-4">
      <div
        className="flex flex-wrap gap-1 border-b border-app-border pb-2"
        role="tablist"
        aria-label="建模与质量"
      >
        {MODELING_TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={modelingTab === id}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              modelingTab === id
                ? "bg-app-activeBg text-app-chipText"
                : "text-app-muted hover:bg-app-hover hover:text-app-primary"
            }`}
            onClick={() => setTab(id)}
          >
            {label}
            {id === "quality" && quarantineBadge != null && (
              <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                {quarantineBadge}
              </span>
            )}
          </button>
        ))}
      </div>

      {modelingTab === "layers" && (
        <OntologyCleanResultCards
          results={cleaningResults}
          kbId={kbId}
          loading={cleaningResultsLoading}
          selectedLayer={selectedLayer}
          onLayerChange={setSelectedLayer}
        />
      )}

      {modelingTab === "quality" && (
        <KbModelingQualityPanel
          kbId={kbId}
          shaclReport={syntheticShacl}
          shaclPassRate={passRate}
          quarantineTotal={quarantineTotal}
          confidenceItems={confidenceItems}
          metricsLoading={metricsLoading}
          onQuarantineResolve={() => void handleQuarantineResolve()}
          onQuarantineTotalChange={setQuarantineTotal}
          onRequestMetrics={() => void loadMetrics()}
        />
      )}
    </div>
  );
}
