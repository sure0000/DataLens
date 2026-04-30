"use client";

import { useEffect, useState } from "react";
import ColumnCard from "../../../components/ColumnCard";
import { api } from "../../../lib/api";
import PageHeader from "../../../components/PageHeader";

type Detail = {
  table: {
    table_name: string;
    database_name: string;
    datasource_name: string;
    row_count: number;
    status: string;
    domain_names: string[];
  };
  columns: any[];
  summary: {
    summary: string;
    sections?: { title: string; items: string[] }[];
    use_cases: string[];
    key_columns: string[];
    warnings: string;
  };
};

const DISPLAY_SECTIONS = ["业务描述", "数据定位", "核心口径", "使用建议"];


// Tab order: summary sections + 典型分析场景 + 风险边界
const TAB_ORDER = [...DISPLAY_SECTIONS, "典型分析场景", "风险边界"];

export default function TableDetail({ params }: { params: { id: string } }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [keyword, setKeyword] = useState("");
  const [activeTab, setActiveTab] = useState("");

  useEffect(() => {
    api<Detail>(`/api/table/${params.id}`).then((d) => {
      setDetail(d);
    });
  }, [params.id]);

  // Set default tab once data loads
  useEffect(() => {
    if (!detail || activeTab) return;
    const first = TAB_ORDER.find((t) => {
      if (t === "典型分析场景") return detail.summary.use_cases.length > 0;
      if (t === "风险边界") {
        const sec = detail.summary.sections?.find((s) => s.title === "风险边界");
        return (sec?.items.length ?? 0) > 0 || !!detail.summary.warnings;
      }
      return detail.summary.sections?.some((s) => s.title === t && s.items.length > 0);
    });
    if (first) setActiveTab(first);
  }, [detail, activeTab]);

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

  const riskSection = detail.summary.sections?.find((s) => s.title === "风险边界");
  const riskItems = riskSection?.items ?? [];
  const warningsText = detail.summary.warnings || "";

  // Build visible tabs
  const visibleTabs = TAB_ORDER.filter((t) => {
    if (t === "典型分析场景") return detail.summary.use_cases.length > 0;
    if (t === "风险边界") return riskItems.length > 0 || !!warningsText;
    return detail.summary.sections?.some((s) => s.title === t && s.items.length > 0);
  });

  const currentSection = detail.summary.sections?.find((s) => s.title === activeTab);

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", href: "/" },
          { label: "数据源", href: "/datasources" },
          { label: "数据表详情" },
        ]}
        title={detail.table.table_name}
        subtitle={`${detail.table.datasource_name || ""}${detail.table.datasource_name ? " / " : ""}${detail.table.database_name}`}
        meta={
          <span className="flex flex-wrap items-center gap-3">
            <span>行数：{detail.table.row_count?.toLocaleString() ?? "—"}</span>
            {detail.table.domain_names.length > 0 ? (
              <span className="flex flex-wrap gap-1">
                {detail.table.domain_names.map((d) => (
                  <span key={d} className="rounded-full border border-[#c7d2fe] bg-[#eef2ff] px-2 py-0.5 text-xs font-medium text-[#4338ca]">
                    {d}
                  </span>
                ))}
              </span>
            ) : (
              <span className="text-xs text-[#9ca3af]">暂未关联业务域</span>
            )}
          </span>
        }
        actions={
          <a className="app-button" href="/copilot">
            去 Copilot 分析
          </a>
        }
      />

      {/* Summary tabs */}
      {visibleTabs.length > 0 && (
        <div className="mt-5">
          {/* Tab bar */}
          <div className="flex gap-1 overflow-x-auto border-b border-[#e5e7eb] pb-px">
            {visibleTabs.map((tab) => {
              const isActive = activeTab === tab;
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
                    isActive
                      ? "border-[#111827] text-[#111827]"
                      : "border-transparent text-[#6b7280] hover:text-[#374151]"
                  }`}
                >
                  {tab}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="mt-4 min-h-[80px]">
            {(() => {
              const items =
                activeTab === "典型分析场景"
                  ? detail.summary.use_cases
                  : activeTab === "风险边界"
                  ? riskItems.length > 0
                    ? riskItems
                    : warningsText
                    ? [warningsText]
                    : []
                  : currentSection?.items ?? [];

              if (items.length === 0 && detail.summary.summary) {
                return <p className="whitespace-pre-wrap break-words text-sm leading-7 text-[#374151]">{detail.summary.summary}</p>;
              }

              return (
                <ul className="divide-y divide-[#f3f4f6] rounded-xl border border-[#e5e7eb] bg-white">
                  {items.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-3 px-4 py-3">
                      <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#f3f4f6] text-[10px] font-semibold text-[#6b7280]">
                        {idx + 1}
                      </span>
                      <span className="break-words text-sm leading-6 text-[#374151]">{item}</span>
                    </li>
                  ))}
                </ul>
              );
            })()}
          </div>
        </div>
      )}

      {/* Columns */}
      <div className="mt-7">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="app-section-title">
            字段列表
            <span className="ml-2 text-sm font-normal text-[#6b7280]">({filteredColumns.length} / {detail.columns.length})</span>
          </h2>
          <input
            className="app-input w-full max-w-xs"
            placeholder="搜索字段名 / 类型 / 语义"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        {filteredColumns.length > 0 ? (
          <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
            {filteredColumns.map((c, i) => (
              <ColumnCard col={c} key={`${c.column_name}-${i}`} isLast={i === filteredColumns.length - 1} />
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-[#6b7280]">未匹配到字段</p>
        )}
      </div>
    </main>
  );
}
