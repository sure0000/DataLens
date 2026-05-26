"use client";

import type { KbRdfView } from "../../lib/ontologyTypes";

interface OntologyTripleViewProps {
  rdfView: KbRdfView | null;
}

export default function OntologyTripleView({ rdfView }: OntologyTripleViewProps) {
  if (!rdfView) {
    return (
      <div className="app-card p-8 text-sm text-app-muted text-center">
        暂无 RDF 本体数据。请先在知识库中运行语义流水线并同步到 RDF。
      </div>
    );
  }

  const prod = rdfView.production;
  const q = rdfView.quarantine;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard label="三元组" value={prod.triple_count} />
        <StatCard label="RDF 术语" value={prod.term_count} />
        <StatCard label="RDF 指标" value={prod.metric_count} />
        <StatCard label="物理表" value={prod.physical_table_count} />
      </div>

      {q.assertion_count > 0 && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm">
          <p className="font-medium text-red-600 dark:text-red-400">
            隔离区 {q.assertion_count} 条断言
          </p>
          <p className="mt-1 text-app-muted text-xs">
            未通过校验的三元组，不会出现在生产图中。
          </p>
        </div>
      )}

      {prod.terms.length > 0 && (
        <section>
          <h3 className="app-section-title mb-2">业务术语</h3>
          <div className="space-y-1.5">
            {prod.terms.slice(0, 10).map((t, i) => (
              <div key={i} className="app-card p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-app-primary">{t.label}</p>
                  {t.definition && <p className="text-xs text-app-muted mt-0.5 line-clamp-1">{t.definition}</p>}
                </div>
                {t.status && (
                  <span className="text-[11px] text-app-muted shrink-0 ml-3">{t.status}</span>
                )}
              </div>
            ))}
            {prod.terms.length > 10 && (
              <p className="text-xs text-app-muted">…还有 {prod.terms.length - 10} 条</p>
            )}
          </div>
        </section>
      )}

      {prod.metrics.length > 0 && (
        <section>
          <h3 className="app-section-title mb-2">指标口径</h3>
          <div className="space-y-1.5">
            {prod.metrics.slice(0, 10).map((m, i) => (
              <div key={i} className="app-card p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-app-primary">{m.label}</p>
                  {m.formula && <p className="text-xs text-app-muted mt-0.5 font-mono">{m.formula}</p>}
                </div>
                {m.status && (
                  <span className="text-[11px] text-app-muted shrink-0 ml-3">{m.status}</span>
                )}
              </div>
            ))}
            {prod.metrics.length > 10 && (
              <p className="text-xs text-app-muted">…还有 {prod.metrics.length - 10} 条</p>
            )}
          </div>
        </section>
      )}

      {prod.physical_tables.length > 0 && (
        <section>
          <h3 className="app-section-title mb-2">物理表</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {prod.physical_tables.map((t) => (
              <div key={t.iri} className="app-card p-3">
                <p className="text-sm font-medium text-app-primary">表 {t.platform_id || "—"}</p>
                <p className="mt-1 text-xs text-app-muted line-clamp-2">{t.summary || "（无业务摘要）"}</p>
                <p className="mt-1.5 font-mono text-[10px] text-app-muted break-all">{t.iri}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="app-card p-3 text-center">
      <p className="text-2xl font-bold text-app-primary">{value}</p>
      <p className="text-xs text-app-muted mt-1">{label}</p>
    </div>
  );
}
