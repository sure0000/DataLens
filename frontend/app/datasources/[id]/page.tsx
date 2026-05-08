"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import EmptyState from "../../../components/EmptyState";
import LoadingSkeletonList from "../../../components/LoadingSkeletonList";
import PageHeader from "../../../components/PageHeader";
import Toast from "../../../components/Toast";
import { api } from "../../../lib/api";
import ListPagination from "../../../components/ListPagination";

type DatabaseNode = { name: string; description?: string };
type Catalog = {
  datasource: { id: number; name: string; database: string; source_type: string; description?: string };
  databases: DatabaseNode[];
};

export default function DataSourceDetailPage({ params }: { params: { id: string } }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  async function load() {
    setLoading(true);
    try {
      const res = await api<Catalog>(`/api/datasources/${params.id}/catalog`);
      setCatalog(res);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [params.id]);

  useEffect(() => {
    setPage(1);
  }, [keyword, pageSize, catalog?.databases.length]);

  async function analyzeDataSource() {
    await api(`/api/datasources/${params.id}/analyze/datasource`, { method: "POST" });
    setMessage("已触发数据源级分析");
    load();
  }

  if (!catalog) return <main className="app-page text-app-secondary">正在加载数据源详情...</main>;
  const normalizedKeyword = keyword.trim().toLowerCase();
  const filteredDatabases = catalog.databases
    .filter((db) => {
      if (!normalizedKeyword) return true;
      return [db.name, db.description].filter(Boolean).join(" ").toLowerCase().includes(normalizedKeyword);
    })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  const start = (page - 1) * pageSize;
  const pagedDatabases = filteredDatabases.slice(start, start + pageSize);

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", href: "/" }, { label: "数据源", href: "/datasources" }, { label: catalog.datasource.name }]}
        title={catalog.datasource.name}
        subtitle={`${catalog.datasource.source_type} / ${catalog.datasource.database}`}
        meta={<span className="break-words">备注：{catalog.datasource.description || "无备注"}</span>}
        actions={
          <div className="app-toolbar">
            <button className="app-button app-toolbar-action" onClick={analyzeDataSource}>
              分析数据源
            </button>
            <input
              className="app-input app-toolbar-input"
              placeholder="搜索数据库名称/描述"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
          </div>
        }
      />
      <Toast message={message} tone="success" onClose={() => setMessage("")} />

      <div className="mt-6 space-y-4">
        {loading && <LoadingSkeletonList count={2} />}
        {pagedDatabases.map((db) => (
          <section key={db.name} className="app-card app-card-interactive p-4">
            <Link className="app-link break-all text-lg font-semibold" href={`/datasources/${params.id}/database/${encodeURIComponent(db.name)}`}>
              数据库：{db.name}
            </Link>
            <p className="app-text-secondary-strong mt-2 text-sm">{db.description || "无备注"}</p>
          </section>
        ))}
        {!filteredDatabases.length && (
          <EmptyState title="未匹配到数据库" description="请尝试更换关键词，或先返回数据源列表检查连接和权限配置。" />
        )}
        {!!filteredDatabases.length && (
          <ListPagination
            page={page}
            pageSize={pageSize}
            total={filteredDatabases.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>
    </main>
  );
}
