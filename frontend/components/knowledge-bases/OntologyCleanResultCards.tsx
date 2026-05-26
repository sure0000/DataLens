"use client";

import Link from "next/link";
import type { OntologyCleaningResults } from "./types";

const LAYER_ICONS: Record<string, string> = {
  vocabulary: "📖",
  rule: "📐",
  "entity-concept": "🏷️",
  relation: "🔗",
  attribute: "📋",
};

const LAYER_ROUTES: Record<string, string> = {
  vocabulary: "vocabulary",
  rule: "rule",
  "entity-concept": "entity-concept",
  relation: "relation",
  attribute: "attribute",
};

interface OntologyCleanResultCardsProps {
  results: OntologyCleaningResults | null;
  kbId: number;
  loading: boolean;
}

export default function OntologyCleanResultCards({
  results,
  kbId,
  loading,
}: OntologyCleanResultCardsProps) {
  if (loading) {
    return (
      <section className="space-y-4">
        <h2 className="app-section-title">本体建模清洗结果</h2>
        <p className="text-sm text-app-muted">加载中…</p>
      </section>
    );
  }

  if (!results || !results.layers || Object.keys(results.layers).length === 0) {
    return null;
  }

  const layers = results.layers;
  const allEmpty = Object.values(layers).every((l) => l.total === 0);

  if (allEmpty) {
    return (
      <section className="space-y-4">
        <h2 className="app-section-title">本体建模清洗结果</h2>
        <p className="text-sm text-app-muted">
          暂无本体建模数据，请先在导入源上点击「语义清洗」触发处理。
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="app-section-title">本体建模清洗结果</h2>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {Object.entries(layers).map(([key, layer]) => {
          const routeKey = LAYER_ROUTES[key] || key;
          return (
            <Link
              key={key}
              href={`/knowledge-bases/${kbId}/ontology?tab=governance`}
              className="app-card app-card-interactive flex flex-col gap-2 p-4 no-underline"
            >
              <div className="flex items-center gap-2">
                <span className="text-lg">{LAYER_ICONS[key] || "📦"}</span>
                <span className="font-semibold text-sm text-app-primary">{layer.label}</span>
              </div>
              <p className="text-xs text-app-muted">{layer.description}</p>
              <div className="mt-auto flex items-baseline gap-1">
                <span className="text-2xl font-bold text-app-primary">{layer.total}</span>
                <span className="text-xs text-app-muted">条记录</span>
              </div>
              {layer.total > 0 && layer.items.slice(0, 2).some((it) => it.label) && (
                <div className="text-[11px] text-app-muted space-y-0.5 mt-1">
                  {layer.items.slice(0, 2).map((it, i) => (
                    <p key={i} className="truncate">
                      {it.label || it.s || "—"}
                    </p>
                  ))}
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
