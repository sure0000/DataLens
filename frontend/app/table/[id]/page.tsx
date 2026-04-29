"use client";

import { useEffect, useState } from "react";
import ColumnCard from "../../../components/ColumnCard";
import { api } from "../../../lib/api";
import ListPagination from "../../../components/ListPagination";
import PageHeader from "../../../components/PageHeader";

type Detail = {
  table: { table_name: string; row_count: number };
  columns: any[];
  summary: {
    summary: string;
    sections?: { title: string; items: string[] }[];
    use_cases: string[];
    key_columns: string[];
    warnings: string;
  };
};

export default function TableDetail({ params }: { params: { id: string } }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  useEffect(() => {
    api<Detail>(`/api/table/${params.id}`).then(setDetail);
  }, [params.id]);
  useEffect(() => {
    setPage(1);
  }, [keyword, pageSize, detail?.columns.length]);
  if (!detail) return <main className="app-page text-[#6b7280]">加载中...</main>;
  const normalizedKeyword = keyword.trim().toLowerCase();
  const filteredColumns = detail.columns
    .filter((c) => {
      if (!normalizedKeyword) return true;
      return [c.column_name, c.data_type, c.semantic_desc, c.semantic_type]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalizedKeyword);
    })
    .sort((a, b) => String(a.column_name || "").localeCompare(String(b.column_name || ""), "zh-Hans-CN"));
  const start = (page - 1) * pageSize;
  const pagedColumns = filteredColumns.slice(start, start + pageSize);
  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", href: "/" },
          { label: "数据源", href: "/datasources" },
          { label: "数据表详情" }
        ]}
        title={detail.table.table_name}
        meta={`行数：${detail.table.row_count}`}
      />
      {!!detail.summary.sections?.some((section) => section.items.length > 0) ? (
        <div className="mt-4 grid gap-3">
          {detail.summary.sections?.map((section) => (
            <section key={section.title} className="rounded-xl border border-[#e5e7eb] bg-white p-4">
              <h3 className="text-sm font-semibold text-[#374151]">{section.title}</h3>
              {section.items.length ? (
                <ul className="mt-2 space-y-1.5 text-sm text-[#111827]">
                  {section.items.map((item, idx) => (
                    <li key={`${section.title}-${idx}`} className="break-words">
                      - {item}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-[#9ca3af]">暂无内容</p>
              )}
            </section>
          ))}
        </div>
      ) : (
        <p className="mt-3 whitespace-pre-wrap break-words text-[#374151]">{detail.summary.summary}</p>
      )}
      {!!detail.summary.warnings && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-700">{detail.summary.warnings}</div>}
      <div className="mt-3 flex flex-wrap gap-2">
        {detail.summary.use_cases.map((u, i) => (
          <span key={i} className="rounded-full border border-[#d1d5db] bg-[#f3f4f6] px-2 py-1 text-xs text-[#4b5563]">
            {u}
          </span>
        ))}
      </div>
      <div className="app-toolbar mt-6">
        <h2 className="app-section-title">字段列表</h2>
        <input
          className="app-input app-toolbar-input"
          placeholder="搜索字段名/类型/语义"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
      </div>
      <div className="mt-3 grid gap-3">{pagedColumns.map((c, i) => <ColumnCard col={c} key={`${c.column_name}-${i}`} />)}</div>
      {!filteredColumns.length && <p className="mt-2 text-sm text-[#6b7280]">未匹配到字段</p>}
      {!!filteredColumns.length && (
        <ListPagination
          page={page}
          pageSize={pageSize}
          total={filteredColumns.length}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
      <a className="app-link mt-6 inline-block" href="/copilot">
        去 Copilot 分析这张表
      </a>
    </main>
  );
}
