"use client";

import { useState } from "react";
import { Icon } from "../AppIcons";
import { api } from "../../lib/api";

export default function SparqlConsole({ kbId }: { kbId: number }) {
  const [query, setQuery] = useState(
    `PREFIX dl: <https://datalens.local/ontology/>\nSELECT ?s ?label WHERE {\n  GRAPH <https://datalens.local/graph/kb/${kbId}> {\n    ?s a dl:BusinessTerm .\n    OPTIONAL { ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label }\n  }\n} LIMIT 20`,
  );
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Record<string, string>[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const res = await api<{ ok?: boolean; results?: Record<string, string>[] }>(
        "/api/ontology/sparql",
        {
          method: "POST",
          body: JSON.stringify({ query, kb_id: kbId }),
        },
      );
      setResults(res.results ?? []);
    } catch (e: unknown) {
      setResults([]);
      setError(e instanceof Error ? e.message : "查询失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <textarea
        className="app-input w-full min-h-[140px] font-mono text-xs"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        spellCheck={false}
      />
      <button
        type="button"
        className={`app-button text-sm ${running ? "is-loading" : ""}`}
        disabled={running || !query.trim()}
        onClick={() => void run()}
      >
        <Icon name="play" className="inline h-4 w-4 mr-1" />
        执行 SPARQL
      </button>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {results.length > 0 && (
        <pre className="app-card p-3 text-[11px] font-mono overflow-auto max-h-64">
          {JSON.stringify(results, null, 2)}
        </pre>
      )}
    </div>
  );
}
