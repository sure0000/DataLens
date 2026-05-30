/** Canonical URLs for ontology browse and KB modeling-quality pages. */

export type OntologyBrowseTab = "overview" | "semantics" | "assets" | "graph";

export type ModelingSectionTab = "layers" | "quality";

export type QualitySubTab = "todo" | "metrics";

/** Product five-layer chip order for semantic assets browse. */
export const SEMANTIC_ASSET_LAYERS = [
  "entity-concept",
  "relation",
  "rule",
  "attribute",
  "vocabulary",
] as const;

export type SemanticAssetLayer = (typeof SEMANTIC_ASSET_LAYERS)[number];

/** Product five-layer chip order (dimension is a sub-view of entity-concept). */
export const MODELING_DISPLAY_LAYERS = [
  "entity-concept",
  "relation",
  "rule",
  "attribute",
  "vocabulary",
] as const;

export type ModelingDisplayLayer = (typeof MODELING_DISPLAY_LAYERS)[number];

const BROWSE_TABS = new Set<OntologyBrowseTab>([
  "overview",
  "semantics",
  "assets",
  "graph",
]);

const MODELING_TABS = new Set<ModelingSectionTab>(["layers", "quality"]);

const QUALITY_SUB_TABS = new Set<QualitySubTab>(["todo", "metrics"]);

const LAYER_ALIASES: Record<string, string> = {
  entity_concept: "entity-concept",
  entity: "entity-concept",
  concept: "entity-concept",
};

export function normalizeModelingLayerKey(key: string | null | undefined): string | null {
  if (!key) return null;
  const normalized = LAYER_ALIASES[key] ?? key;
  if (
    SEMANTIC_ASSET_LAYERS.includes(normalized as SemanticAssetLayer) ||
    MODELING_DISPLAY_LAYERS.includes(normalized as ModelingDisplayLayer) ||
    normalized === "dimension"
  ) {
    return normalized;
  }
  return null;
}

export function normalizeQualitySubTab(value: string | null | undefined): QualitySubTab | null {
  if (!value) return null;
  return QUALITY_SUB_TABS.has(value as QualitySubTab) ? (value as QualitySubTab) : null;
}

export function isOntologyBrowseTab(tab: string | null | undefined): tab is OntologyBrowseTab {
  if (tab == null) return false;
  if (tab === "expert") return false;
  return BROWSE_TABS.has(tab as OntologyBrowseTab);
}

/** Semantic assets browse for a business domain (optional KB filter). */
export function ontologyUrl(options?: {
  domainId?: number;
  kbId?: number;
  tab?: OntologyBrowseTab;
  layer?: string;
  entitySub?: "concept" | "dimension";
}): string {
  if (options?.domainId != null && Number.isFinite(options.domainId)) {
    return domainOntologyUrl(options.domainId, {
      kbId: options.kbId,
      tab: options.tab,
      layer: options.layer,
      entitySub: options.entitySub,
    });
  }
  const params = new URLSearchParams();
  if (options?.kbId != null && Number.isFinite(options.kbId)) {
    params.set("kb", String(options.kbId));
  }
  if (options?.layer) {
    params.set("layer", options.layer);
  } else if (options?.tab && options.tab !== "overview") {
    params.set("tab", options.tab);
  }
  if (options?.entitySub && options.entitySub !== "concept") {
    params.set("entity", options.entitySub);
  }
  const q = params.toString();
  return q ? `/ontology?${q}` : "/ontology";
}

export function domainOntologyUrl(
  domainId: number,
  options?: {
    kbId?: number;
    tab?: OntologyBrowseTab;
    layer?: string;
    entitySub?: "concept" | "dimension";
  },
): string {
  const params = new URLSearchParams();
  if (options?.kbId != null && Number.isFinite(options.kbId)) {
    params.set("kb", String(options.kbId));
  }
  if (options?.layer) {
    params.set("layer", options.layer);
  } else if (options?.tab && options.tab !== "overview") {
    params.set("tab", options.tab);
  }
  if (options?.entitySub && options.entitySub !== "concept") {
    params.set("entity", options.entitySub);
  }
  const q = params.toString();
  const base = `/business-domains/${domainId}/ontology`;
  return q ? `${base}?${q}` : base;
}

export type ModelingHashState = {
  tab: ModelingSectionTab;
  layer: string | null;
  qualitySub: QualitySubTab | null;
  scrollQuarantine: boolean;
};

export function parseModelingHash(hash: string): ModelingHashState {
  const raw = hash.replace(/^#/, "").trim();
  if (!raw || raw === "modeling") {
    return { tab: "layers", layer: null, qualitySub: null, scrollQuarantine: false };
  }
  if (raw === "quarantine") {
    return { tab: "quality", layer: null, qualitySub: "todo", scrollQuarantine: true };
  }

  const qIdx = raw.indexOf("?");
  const anchor = qIdx >= 0 ? raw.slice(0, qIdx) : raw;
  const query = qIdx >= 0 ? raw.slice(qIdx + 1) : "";
  const params = new URLSearchParams(query);

  if (anchor === "quarantine") {
    return { tab: "quality", layer: null, qualitySub: "todo", scrollQuarantine: true };
  }

  const tabRaw = params.get("tab") ?? params.get("modeling-tab");
  const tab =
    tabRaw && MODELING_TABS.has(tabRaw as ModelingSectionTab)
      ? (tabRaw as ModelingSectionTab)
      : anchor === "modeling"
        ? "layers"
        : "layers";

  const layer = normalizeModelingLayerKey(
    params.get("layer") ?? params.get("modeling-layer"),
  );

  const qualitySub = normalizeQualitySubTab(params.get("quality"));

  const scrollQuarantine =
    params.get("quarantine") === "1" || anchor === "quarantine" || raw === "quarantine";

  return {
    tab,
    layer,
    qualitySub: scrollQuarantine && !qualitySub ? "todo" : qualitySub,
    scrollQuarantine,
  };
}

export function buildModelingHash(options?: {
  tab?: ModelingSectionTab;
  layer?: string | null;
  qualitySub?: QualitySubTab | null;
  quarantine?: boolean;
}): string {
  if (options?.quarantine) {
    return "#modeling?tab=quality&quality=todo&quarantine=1";
  }
  const params = new URLSearchParams();
  if (options?.tab && options.tab !== "layers") {
    params.set("tab", options.tab);
  }
  if (options?.layer) {
    params.set("layer", options.layer);
  }
  if (options?.qualitySub) {
    params.set("quality", options.qualitySub);
  }
  const q = params.toString();
  if (!q && (!options?.tab || options.tab === "layers")) {
    return options?.layer ? `#modeling?layer=${encodeURIComponent(options.layer)}` : "#modeling";
  }
  return `#modeling?${q}`;
}

export function kbModelingSectionUrl(
  kbId: number,
  options?: {
    tab?: ModelingSectionTab;
    layer?: string;
    qualitySub?: QualitySubTab;
    quarantine?: boolean;
  },
): string {
  return `/knowledge-bases/${kbId}/modeling-quality${buildModelingHash(options)}`;
}

export function kbModelingLayerUrl(kbId: number, layerKey: string): string {
  return `/knowledge-bases/${kbId}/ontology/${encodeURIComponent(layerKey)}`;
}

export function parseKbIdFromSearchParams(
  searchParams: URLSearchParams | { get: (key: string) => string | null },
): number | null {
  const raw = searchParams.get("kb");
  if (!raw) return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
}

export function parseKbFilterFromSearchParams(
  searchParams: URLSearchParams | { get: (key: string) => string | null },
): number | null {
  return parseKbIdFromSearchParams(searchParams);
}
