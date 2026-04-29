"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../../lib/api";
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

  if (!catalog) return <main className="app-page text-[#6b7280]">加载中...</main>;
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
        meta={<span className="break-words">备注：{catalog.database.description || "无备注"}</span>}
      />

      <div className="mt-4">
        <div className="app-toolbar">
          <button className="app-button app-toolbar-action" onClick={analyzeDatabase}>
            分析该数据库
          </button>
          <input
            className="app-input app-toolbar-input"
            placeholder="搜索表名/备注/AI分析/状态"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
      </div>
      {!!message && <p className="mt-2 text-sm text-emerald-600">{message}</p>}

      <div className="app-card mt-6 overflow-x-auto">
        <table className="app-table min-w-[680px] md:min-w-[900px]">
          <thead>
            <tr>
              <th>数据表</th>
              <th>备注</th>
              <th>AI分析</th>
              <th>分析状态</th>
              <th>最新分析时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {pagedTables.map((t) => (
              <tr key={t.name}>
                <td>
                  {t.table_id ? (
                    <a className="app-link font-medium" href={`/table/${t.table_id}`}>
                      {t.name}
                    </a>
                  ) : (
                    <p className="font-medium">{t.name}</p>
                  )}
                </td>
                <td className="max-w-[260px] text-[#374151]">{t.comment || "-"}</td>
                <td className="max-w-[300px] text-[#374151]">{t.ai_analysis || "-"}</td>
                <td>{t.status}</td>
                <td className="text-[#374151]">{t.latest_analyzed_at ? new Date(t.latest_analyzed_at).toLocaleString() : "-"}</td>
                <td>
                  <button className="app-button" onClick={() => analyzeTable(t.name)}>
                    分析数据表
                  </button>
                </td>
              </tr>
            ))}
            {!filteredTables.length && (
              <tr>
                <td className="text-[#6b7280]" colSpan={6}>
                  未匹配到数据表
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!!filteredTables.length && (
        <ListPagination
          page={page}
          pageSize={pageSize}
          total={filteredTables.length}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
    </main>
  );
}
