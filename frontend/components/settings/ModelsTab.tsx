"use client";

type LlmConnPublic = {
  id: string;
  catalog_id: string;
  vendor_id: string;
  vendor_label: string;
  custom_name: string;
  base_url: string;
  provider: string;
  model_id: string;
  created_at: string;
};

function IconPlug({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M12 22v-9" strokeLinecap="round" />
      <path d="M9 7V5a3 3 0 016 0v2" strokeLinecap="round" />
      <path d="M5 10h14v4a4 4 0 01-4 4H9a4 4 0 01-4-4v-4z" strokeLinejoin="round" />
    </svg>
  );
}

interface ModelsTabProps {
  loading: boolean;
  connections: LlmConnPublic[];
  onAdd: () => void;
  onView: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function ModelsTab({ loading, connections, onAdd, onView, onDelete }: ModelsTabProps) {
  return (
    <section className="app-card rounded-2xl p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
            <IconPlug />
          </span>
          <div>
            <h2 className="app-card-title text-base">大模型接入</h2>
            <p className="mt-1 text-[11px] text-app-muted">新增后写入数据库，并出现在下方「可用大模型」与语义分析/Copilot 可选列表中。</p>
          </div>
        </div>
        <button type="button" className="app-button shrink-0 rounded-xl px-4 py-2 text-sm font-medium" onClick={onAdd}>
          新增接入
        </button>
      </div>

      {loading ? (
        <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
          加载中
        </div>
      ) : (
        <div className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-app-muted">可用大模型</h3>
          {connections.length === 0 ? (
            <div className="mt-3 rounded-xl border border-dashed border-app-border bg-app-hover/30 px-4 py-8 text-center text-sm text-app-muted">
              暂无接入，请点击右上角「新增接入」。
            </div>
          ) : (
            <ul className="mt-3 divide-y divide-app-border overflow-hidden rounded-xl border border-app-border bg-white">
              {connections.map((row) => (
                <li key={row.id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-4">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="truncate text-sm font-semibold text-app-ink">{row.custom_name}</p>
                    <p className="text-[11px] text-app-secondary">
                      <span className="text-app-muted">厂商</span> {row.vendor_label}
                      <span className="mx-1.5 text-app-border">·</span>
                      <span className="text-app-muted">模型</span>{" "}
                      <span className="font-mono text-app-ink">{row.model_id}</span>
                    </p>
                    <p className="truncate font-mono text-[10px] text-app-muted" title={row.base_url}>
                      {row.base_url}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <button
                      type="button"
                      className="app-button-secondary rounded-lg px-3 py-1.5 text-xs font-medium"
                      onClick={() => onView(row.id)}
                    >
                      查看
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
                      onClick={() => onDelete(row.id)}
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
