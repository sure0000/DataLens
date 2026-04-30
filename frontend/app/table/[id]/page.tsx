"use client";

import { useEffect, useRef, useState } from "react";
import ColumnCard from "../../../components/ColumnCard";
import { api } from "../../../lib/api";
import PageHeader from "../../../components/PageHeader";

type Detail = {
  table: {
    id?: number;
    table_name: string;
    database_name: string;
    datasource_name: string;
    row_count: number;
    status: string;
    domain_names: string[];
  };
  knowledge_bases?: { id: number; name: string }[];
  knowledge_entries?: { id: number; knowledge_base_id: number; title: string }[];
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
  const [allKbs, setAllKbs] = useState<{ id: number; name: string }[]>([]);
  const [linkKbIds, setLinkKbIds] = useState<number[]>([]);
  const [linkEntryIds, setLinkEntryIds] = useState<number[]>([]);
  const [savingLinks, setSavingLinks] = useState(false);
  const [kbModalOpen, setKbModalOpen] = useState(false);
  const [kbPickerPick, setKbPickerPick] = useState<Record<number, boolean>>({});
  const [entryModalOpen, setEntryModalOpen] = useState(false);
  const [pickerKbId, setPickerKbId] = useState("");
  const [pickerEntries, setPickerEntries] = useState<{ id: number; title: string }[]>([]);
  const [pickerPick, setPickerPick] = useState<Record<number, boolean>>({});
  const linkEntryIdsRef = useRef(linkEntryIds);
  linkEntryIdsRef.current = linkEntryIds;

  useEffect(() => {
    api<{ knowledge_bases: { id: number; name: string }[] }>("/api/knowledge-bases")
      .then((r) => setAllKbs(r.knowledge_bases || []))
      .catch(() => setAllKbs([]));
  }, []);

  useEffect(() => {
    api<Detail>(`/api/table/${params.id}`).then((d) => {
      setDetail(d);
      setLinkKbIds(d.knowledge_bases?.map((k) => k.id) ?? []);
      setLinkEntryIds(d.knowledge_entries?.map((e) => e.id) ?? []);
    });
  }, [params.id]);

  useEffect(() => {
    if (!entryModalOpen || !pickerKbId) return;
    const kbNum = Number(pickerKbId);
    if (!Number.isFinite(kbNum)) return;
    api<{ entries: { id: number; title: string }[] }>(`/api/knowledge-bases/${kbNum}`).then((res) => {
      const entries = res.entries || [];
      setPickerEntries(entries);
      const next: Record<number, boolean> = {};
      entries.forEach((e) => {
        next[e.id] = linkEntryIdsRef.current.includes(e.id);
      });
      setPickerPick(next);
    });
  }, [entryModalOpen, pickerKbId]);

  function openKbModal() {
    const next: Record<number, boolean> = {};
    allKbs.forEach((kb) => {
      next[kb.id] = linkKbIds.includes(kb.id);
    });
    setKbPickerPick(next);
    setKbModalOpen(true);
  }

  function confirmKbPicker() {
    const picked = allKbs.filter((kb) => kbPickerPick[kb.id]).map((kb) => kb.id);
    setLinkKbIds(picked);
    setKbModalOpen(false);
  }

  function openEntryModal() {
    setPickerKbId(allKbs[0]?.id != null ? String(allKbs[0].id) : "");
    setPickerEntries([]);
    setPickerPick({});
    setEntryModalOpen(true);
  }

  function confirmPickerEntries() {
    const pickerSet = new Set(pickerEntries.map((e) => e.id));
    const rest = linkEntryIds.filter((id) => !pickerSet.has(id));
    const picked = pickerEntries.filter((e) => pickerPick[e.id]).map((e) => e.id);
    setLinkEntryIds([...rest, ...picked]);
    setEntryModalOpen(false);
  }

  async function saveTableKnowledgeLinks() {
    setSavingLinks(true);
    try {
      await api(`/api/table/${params.id}/knowledge-links`, {
        method: "PUT",
        body: JSON.stringify({ knowledge_base_ids: linkKbIds, knowledge_entry_ids: linkEntryIds })
      });
      const d = await api<Detail>(`/api/table/${params.id}`);
      setDetail(d);
      setLinkKbIds(d.knowledge_bases?.map((k) => k.id) ?? []);
      setLinkEntryIds(d.knowledge_entries?.map((e) => e.id) ?? []);
    } finally {
      setSavingLinks(false);
    }
  }

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
          <a className="app-button" href={`/copilot?table=${encodeURIComponent(params.id)}`}>
            去 Copilot 分析
          </a>
        }
      />

      <section className="app-card mt-5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="app-section-title">关联知识库与条目</h2>
          <button type="button" className={`app-button ${savingLinks ? "is-loading" : ""}`} onClick={saveTableKnowledgeLinks} disabled={savingLinks}>
            {savingLinks ? "保存中…" : "保存"}
          </button>
        </div>
        <p className="app-text-muted mt-1 text-xs">
          关联知识库后，Copilot 在本表上下文中会对这些库做语义检索；固定条目将全文注入上下文。可与会话所选业务域下的知识库叠加。
        </p>
        <div className="mt-3 rounded-lg border border-[#e5e7eb] bg-[#fafafa] p-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-[#374151]">知识库</p>
            <button type="button" className="app-button-secondary text-xs" onClick={openKbModal}>
              添加知识库
            </button>
          </div>
          {!linkKbIds.length ? (
            <p className="mt-2 text-xs text-[#9ca3af]">未选择知识库</p>
          ) : (
            <p className="mt-2 text-xs text-[#4b5563]">
              已选择 {linkKbIds.length} 个：{linkKbIds.map((id) => allKbs.find((kb) => kb.id === id)?.name || `#${id}`).join("、")}
            </p>
          )}
        </div>
        <div className="mt-3 rounded-lg border border-[#e5e7eb] bg-[#fafafa] p-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-[#374151]">知识库条目</p>
            <button type="button" className="app-button-secondary text-xs" onClick={openEntryModal}>
              添加条目
            </button>
          </div>
          {!linkEntryIds.length ? (
            <p className="mt-2 text-xs text-[#9ca3af]">未选择条目</p>
          ) : (
            <p className="mt-2 text-xs text-[#4b5563]">
              已选择 {linkEntryIds.length} 条：
              {linkEntryIds
                .map((id) => detail.knowledge_entries?.find((e) => e.id === id)?.title || `#${id}`)
                .join("、")}
            </p>
          )}
        </div>
      </section>

      {kbModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#111827]/35 p-4 backdrop-blur-[2px]"
          role="presentation"
          onClick={() => setKbModalOpen(false)}
        >
          <div className="app-card max-h-[85vh] w-full max-w-lg overflow-auto p-5" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">选择知识库</h2>
              <button type="button" className="app-control-button" onClick={() => setKbModalOpen(false)}>
                关闭
              </button>
            </div>
            {!allKbs.length ? (
              <p className="text-sm text-[#9ca3af]">暂无知识库</p>
            ) : (
              <ul className="max-h-[56vh] space-y-2 overflow-y-auto">
                {allKbs.map((kb) => (
                  <li key={kb.id}>
                    <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#e5e7eb] px-3 py-2 text-sm hover:bg-[#f9fafb]">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={!!kbPickerPick[kb.id]}
                        onChange={() => setKbPickerPick((p) => ({ ...p, [kb.id]: !p[kb.id] }))}
                      />
                      <span>{kb.name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4 flex gap-2">
              <button type="button" className="app-button flex-1" onClick={confirmKbPicker}>
                确定
              </button>
              <button type="button" className="app-button-secondary flex-1" onClick={() => setKbModalOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {entryModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#111827]/35 p-4 backdrop-blur-[2px]"
          role="presentation"
          onClick={() => setEntryModalOpen(false)}
        >
          <div className="app-card max-h-[85vh] w-full max-w-lg overflow-auto p-5" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">选择知识条目</h2>
              <button type="button" className="app-control-button" onClick={() => setEntryModalOpen(false)}>
                关闭
              </button>
            </div>
            <label className="app-form-label">
              <span>知识库</span>
              <select className="app-input" value={pickerKbId} onChange={(e) => setPickerKbId(e.target.value)} disabled={!allKbs.length}>
                {!allKbs.length && <option value="">暂无知识库</option>}
                {allKbs.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </select>
            </label>
            <ul className="mt-3 max-h-[48vh] space-y-2 overflow-y-auto">
              {pickerEntries.map((e) => (
                <li key={e.id}>
                  <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#e5e7eb] px-3 py-2 text-sm hover:bg-[#f9fafb]">
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={!!pickerPick[e.id]}
                      onChange={() => setPickerPick((p) => ({ ...p, [e.id]: !p[e.id] }))}
                    />
                    <span>{e.title}</span>
                  </label>
                </li>
              ))}
              {!pickerEntries.length && pickerKbId && <li className="text-sm text-[#9ca3af]">该库暂无条目或加载中</li>}
            </ul>
            <div className="mt-4 flex gap-2">
              <button type="button" className="app-button flex-1" onClick={confirmPickerEntries}>
                确定
              </button>
              <button type="button" className="app-button-secondary flex-1" onClick={() => setEntryModalOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

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
