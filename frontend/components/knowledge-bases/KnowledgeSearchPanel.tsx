"use client";

import { useState } from "react";
import type { Hit } from "./types";

interface KnowledgeSearchPanelProps {
  searching: boolean;
  searched: boolean;
  hits: Hit[];
  searchQuery: string;
  onSearchQueryChange: (q: string) => void;
  onSearch: () => void;
  onHitClick: (hit: Hit) => void;
}

export default function KnowledgeSearchPanel({
  searching,
  searched,
  hits,
  searchQuery,
  onSearchQueryChange,
  onSearch,
  onHitClick,
}: KnowledgeSearchPanelProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="app-card overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center gap-2 p-3 text-left hover:bg-app-hover transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <svg
          className={`h-4 w-4 shrink-0 text-app-muted transition-transform ${expanded ? "rotate-90" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
        <span className="text-sm font-medium text-app-primary">检索测试</span>
        <span className="text-xs text-app-muted">向量 + 关键词混合检索</span>
      </button>

      {expanded && (
        <div className="border-t border-app-border p-3 space-y-3">
          <div className="flex items-center gap-2">
            <input
              className="app-input h-8 flex-1 text-xs"
              placeholder="输入检索关键词…"
              value={searchQuery}
              onChange={(e) => onSearchQueryChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSearch();
              }}
            />
            <button
              className={`app-button text-xs h-8 ${searching ? "is-loading" : ""}`}
              type="button"
              disabled={searching || !searchQuery.trim()}
              onClick={onSearch}
            >
              {searching ? "…" : "搜索"}
            </button>
          </div>

          {searched && !searching && hits.length === 0 && (
            <p className="text-xs text-app-muted">无匹配结果</p>
          )}

          {hits.length > 0 && (
            <div className="divide-y divide-app-border rounded-lg border border-app-border max-h-64 overflow-y-auto">
              {hits.map((hit) => (
                <div
                  key={hit.entry_id}
                  className="p-2.5 space-y-1 cursor-pointer hover:bg-app-hover transition-colors"
                  onClick={() => onHitClick(hit)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-app-primary truncate">
                      {hit.title}
                    </p>
                    <span className="shrink-0 text-[10px] text-app-muted font-mono">
                      {hit.rrf_score != null && <>RRF:{hit.rrf_score.toFixed(3)}</>}
                      {hit.vector_rank != null && <> V#{hit.vector_rank}</>}
                      {hit.bm25_rank != null && <> BM25#{hit.bm25_rank}</>}
                    </span>
                  </div>
                  {hit.snippet && (
                    <p className="text-xs text-app-muted line-clamp-2 leading-relaxed">
                      {hit.snippet}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
