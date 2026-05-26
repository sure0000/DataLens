"use client";

import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight, Copy, Search } from "lucide-react";

export interface RawTriple {
  subject: string;
  predicate: string;
  object: string;
}

interface TripleViewerProps {
  triples: RawTriple[];
  compact?: boolean;
}

const KNOWN_PREFIXES: Record<string, string> = {
  "https://datalens.local/ontology/": "dl:",
  "https://datalens.local/data/": "data:",
  "https://datalens.local/graph/": "graph:",
  "http://www.w3.org/2004/02/skos/core#": "skos:",
  "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
  "https://schema.org/": "schema:",
  "http://www.w3.org/2002/07/owl#": "owl:",
};

function shortenIri(iri: string): string {
  for (const [ns, prefix] of Object.entries(KNOWN_PREFIXES)) {
    if (iri.startsWith(ns)) return iri.replace(ns, prefix);
    if (iri.startsWith(`<${ns}`)) return `<${iri.slice(1).replace(ns, prefix)}`;
  }
  return iri;
}

export default function TripleViewer({ triples, compact = false }: TripleViewerProps) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(true);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return triples;
    return triples.filter(
      (t) =>
        t.subject.toLowerCase().includes(q) ||
        t.predicate.toLowerCase().includes(q) ||
        t.object.toLowerCase().includes(q),
    );
  }, [triples, search]);

  const handleCopyAll = () => {
    const text = triples
      .map((t) => `${t.subject} ${t.predicate} ${t.object}`)
      .join("\n");
    navigator.clipboard.writeText(text).catch(() => {});
  };

  if (triples.length === 0) {
    return (
      <p className="text-sm text-app-muted px-3 py-4">暂无三元组数据。</p>
    );
  }

  return (
    <div className="space-y-2">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="app-button-secondary text-xs px-2 py-1 flex items-center gap-1"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          {expanded ? "收起" : "展开"} ({triples.length})
        </button>
        <div className="relative flex-1 max-w-[240px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-app-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索三元组…"
            className="w-full rounded-lg border border-app-border bg-app-fill-input py-1 pl-7 pr-2 text-xs text-app-primary placeholder:text-app-placeholder focus:outline-none focus:border-app-active-border"
          />
        </div>
        <button
          type="button"
          className="app-button-secondary text-xs px-2 py-1 flex items-center gap-1"
          onClick={handleCopyAll}
          title="复制全部三元组"
        >
          <Copy className="h-3 w-3" />
          N-Triples
        </button>
      </div>

      {/* Triple table */}
      {expanded && (
        <div className="overflow-x-auto rounded-xl border border-app-border">
          <table className={`w-full font-mono ${compact ? "text-[10px]" : "text-[11px]"}`}>
            {!compact && (
              <thead>
                <tr className="bg-app-surface-subtle text-app-muted">
                  <th className="text-left px-3 py-1.5 font-medium w-[30%]">Subject</th>
                  <th className="text-left px-3 py-1.5 font-medium w-[30%]">Predicate</th>
                  <th className="text-left px-3 py-1.5 font-medium w-[40%]">Object</th>
                </tr>
              </thead>
            )}
            <tbody>
              {filtered.slice(0, compact ? 100 : 500).map((t, i) => (
                <tr
                  key={i}
                  className={`border-t border-app-border-subtle ${
                    i % 2 === 0 ? "bg-transparent" : "bg-app-surface-subtle"
                  }`}
                >
                  <td className="px-3 py-1 text-app-link break-all">{shortenIri(t.subject)}</td>
                  <td className="px-3 py-1 text-app-muted break-all">{shortenIri(t.predicate)}</td>
                  <td className="px-3 py-1 text-app-primary break-all">{shortenIri(t.object)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length > (compact ? 100 : 500) && (
            <p className="px-3 py-1.5 text-xs text-app-muted bg-app-surface-subtle">
              显示前 {compact ? 100 : 500} / {filtered.length} 条
            </p>
          )}
        </div>
      )}
    </div>
  );
}
