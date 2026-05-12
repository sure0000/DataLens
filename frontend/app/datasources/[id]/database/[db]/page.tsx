"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../../lib/api";
import EmptyState from "../../../../../components/EmptyState";
import ListPagination from "../../../../../components/ListPagination";
import PageHeader from "../../../../../components/PageHeader";

type TableNode = {
  name: string;
  comment?: string;
  status: string;
  latest_analyzed_at?: string;
  ai_analysis?: string;
  table_id?: number;
};
type DatabaseCatalog = {
  datasource: { id: number; name: string };
  database: { name: string; description?: string };
  tables: TableNode[];
};

const STATUS_STYLE: Record<string, string> = {
  done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  analyzing: "bg-sky-50 text-sky-700 border-sky-200",
  error: "bg-rose-50 text-rose-700 border-rose-200",
  pending: "bg-app-hover text-app-secondary border-app-border",
};
const STATUS_LABEL: Record<string, string> = {
  done: "完成",
  analyzing: "分析中",
  error: "失败",
  pending: "待分析",
};

export default function DatabaseDetailPage({ params }: { params: { id: string; db: string } }) {
  const databaseName = decodeURIComponent(params.db);
  const [catalog, setCatalog] = useState<DatabaseCatalog | null>(null);
  const [message, setMessage] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  async function load() {
    const res = await api<DatabaseCatalog>(`/api/datasources/${params.id}/databases/${encodeURIComponent(databaseName)}/catalog`);
    setCatalog(res);
  }

  useEffect(() => {
    load();
  }, [params.id, databaseName, refreshTick]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setRefreshTick((v) => v + 1);
    }, 3000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setPage(1);
  }, [keyword, pageSize, catalog?.tables.length]);

  async function analyzeDatabase() {
    await api(`/api/datasources/${params.id}/analyze/database/${encodeURIComponent(databaseName)}`, { method: "POST" });
    setMessage(`已触发数据库级分析：${databaseName}`);
    load();
  }

  async function analyzeTable(tableName: string) {
    await api(`/api/datasources/${params.id}/analyze/table/${tableName}?database_name=${encodeURIComponent(databaseName)}`, {
      method: "POST"
    });
    setMessage(`已触发表级分析：${databaseName}.${tableName}`);
    load();
  }

  if (!catalog) return <main className="app-page text-app-secondary">加载中...</main>;
  const normalizedKeyword = keyword.trim().toLowerCase();
  const filteredTables = catalog.tables
    .filter((t) => {
      if (!normalizedKeyword) return true;
      return [t.name, t.comment, t.ai_analysis, t.status].filter(Boolean).join(" ").toLowerCase().includes(normalizedKeyword);
    })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  const start = (page - 1) * pageSize;
  const pagedTables = filteredTables.slice(start, start + pageSize);

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", href: "/" },
          { label: "数据源", href: "/datasources" },
          { label: catalog.datasource.name, href: `/datasources/${params.id}` },
          { label: catalog.database.name }
        ]}
        title={catalog.database.name}
        subtitle={catalog.database.description || `${catalog.tables.length} 张数据表`}
        actions={
          <div className="app-toolbar !flex-nowrap w-full min-w-0 md:w-auto">
            <input
              className="app-input app-toolbar-input min-w-0 w-full max-w-[13.5rem] sm:max-w-[15rem]"
              placeholder="搜索表名 / AI分析"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button className="app-button app-toolbar-action shrink-0" onClick={analyzeDatabase}>
              分析全部
            </button>
          </div>
        }
      />
      {!!message && <p className="mt-2 text-sm text-emerald-600">{message}</p>}

      <div className="mt-5 space-y-2.5">
        {pagedTables.map((t) => (
          <div key={t.name} className="app-card app-card-interactive app-list-item px-4 py-3.5">
            <div className="app-list-item-main">
              <div className="flex flex-wrap items-center gap-2">
                {t.table_id ? (
                  <a className="app-link break-all font-semibold" href={`/table/${t.table_id}`}>
                    {t.name}
                  </a>
                ) : (
                  <span className="break-all font-semibold text-app-primary">{t.name}</span>
                )}
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_STYLE[t.status] || STATUS_STYLE.pending}`}>
                  {STATUS_LABEL[t.status] || t.status}
                </span>
              </div>
              {t.ai_analysis ? (
                <p className="mt-1 line-clamp-2 break-words text-sm text-app-secondary">{t.ai_analysis}</p>
              ) : t.comment ? (
                <p className="mt-1 line-clamp-2 break-words text-sm text-app-muted">{t.comment}</p>
              ) : (
                <p className="mt-1 text-sm text-app-muted">暂无 AI 分析</p>
              )}
              <p className="mt-0.5 text-xs text-app-muted">
                {t.latest_analyzed_at ? `最近分析：${new Date(t.latest_analyzed_at).toLocaleString()}` : "尚未分析"}
              </p>
            </div>
            <div className="app-list-item-actions">
              <button className="app-button w-16" onClick={() => analyzeTable(t.name)}>
                分析
              </button>
            </div>
          </div>
        ))}
        {!filteredTables.length && (
          <EmptyState
            title="未匹配到数据表"
            description="请尝试更换搜索关键词，或点击「分析全部」触发批量分析。"
            actionLabel="分析全部"
            onAction={analyzeDatabase}
          />
        )}
        {!!filteredTables.length && (
          <ListPagination
            page={page}
            pageSize={pageSize}
            total={filteredTables.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>
    </main>
  );
}
