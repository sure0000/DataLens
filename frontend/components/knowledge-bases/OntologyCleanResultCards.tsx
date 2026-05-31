"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  MODELING_DISPLAY_LAYERS,
  buildModelingHash,
  normalizeModelingLayerKey,
  parseModelingHash,
  pickDefaultModelingLayer,
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
  const attributeTotal = layers.attribute?.total ?? 0;
  const semanticLayerTotal =
    (layers.vocabulary?.total ?? 0) +
    (layers.rule?.total ?? 0) +
    (layers["entity-concept"]?.total ?? 0) +
    (layers.relation?.total ?? 0);
  const databaseSchemaOnly = attributeTotal > 0 && semanticLayerTotal === 0;

  useEffect(() => {
    if (!results?.layers || controlledLayer) return;
    if (typeof window !== "undefined") {
      const { layer } = parseModelingHash(window.location.hash);
      if (layer) return;
    }
    const next = pickDefaultModelingLayer(results.layers);
    setInternalLayer(next);
    onLayerChange?.(next);
  }, [results, controlledLayer, onLayerChange]);

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
    return (
      <section className="space-y-4">
        <h2 className="app-section-title">五层清洗结果</h2>
        <div className="app-card space-y-1 p-4 text-sm text-app-muted">
          <p>暂无五层统计数据。</p>
          <p>
            若已完成语义清洗仍无数据，请刷新页面；或在导入源卡片再次触发「语义清洗」后查看属性层。
          </p>
        </div>
      </section>
    );
  }

  const allEmpty = Object.values(layers).every((l) => (l?.total ?? 0) === 0);

  if (allEmpty) {
    return (
      <section className="space-y-4">
        <h2 className="app-section-title">五层清洗结果</h2>
        <div className="app-card space-y-1 p-4 text-sm text-app-muted">
          <p>暂无入图数据。</p>
          <p>
            若已导入数据源：请确认表在「数据源管理」中已完成 AI 分析，并在知识库「设置 → 语义清洗」或导入源卡片上触发；成功后请切换到
            「属性层」查看 businessSummary、semanticDescription 等表/字段语义（数据库源通常不会填充词汇/规则层）。
          </p>
          <p>
            若已导入文档或代码库：请在导入源上触发「语义清洗」以抽取术语、指标与关系。
          </p>
          {results.last_cleaning_at && (
            <p>
              若抽取已结束仍为空，请到「质量与隔离」查看 SHACL 拦截或隔离区记录。
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
                  <p className="text-lg font-semibold tabular-nums text-app-primary">
                    {total}
                    {key === "attribute" && (layer?.physical_total ?? 0) > 0 && (
                      <span className="ml-1 text-[10px] font-normal text-app-muted">
                        表{layer?.physical_total}
                      </span>
                    )}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {databaseSchemaOnly && selectedChip !== "attribute" && (
        <p className="text-sm text-app-muted">
          当前知识库的数据源语义清洗结果在「属性层」（{attributeTotal} 条）。请点击上方属性层芯片查看表/字段摘要。
        </p>
      )}

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
          physicalAttributeTotal={layers.attribute?.physical_total ?? 0}
        />
      )}
    </section>
  );
}
