"use client";

import { useCallback, useEffect, useState } from "react";
import ConceptHierarchyTree, { type HierarchyNode } from "../ontology/ConceptHierarchyTree";
import { api, ApiError, formatApiError } from "../../lib/api";

interface ConceptHierarchyPanelProps {
  kbId: number;
}

export default function ConceptHierarchyPanel({ kbId }: ConceptHierarchyPanelProps) {
  const [roots, setRoots] = useState<HierarchyNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api<{ roots?: HierarchyNode[] }>(
        `/api/ontology/knowledge-bases/${kbId}/views/hierarchy`,
      );
      setRoots(res.roots ?? []);
    } catch (e: unknown) {
      setRoots([]);
      setError(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-sm text-app-muted py-4">加载概念层级…</p>;
  }

  if (error) {
    return <p className="text-sm text-app-danger py-4">{error}</p>;
  }

  return (
    <div className="app-card p-4">
      <p className="text-xs text-app-muted mb-3">
        树形查看 BusinessConcept 的 skos:broader 结构，用于核对挂类与层级深度（对应 hierarchy SHACL）。
      </p>
      <ConceptHierarchyTree roots={roots} defaultExpandDepth={1} />
    </div>
  );
}
