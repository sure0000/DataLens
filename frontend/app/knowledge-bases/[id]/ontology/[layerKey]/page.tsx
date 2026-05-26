"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PageHeader from "../../../../../components/PageHeader";
import { api } from "../../../../../lib/api";
import type { OntologyCleaningResults } from "../../../../../components/knowledge-bases/types";

const LAYER_LABELS: Record<string, string> = {
  vocabulary: "词汇层",
  rule: "规则层",
  "entity-concept": "实体概念层",
  relation: "关系层",
  attribute: "属性层",
};

export default function OntologyLayerDetailPage({
  params,
}: {
  params: { id: string; layerKey: string };
}) {
  const kbId = Number(params.id);
  const layerKey = params.layerKey;

  const [results, setResults] = useState<OntologyCleaningResults | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadResults() {
    setLoading(true);
    try {
      const res = await api<OntologyCleaningResults>(
        `/api/ontology/knowledge-bases/${kbId}/ontology-cleaning-results`
      );
      setResults(res);
    } catch {
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadResults(); }, [kbId]);

  const layer = results?.layers?.[layerKey];
  const layerLabel = (layer?.label) || LAYER_LABELS[layerKey] || layerKey;

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "语义知识库", href: "/knowledge-bases" },
          { label: `知识库 ${kbId}`, href: `/knowledge-bases/${kbId}` },
          { label: layerLabel },
        ]}
        title={`本体建模 · ${layerLabel}`}
        subtitle={layer?.description || ""}
      />

      {loading && <p className="text-sm text-app-muted mt-4">加载中…</p>}

      {!loading && !layer && (
        <p className="text-sm text-app-muted mt-4">暂无数据。</p>
      )}

      {!loading && layer && layer.items.length === 0 && (
        <p className="text-sm text-app-muted mt-4">该层暂无数据，请先触发语义清洗。</p>
      )}

      {!loading && layer && layer.items.length > 0 && (
        <div className="mt-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-app-muted">
              共 {layer.total} 条 · {layer.ontology_class}
            </span>
          </div>

          <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
            <table className="app-table">
              <thead>
                <tr>
                  {layerKey === "vocabulary" && (
                    <>
                      <th className="px-3 py-2.5">术语 IRI</th>
                      <th className="px-3 py-2.5">标签</th>
                      <th className="px-3 py-2.5">定义</th>
                      <th className="w-24 px-3 py-2.5">状态</th>
                    </>
                  )}
                  {layerKey === "rule" && (
                    <>
                      <th className="px-3 py-2.5">IRI</th>
                      <th className="px-3 py-2.5">标签</th>
                      <th className="px-3 py-2.5">公式 / 表达式</th>
                      <th className="w-24 px-3 py-2.5">状态</th>
                    </>
                  )}
                  {layerKey === "entity-concept" && (
                    <>
                      <th className="px-3 py-2.5">概念 IRI</th>
                      <th className="px-3 py-2.5">标签</th>
                      <th className="px-3 py-2.5">上位概念</th>
                      <th className="w-24 px-3 py-2.5">状态</th>
                    </>
                  )}
                  {layerKey === "relation" && (
                    <>
                      <th className="px-3 py-2.5">主体</th>
                      <th className="px-3 py-2.5">谓词</th>
                      <th className="px-3 py-2.5">客体</th>
                    </>
                  )}
                  {layerKey === "attribute" && (
                    <>
                      <th className="px-3 py-2.5">主体</th>
                      <th className="px-3 py-2.5">属性</th>
                      <th className="px-3 py-2.5">值</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {layer.items.map((item, i) => (
                  <tr key={i} className="hover:bg-app-hover">
                    {layerKey === "vocabulary" && (
                      <>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[200px] truncate" title={item.s}>
                          {item.s}
                        </td>
                        <td className="px-3 py-2.5 text-sm text-app-primary">{item.label || "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-app-muted max-w-[300px] truncate" title={item.definition}>
                          {item.definition || "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${
                            item.status === "approved" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-gray-50 text-gray-600 border-gray-200"
                          }`}>
                            {item.status || "draft"}
                          </span>
                        </td>
                      </>
                    )}
                    {layerKey === "rule" && (
                      <>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[200px] truncate" title={item.s}>
                          {item.s}
                        </td>
                        <td className="px-3 py-2.5 text-sm text-app-primary">{item.label || "—"}</td>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[300px] truncate" title={item.formula || item.ruleExpression}>
                          {item.formula || item.ruleExpression || "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${
                            item.status === "approved" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-gray-50 text-gray-600 border-gray-200"
                          }`}>
                            {item.status || "draft"}
                          </span>
                        </td>
                      </>
                    )}
                    {layerKey === "entity-concept" && (
                      <>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[200px] truncate" title={item.s}>
                          {item.s}
                        </td>
                        <td className="px-3 py-2.5 text-sm text-app-primary">{item.label || "—"}</td>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[200px] truncate" title={item.broader}>
                          {item.broader || "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${
                            item.status === "approved" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-gray-50 text-gray-600 border-gray-200"
                          }`}>
                            {item.status || "draft"}
                          </span>
                        </td>
                      </>
                    )}
                    {layerKey === "relation" && (
                      <>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[250px] truncate" title={item.s}>
                          {item.s}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-app-secondary font-medium">{item.p}</td>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[250px] truncate" title={item.o}>
                          {item.o}
                        </td>
                      </>
                    )}
                    {layerKey === "attribute" && (
                      <>
                        <td className="px-3 py-2.5 text-xs font-mono text-app-muted max-w-[250px] truncate" title={item.s}>
                          {item.s}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-app-secondary font-medium">{item.p}</td>
                        <td className="px-3 py-2.5 text-xs text-app-primary max-w-[300px] truncate" title={item.o}>
                          {item.o}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  );
}
