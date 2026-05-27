"use client";

import { useCallback, useEffect, useState } from "react";
import ConceptHierarchyTree, { type HierarchyNode } from "../ontology/ConceptHierarchyTree";
import ConfidenceDistribution from "../ontology/ConfidenceDistribution";
import ModelingPipelineStatus, { type ModelingStatus } from "../ontology/ModelingPipelineStatus";
import QuarantineList, { type QuarantineItem } from "../ontology/QuarantineList";
import ShaclDashboard, { type ShaclReport } from "../ontology/ShaclDashboard";
import { api, ApiError, formatApiError } from "../../lib/api";
import type { OntologyMetric, OntologyTerm } from "../../lib/ontologyTypes";
import type { OntologyCleaningResults } from "./types";
import OntologyCleanResultCards from "./OntologyCleanResultCards";

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
  const [modelingStatus, setModelingStatus] = useState<ModelingStatus | null>(null);
  const [quarantineItems, setQuarantineItems] = useState<QuarantineItem[]>([]);
  const [hierarchyRoots, setHierarchyRoots] = useState<HierarchyNode[]>([]);
  const [shaclReport, setShaclReport] = useState<ShaclReport | null>(null);
  const [confidenceItems, setConfidenceItems] = useState<{ confidence?: number; name?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningModeling, setRunningModeling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, quarantineRes, hierarchyRes, termsRes, metricsRes] = await Promise.all([
        api<ModelingStatus>(`/api/ontology/knowledge-bases/${kbId}/modeling/status`).catch(() => null),
        api<{ items?: QuarantineItem[] }>(`/api/ontology/knowledge-bases/${kbId}/quarantine`).catch(() => ({
          items: [],
        })),
        api<{ roots?: HierarchyNode[] }>(
          `/api/ontology/knowledge-bases/${kbId}/views/hierarchy`,
        ).catch(() => ({ roots: [] })),
        api<{ terms: OntologyTerm[] }>(`/api/ontology/knowledge-bases/${kbId}/terms`).catch(() => ({
          terms: [],
        })),
        api<{ metrics: OntologyMetric[] }>(`/api/ontology/knowledge-bases/${kbId}/metrics`).catch(
          () => ({ metrics: [] }),
        ),
      ]);
      setModelingStatus(statusRes);
      setQuarantineItems(quarantineRes.items ?? []);
      setHierarchyRoots(hierarchyRes.roots ?? []);
      setShaclReport(null);
      setConfidenceItems(
        [...(termsRes.terms ?? []), ...(metricsRes.metrics ?? [])].map((t) => ({
          confidence: t.confidence,
          name: t.name,
        })),
      );
    } catch (e: unknown) {
      setError(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (modelingStatus?.extraction?.status !== "running") return;
    const t = setInterval(() => {
      api<ModelingStatus>(`/api/ontology/knowledge-bases/${kbId}/modeling/status`)
        .then(setModelingStatus)
        .catch(() => {});
    }, 4000);
    return () => clearInterval(t);
  }, [kbId, modelingStatus?.extraction?.status]);

  async function handleRunModeling() {
    setRunningModeling(true);
    try {
      await api(`/api/ontology/knowledge-bases/${kbId}/modeling/runs`, {
        method: "POST",
        body: JSON.stringify({ source_type: "manual_ui", skip_if_running: true }),
      });
      const statusRes = await api<ModelingStatus>(
        `/api/ontology/knowledge-bases/${kbId}/modeling/status`,
      );
      setModelingStatus(statusRes);
      onPipelineChange?.();
    } finally {
      setRunningModeling(false);
    }
  }

  const passRate = modelingStatus?.quality?.shacl_pass_rate;
  const syntheticShacl: ShaclReport | null =
    passRate != null
      ? {
          conforms: passRate >= 100 && quarantineItems.length === 0,
          totalAssertions: 100,
          passed: Math.round(passRate),
          violations: quarantineItems.length
            ? [
                {
                  focusNode: "—",
                  constraintType: "quarantine",
                  severity: "Violation",
                  message: `${quarantineItems.length} 条隔离断言`,
                },
              ]
            : [],
        }
      : shaclReport;

  if (error) {
    return <p className="text-sm text-app-danger">{error}</p>;
  }

  return (
    <div className="space-y-6">
      <ModelingPipelineStatus
        status={modelingStatus}
        loading={loading}
        onRunModeling={handleRunModeling}
        runningModeling={runningModeling}
      />
      <OntologyCleanResultCards
        results={cleaningResults}
        kbId={kbId}
        loading={cleaningResultsLoading}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="app-card p-4">
          <h3 className="app-section-title mb-3">SHACL 校验</h3>
          <ShaclDashboard report={syntheticShacl} compact />
        </div>
        <div className="app-card p-4">
          <h3 className="app-section-title mb-3">置信度分布</h3>
          <ConfidenceDistribution items={confidenceItems} title="提取质量" />
        </div>
      </div>
      <div className="app-card p-4">
        <h3 className="app-section-title mb-3">概念层级</h3>
        <ConceptHierarchyTree roots={hierarchyRoots} />
      </div>
      <div id="quarantine" className="app-card scroll-mt-24 p-4">
        <h3 className="app-section-title mb-3">隔离区</h3>
        <QuarantineList kbId={kbId} items={quarantineItems} onResolve={load} />
      </div>
    </div>
  );
}
