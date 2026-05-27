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
        <p className="text-sm text-app-muted">加载中…</p>
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
        <div className="space-y-1 text-sm text-app-muted">
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
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="app-section-title">五层清洗结果</h2>
        {results.last_cleaning_at && (
          <span className="text-[11px] text-app-muted">
            上次完成 {new Date(results.last_cleaning_at).toLocaleString()}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {MODELING_DISPLAY_LAYERS.map((key) => {
          const layer = layers[key];
          const total = layer?.total ?? 0;
          const isActive = selectedChip === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setSelectedChip(key)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? "border-app-activeBorder bg-app-activeBg text-app-chipText"
                  : "border-app-border bg-app-surface text-app-secondary hover:bg-app-hover"
              }`}
            >
              <span>{LAYER_ICONS[key] || "📦"}</span>
              <span>{layer?.label ?? key}</span>
              <span className="tabular-nums font-semibold">{total}</span>
              {key === "entity-concept" && dimensionTotal > 0 && (
                <span
                  className="ml-0.5 rounded bg-app-surfaceMuted px-1 py-0.5 text-[10px] text-app-muted"
                  title={`含 ${dimensionTotal} 个维度`}
                >
                  +{dimensionTotal}维
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selectedChip === "entity-concept" && (
        <div className="flex flex-wrap items-center gap-2">
          {dimensionTotal > 0 && (
            <div className="flex gap-1">
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 text-xs ${
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
                className={`rounded-md px-2.5 py-1 text-xs ${
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
            <div className="flex gap-1 ml-auto">
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 text-xs ${
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
                className={`rounded-md px-2.5 py-1 text-xs ${
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
