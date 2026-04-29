"use client";

type TableItem = { id: number; table_name: string; row_count: number; status: string };

export default function TableList({
  tables,
  onAnalyze
}: {
  tables: TableItem[];
  onAnalyze: (tableName: string) => void;
}) {
  return (
    <div className="space-y-3">
      {tables.map((t) => (
        <article key={t.id} className="app-card app-card-interactive app-list-item p-4">
          <div className="app-list-item-main">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <a className="app-link break-all font-semibold" href={`/table/${t.id}`}>
                {t.table_name}
              </a>
              <span className="rounded-full border border-[#cbd5e1] bg-[#f8fafc] px-2 py-0.5 text-xs text-[#475569]">{t.status}</span>
            </div>
            <p className="app-text-muted mt-2 text-sm">行数：{t.row_count ?? "-"}</p>
          </div>
          <div className="app-list-item-actions">
            <button className="app-button app-button-xs" onClick={() => onAnalyze(t.table_name)}>
              分析
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
