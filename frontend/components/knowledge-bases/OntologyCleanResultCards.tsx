"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  MODELING_DISPLAY_LAYERS,
  buildModelingHash,
  normalizeModelingLayerKey,
  parseModelingHash,
  type ModelingDisplayLayer,
} from "../../lib/ontologyRoutes";
import type { OntologyCleaningResults } from "./types";
import ConceptHierarchyPanel from "./ConceptHierarchyPanel";
import OntologyLayerDetailPanel from "./OntologyLayerDetailPanel";

const LAYER_ICONS: Record<string, string> = {
  vocabulary: "📖",
  rule: "📐",
  "entity-concept": "🏷️",
  relation: "🔗",
  attribute: "📋",
  dimension: "📊",
};

type EntitySubView = "concept" | "dimension";
type ConceptViewMode = "list" | "tree";

interface OntologyCleanResultCardsProps {
  results: OntologyCleaningResults | null;
  kbId: number;
  loading: boolean;
  selectedLayer?: string | null;
  onLayerChange?: (layerKey: string) => void;
}

export default function OntologyCleanResultCards({
  results,
  kbId,
  loading,
  selectedLayer: controlledLayer,
  onLayerChange,
}: OntologyCleanResultCardsProps) {
  const [internalLayer, setInternalLayer] = useState<ModelingDisplayLayer>("vocabulary");
  const [entitySubView, setEntitySubView] = useState<EntitySubView>("concept");
  const [conceptViewMode, setConceptViewMode] = useState<ConceptViewMode>("list");

  const selectedChip =
    (controlledLayer
      ? normalizeModelingLayerKey(controlledLayer)
      : null) ?? internalLayer;

  const setSelectedChip = useCallback(
    (key: ModelingDisplayLayer) => {
      setInternalLayer(key);
      setEntitySubView("concept");
      setConceptViewMode("list");
      onLayerChange?.(key);
      if (typeof window !== "undefined") {
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}${buildModelingHash({ tab: "layers", layer: key })}`,
        );
      }
    },
    [onLayerChange],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const syncFromHash = () => {
      const { layer } = parseModelingHash(window.location.hash);
      if (layer === "dimension") {
        setInternalLayer("entity-concept");
        setEntitySubView("dimension");
        onLayerChange?.("entity-concept");
        return;
      }
      const normalized = normalizeModelingLayerKey(layer);
      if (
        normalized &&
        MODELING_DISPLAY_LAYERS.includes(normalized as ModelingDisplayLayer)
      ) {
        setInternalLayer(normalized as ModelingDisplayLayer);
        setEntitySubView("concept");
        onLayerChange?.(normalized);
      }
    };
    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, [onLayerChange]);

  const layers = results?.layers ?? {};
  const dimensionTotal = layers.dimension?.total ?? 0;

  const activeDetailKey = useMemo(() => {
    if (selectedChip === "entity-concept" && entitySubView === "dimension") {
      return "dimension";
    }
    return selectedChip;
  }, [selectedChip, entitySubView]);

  const activeMeta = layers[activeDetailKey];

  if (loading) {
    return (
      <section className="space-y-4">
        <h2 className="app-section-title">五层清洗结果</h2>
        <div className="app-card p-4">
          <p className="text-sm text-app-muted">加载中…</p>
        </div>
      </section>
    );
  }

  if (!results || !results.layers || Object.keys(results.layers).length === 0) {
    return null;
  }

  const allEmpty = Object.values(layers).every((l) => (l?.total ?? 0) === 0);

  if (allEmpty) {
    return (
      <section className="space-y-4">
        <h2 className="app-section-title">五层清洗结果</h2>
        <div className="app-card space-y-1 p-4 text-sm text-app-muted">
          <p>暂无清洗结果，请先在导入源上点击「语义清洗」触发处理。</p>
          {results.last_cleaning_at && (
            <p>
              若抽取已结束仍为空，请到「流水线」查看入图步骤是否失败（常见原因：SHACL 校验拦截）。
            </p>
          )}
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="app-section-title">五层清洗结果</h2>
        {results.last_cleaning_at && (
          <span className="text-[11px] text-app-muted">
            上次完成 {new Date(results.last_cleaning_at).toLocaleString()}
          </span>
        )}
      </div>

      <div className="app-card p-3 sm:p-4">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {MODELING_DISPLAY_LAYERS.map((key) => {
            const layer = layers[key];
            const total = layer?.total ?? 0;
            const isActive = selectedChip === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setSelectedChip(key)}
                className={`group flex min-h-20 flex-col items-start justify-between rounded-xl border px-3 py-2 text-left transition-colors ${
                  isActive
                    ? "border-app-activeBorder bg-app-activeBg"
                    : "border-app-border bg-app-surface hover:bg-app-hover"
                }`}
                aria-pressed={isActive}
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-md text-sm ${
                      isActive ? "bg-app-surface text-app-primary" : "bg-app-surfaceMuted text-app-secondary"
                    }`}
                  >
                    {LAYER_ICONS[key] || "📦"}
                  </span>
                  {key === "entity-concept" && dimensionTotal > 0 && (
                    <span
                      className="rounded-full border border-app-border px-1.5 py-0.5 text-[10px] text-app-muted"
                      title={`含 ${dimensionTotal} 个维度`}
                    >
                      +{dimensionTotal}维
                    </span>
                  )}
                </div>
                <div className="space-y-0.5">
                  <p className={`text-xs font-medium ${isActive ? "text-app-primary" : "text-app-secondary"}`}>
                    {layer?.label ?? key}
                  </p>
                  <p className="text-lg font-semibold tabular-nums text-app-primary">{total}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {selectedChip === "entity-concept" && (
        <div className="app-card flex flex-wrap items-center gap-2 p-3">
          {dimensionTotal > 0 && (
            <div className="inline-flex rounded-lg border border-app-border bg-app-surface p-1">
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  entitySubView === "concept"
                    ? "bg-app-activeBg text-app-chipText font-medium"
                    : "text-app-muted hover:bg-app-hover"
                }`}
                onClick={() => {
                  setEntitySubView("concept");
                  setConceptViewMode("list");
                }}
              >
                概念 ({layers["entity-concept"]?.total ?? 0})
              </button>
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  entitySubView === "dimension"
                    ? "bg-app-activeBg text-app-chipText font-medium"
                    : "text-app-muted hover:bg-app-hover"
                }`}
                onClick={() => {
                  setEntitySubView("dimension");
                  if (typeof window !== "undefined") {
                    window.history.replaceState(
                      null,
                      "",
                      `${window.location.pathname}${buildModelingHash({ tab: "layers", layer: "dimension" })}`,
                    );
                  }
                }}
              >
                维度 ({dimensionTotal})
              </button>
            </div>
          )}
          {entitySubView === "concept" && (
            <div className="ml-auto inline-flex rounded-lg border border-app-border bg-app-surface p-1">
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  conceptViewMode === "list"
                    ? "bg-app-activeBg text-app-chipText font-medium"
                    : "text-app-muted hover:bg-app-hover"
                }`}
                onClick={() => setConceptViewMode("list")}
              >
                列表
              </button>
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  conceptViewMode === "tree"
                    ? "bg-app-activeBg text-app-chipText font-medium"
                    : "text-app-muted hover:bg-app-hover"
                }`}
                onClick={() => setConceptViewMode("tree")}
              >
                树形
              </button>
            </div>
          )}
        </div>
      )}

      {selectedChip === "entity-concept" &&
      entitySubView === "concept" &&
      conceptViewMode === "tree" ? (
        <ConceptHierarchyPanel kbId={kbId} />
      ) : (
        <OntologyLayerDetailPanel
          kbId={kbId}
          layerKey={activeDetailKey}
          layerLabel={activeMeta?.label}
          layerDescription={activeMeta?.description}
          expectedTotal={activeMeta?.total}
        />
      )}
    </section>
  );
}
