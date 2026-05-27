/** Canonical URLs for ontology browse (modeling progress lives on knowledge-base detail). */

export type OntologyBrowseTab = "overview" | "semantics" | "assets" | "graph" | "expert";

const BROWSE_TABS = new Set<OntologyBrowseTab>([
  "overview",
  "semantics",
  "assets",
  "graph",
  "expert",
]);

export function isOntologyBrowseTab(tab: string | null | undefined): tab is OntologyBrowseTab {
  return tab != null && BROWSE_TABS.has(tab as OntologyBrowseTab);
}

export function ontologyUrl(options?: { kbId?: number; tab?: OntologyBrowseTab }): string {
  const params = new URLSearchParams();
  if (options?.kbId != null && Number.isFinite(options.kbId)) {
    params.set("kb", String(options.kbId));
  }
  if (options?.tab && options.tab !== "overview") {
    params.set("tab", options.tab);
  }
  const q = params.toString();
  return q ? `/ontology?${q}` : "/ontology";
}

export function kbModelingSectionUrl(kbId: number, anchor?: "quarantine"): string {
  const hash = anchor ? `#${anchor}` : "#modeling";
  return `/knowledge-bases/${kbId}${hash}`;
}

export function parseKbIdFromSearchParams(
  searchParams: URLSearchParams | { get: (key: string) => string | null },
): number | null {
  const raw = searchParams.get("kb");
  if (!raw) return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
}
