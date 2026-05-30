"use client";

type CatalogModel = {
  id: string;
  label: string;
  provider: string;
  kind_label: string;
  connection_name: string;
  model_id: string;
  model_short_label?: string;
  model_family?: string;
  vendor_id?: string;
};

type Catalog = {
  auto_id: string;
  auto_label: string;
  auto_resolved: string;
  auto_resolved_label?: string;
  models: CatalogModel[];
  has_llm: boolean;
};

type ModelTriplet = { name: string; vendor: string; model: string };

function tripletFromCatalogModel(m: CatalogModel | undefined): ModelTriplet {
  if (!m) return { name: "—", vendor: "—", model: "—" };
  return {
    name: (m.connection_name || "").trim() || "—",
    vendor: (m.kind_label || "").trim() || "—",
    model: (m.model_id || "").trim() || "—"
  };
}

function tripletForModelRef(catalog: Catalog, ref: string): ModelTriplet {
  const m = catalog.models.find((x) => x.id === ref);
  if (m) return tripletFromCatalogModel(m);
  return { name: "—", vendor: "—", model: ref || "—" };
}

export function formatTripletLine(t: ModelTriplet) {
  return `${t.name} · ${t.vendor} · ${t.model}`;
}

function IconColumns({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18M15 9h.01M15 15h.01" />
    </svg>
  );
}

interface SemanticTabProps {
  loading: boolean;
  catalog: Catalog | null;
  semantic: string;
  onSemanticChange: (val: string) => void;
  saving: boolean;
  hasSemanticConnections: boolean;
  semanticCustomModels: CatalogModel[];
  semanticOrphanOption: boolean;
  effectiveTriplet: ModelTriplet | null;
  onSave: () => void;
  onAdd: () => void;
}

export default function SemanticTab({
  loading, catalog, semantic, onSemanticChange, saving,
  hasSemanticConnections, semanticCustomModels,
  semanticOrphanOption, effectiveTriplet, onSave, onAdd
}: SemanticTabProps) {
  return (
    <section className="app-card rounded-2xl p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
          <IconColumns />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="app-card-title text-base">语义分析</h2>
        </div>
      </div>

      {loading ? (
        <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
          加载中
        </div>
      ) : !hasSemanticConnections ? (
        <div className="mt-6 flex flex-col items-center gap-4 rounded-2xl border border-dashed border-app-border bg-app-hover/30 px-4 py-10">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-app-border bg-app-surfaceMuted text-app-secondary">
            <IconColumns className="h-7 w-7" />
          </div>
          <p className="text-center text-sm text-app-secondary">尚未配置可用大模型，请先新增一条接入。</p>
          <button type="button" className="app-button" onClick={onAdd}>
            新增接入
          </button>
        </div>
      ) : !catalog ? (
        <p className="mt-6 text-sm text-app-muted">模型目录加载中…</p>
      ) : (
        <div className="mt-5 space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs font-medium text-app-secondary">
              可选模型
              <select
                className="app-input rounded-xl px-3 py-2.5 text-sm focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                value={semantic}
                onChange={(e) => onSemanticChange(e.target.value)}
              >
                <option value={catalog.auto_id}>自动</option>
                {semanticOrphanOption ? (
                  <option value={semantic} disabled>
                    （已不在列表）{formatTripletLine(tripletForModelRef(catalog, semantic))}
                  </option>
                ) : null}
                {semanticCustomModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {formatTripletLine(tripletFromCatalogModel(m))}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="app-button shrink-0"
              disabled={saving}
              onClick={onSave}
            >
              {saving ? "保存中…" : "保存"}
            </button>
          </div>
          {effectiveTriplet ? (
            <div className="rounded-xl border border-app-border bg-app-hover/40 px-3 py-3 text-sm">
              <p className="text-[11px] font-medium text-app-muted">当前生效</p>
              <dl className="mt-2 grid gap-2 sm:grid-cols-3">
                <div>
                  <dt className="text-[10px] font-medium uppercase tracking-wide text-app-muted">名称</dt>
                  <dd className="mt-0.5 font-medium text-app-ink">{effectiveTriplet.name}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-medium uppercase tracking-wide text-app-muted">厂商</dt>
                  <dd className="mt-0.5 text-app-ink">{effectiveTriplet.vendor}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-medium uppercase tracking-wide text-app-muted">模型</dt>
                  <dd className="mt-0.5 font-mono text-xs text-app-ink">{effectiveTriplet.model}</dd>
                </div>
              </dl>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
