"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { ModelingStatus } from "../ontology/ModelingPipelineStatus";
import type { EvidencePackage } from "./ingestionTypes";
import { CONNECTOR_LABELS, PROCESSING_STATE_LABELS } from "./ingestionTypes";
import {
  chipError,
  chipInfo,
  chipNeutral,
  chipProgress,
  chipSuccess,
  chipWarning,
} from "../../lib/themeClasses";

/** 连接器图标悬停说明：仅显示连接器中文名 */
function connectorTooltip(pkg: EvidencePackage): string {
  const fromApi = (pkg.connector_label || "").trim();
  const fallback = CONNECTOR_LABELS[pkg.connector as keyof typeof CONNECTOR_LABELS];
  return fromApi || fallback || pkg.connector;
}

function ConnectorIcon({ connector, className = "text-app-secondary" }: { connector: string; className?: string }) {
  const props = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: `shrink-0 ${className}`,
    "aria-hidden": true,
  };

  switch (connector) {
    case "git":
      return (
        <svg {...props}>
          <path d="M6 3v12" />
          <circle cx="6" cy="18" r="3" />
          <path d="M18 6v9" />
          <circle cx="18" cy="18" r="3" />
          <path d="M6 15a9 9 0 009-9" />
        </svg>
      );
    case "database":
      return (
        <svg {...props}>
          <ellipse cx="12" cy="6" rx="8" ry="3" />
          <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
          <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
        </svg>
      );
    case "api":
      return (
        <svg {...props}>
          <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
        </svg>
      );
    case "manual":
      return (
        <svg {...props}>
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
      );
    case "ttl":
      return (
        <svg {...props}>
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
          <line x1="12" y1="22.08" x2="12" y2="12" />
        </svg>
      );
    case "file":
    default:
      return (
        <svg {...props}>
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      );
  }
}

function AssetTypeCell({ pkg }: { pkg: EvidencePackage }) {
  const tip = connectorTooltip(pkg);
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span
        className="group relative inline-flex h-7 w-7 shrink-0 cursor-help items-center justify-center rounded-md border border-app-border bg-[var(--app-surface)]"
        aria-label={tip}
      >
        <ConnectorIcon connector={pkg.connector} />
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-[calc(100%+6px)] left-1/2 z-20 hidden w-max max-w-[240px] -translate-x-1/2 rounded-md border border-app-border bg-[var(--app-surface)] px-2 py-1 text-[11px] leading-snug text-app-primary shadow-md group-hover:block"
        >
          {tip}
        </span>
      </span>
      <span className="truncate text-app-primary">{pkg.asset_label}</span>
    </div>
  );
}

function formatRegisteredAt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function mergedStatusChip(
  pkg: EvidencePackage,
  modeling: ModelingStatus | null,
): { text: string; className: string } {
  if (modeling) {
    const phase = modeling.pipeline_phase;
    const pct = modeling.extraction.progress_percent;
    if (phase === "extracting") {
      return { text: `抽取中 ${pct}%`, className: chipProgress };
    }
    if (phase === "completed") {
      return { text: "已入图", className: chipSuccess };
    }
    if (phase === "failed") {
      return { text: "抽取失败", className: chipError };
    }
    if (pkg.processing_state === "registered") {
      return { text: "待规范化", className: chipWarning };
    }
    if (pkg.processing_state === "normalized") {
      return { text: "待索引", className: chipWarning };
    }
    if (pkg.processing_state === "ready_for_extraction" || pkg.processing_state === "indexed") {
      return { text: "待抽取", className: chipInfo };
    }
  }

  const text = PROCESSING_STATE_LABELS[pkg.processing_state] || pkg.processing_state;
  const classByState: Record<string, string> = {
    registered: `${chipNeutral} text-app-muted`,
    normalized: chipInfo,
    indexed: chipSuccess,
    ready_for_extraction: chipInfo,
  };
  return {
    text,
    className: classByState[pkg.processing_state] ?? `${chipNeutral} text-app-secondary`,
  };
}

export default function EvidencePackageList({ kbId }: { kbId: number }) {
  const [packages, setPackages] = useState<EvidencePackage[]>([]);
  const [modeling, setModeling] = useState<ModelingStatus | null>(null);
  const [loading, setLoading] = useState(true);

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
            <th className="px-3 py-2 text-left">标题</th>
            <th className="px-3 py-2 text-left">类型</th>
            <th className="px-3 py-2 text-left">状态</th>
            <th className="px-3 py-2 text-left whitespace-nowrap">登记时间</th>
          </tr>
        </thead>
        <tbody>
          {packages.map((pkg) => {
            const status = mergedStatusChip(pkg, modeling);
            return (
            <tr key={pkg.id} className="hover:bg-app-hover">
              <td className="px-3 py-2 font-mono text-xs text-app-muted whitespace-nowrap">{pkg.display_id}</td>
              <td className="px-3 py-2 text-app-primary max-w-[240px] truncate" title={pkg.title}>
                {pkg.title}
              </td>
              <td className="px-3 py-2 max-w-[180px]">
                <AssetTypeCell pkg={pkg} />
              </td>
              <td className="px-3 py-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${status.className}`}
                >
                  {status.text}
                </span>
              </td>
              <td className="px-3 py-2 whitespace-nowrap text-xs text-app-secondary">
                {formatRegisteredAt(pkg.created_at)}
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
