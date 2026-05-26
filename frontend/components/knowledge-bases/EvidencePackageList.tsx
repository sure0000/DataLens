"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { ModelingStatus } from "../ontology/ModelingPipelineStatus";
import type { EvidencePackage } from "./ingestionTypes";
import { PROCESSING_STATE_LABELS } from "./ingestionTypes";

function downstreamLabel(pkg: EvidencePackage, modeling: ModelingStatus | null): string {
  if (!modeling) return "—";
  const phase = modeling.pipeline_phase;
  const pct = modeling.extraction.progress_percent;
  if (pkg.processing_state === "registered") return "待规范化";
  if (pkg.processing_state === "normalized") return "待索引";
  if (phase === "extracting") return `抽取中 ${pct}%`;
  if (phase === "completed") return "已入图";
  if (phase === "failed") return "抽取失败";
  if (pkg.processing_state === "ready_for_extraction" || pkg.processing_state === "indexed") {
    return "待抽取";
  }
  return PROCESSING_STATE_LABELS[pkg.processing_state] || pkg.processing_state;
}

export default function EvidencePackageList({ kbId }: { kbId: number }) {
  const [packages, setPackages] = useState<EvidencePackage[]>([]);
  const [modeling, setModeling] = useState<ModelingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pkgRes, modelingRes] = await Promise.all([
        api<{ packages: EvidencePackage[] }>(`/api/knowledge-bases/${kbId}/ingestion/packages`),
        api<ModelingStatus>(`/api/ontology/knowledge-bases/${kbId}/modeling/status`).catch(() => null),
      ]);
      setPackages(pkgRes.packages ?? []);
      setModeling(modelingRes);
    } catch {
      setPackages([]);
      setModeling(null);
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (modeling?.extraction?.status !== "running") return;
    const t = setInterval(() => {
      api<ModelingStatus>(`/api/ontology/knowledge-bases/${kbId}/modeling/status`)
        .then(setModeling)
        .catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [kbId, modeling?.extraction?.status]);

  const handleNormalize = async (pkg: EvidencePackage) => {
    if (!pkg.db_id) return;
    setBusyId(pkg.id);
    try {
      await api(`/api/knowledge-bases/${kbId}/ingestion/packages/${pkg.db_id}/normalize`, {
        method: "POST",
      });
      await load();
    } finally {
      setBusyId(null);
    }
  };

  const handleTriggerModeling = async () => {
    setBusyId("modeling");
    try {
      await api(`/api/ontology/knowledge-bases/${kbId}/modeling/runs`, {
        method: "POST",
        body: JSON.stringify({ source_type: "evidence_package_ui", skip_if_running: true }),
      });
      await load();
    } finally {
      setBusyId(null);
    }
  };

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
    <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
      <table className="app-table text-sm">
        <thead>
          <tr>
            <th className="px-3 py-2 text-left">证据包</th>
            <th className="px-3 py-2 text-left">资产类型</th>
            <th className="px-3 py-2 text-left">连接器</th>
            <th className="px-3 py-2 text-left">状态</th>
            <th className="px-3 py-2 text-left">下游</th>
            <th className="px-3 py-2 text-left">标题</th>
            <th className="px-3 py-2 text-left">操作</th>
          </tr>
        </thead>
        <tbody>
          {packages.map((pkg) => (
            <tr key={pkg.id} className="hover:bg-app-hover">
              <td className="px-3 py-2 font-mono text-xs text-app-muted">{pkg.display_id}</td>
              <td className="px-3 py-2">{pkg.asset_label}</td>
              <td className="px-3 py-2 text-app-secondary">{pkg.connector_label}</td>
              <td className="px-3 py-2">
                <span className="inline-flex items-center rounded-full border border-app-border px-2 py-0.5 text-[11px]">
                  {PROCESSING_STATE_LABELS[pkg.processing_state] || pkg.processing_state}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-app-secondary">{downstreamLabel(pkg, modeling)}</td>
              <td className="px-3 py-2 text-app-primary max-w-[200px] truncate" title={pkg.title}>
                {pkg.title}
              </td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-2">
                  {pkg.persistent && pkg.db_id && pkg.processing_state === "registered" ? (
                    <button
                      type="button"
                      className="app-link text-xs"
                      disabled={busyId === pkg.id}
                      onClick={() => handleNormalize(pkg)}
                    >
                      规范化
                    </button>
                  ) : null}
                  {pkg.processing_state === "ready_for_extraction" ||
                  pkg.processing_state === "indexed" ? (
                    <button
                      type="button"
                      className="app-link text-xs"
                      disabled={busyId === "modeling"}
                      onClick={handleTriggerModeling}
                    >
                      触发建模
                    </button>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
