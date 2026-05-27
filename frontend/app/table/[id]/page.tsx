"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import ColumnCard from "../../../components/ColumnCard";
import { api } from "../../../lib/api";
import { badgeExclusive } from "../../../lib/themeClasses";
import PageHeader from "../../../components/PageHeader";
import CopilotValidatePanel from "../../../components/ontology/CopilotValidatePanel";
import KnowledgeBasePicker from "../../../components/knowledge-bases/KnowledgeBasePicker";

type Detail = {
  table: {
    id?: number;
    table_name: string;
    database_name: string;
    datasource_id?: number | null;
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
  const [savingLinks, setSavingLinks] = useState(false);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkModalTab, setLinkModalTab] = useState<"kb" | "entry">("kb");
  const [modalKbIds, setModalKbIds] = useState<number[]>([]);
  const [modalEntryKbId, setModalEntryKbId] = useState("");
  const [modalEntryRows, setModalEntryRows] = useState<{ id: number; title: string }[]>([]);
  const [modalEntryPick, setModalEntryPick] = useState<Record<number, boolean>>({});
  const modalEntryDraftRef = useRef<Set<number>>(new Set());
  const [knowledgeExpanded, setKnowledgeExpanded] = useState(false);

  useEffect(() => {
    api<{ knowledge_bases: { id: number; name: string }[] }>("/api/knowledge-bases")
      .then((r) => setAllKbs(r.knowledge_bases || []))
      .catch(() => setAllKbs([]));
  }, []);

  useEffect(() => {
    api<Detail>(`/api/table/${params.id}`).then((d) => setDetail(d));
  }, [params.id]);

  useEffect(() => {
    if (!linkModalOpen || linkModalTab !== "entry" || !modalEntryKbId) return;
    const kbNum = Number(modalEntryKbId);
    if (!Number.isFinite(kbNum)) return;
    api<{ entries: { id: number; title: string }[] }>(`/api/knowledge-bases/${kbNum}`).then((res) => {
      const entries = res.entries || [];
      setModalEntryRows(entries);
      const draft = modalEntryDraftRef.current;
      const next: Record<number, boolean> = {};
      entries.forEach((e) => {
        next[e.id] = draft.has(e.id);
      });
      setModalEntryPick(next);
    });
  }, [linkModalOpen, linkModalTab, modalEntryKbId]);

  function openLinkModal() {
    if (!detail) return;
    setModalKbIds((detail.knowledge_bases || []).map((kb) => kb.id));
    modalEntryDraftRef.current = new Set((detail.knowledge_entries || []).map((e) => e.id));
    setModalEntryKbId(allKbs[0] ? String(allKbs[0].id) : "");
    setModalEntryRows([]);
    setModalEntryPick({});
    setLinkModalTab("kb");
    setLinkModalOpen(true);
  }

  function toggleModalEntry(entryId: number) {
    const draft = modalEntryDraftRef.current;
    if (draft.has(entryId)) draft.delete(entryId);
    else draft.add(entryId);
    setModalEntryPick((prev) => ({ ...prev, [entryId]: draft.has(entryId) }));
  }

  async function persistKnowledgeLinks(kbIds: number[], entryIds: number[]) {
    setSavingLinks(true);
    try {
      await api(`/api/table/${params.id}/knowledge-links`, {
        method: "PUT",
        body: JSON.stringify({ knowledge_base_ids: kbIds, knowledge_entry_ids: entryIds })
      });
      const d = await api<Detail>(`/api/table/${params.id}`);
      setDetail(d);
    } finally {
      setSavingLinks(false);
    }
  }

  async function saveLinkModal() {
    const kbIds = modalKbIds;
    const entryIds = Array.from(modalEntryDraftRef.current);
    await persistKnowledgeLinks(kbIds, entryIds);
    setLinkModalOpen(false);
  }

  async function removeKbAssociation(kbId: number) {
    if (!detail) return;
    const kbIds = (detail.knowledge_bases || []).filter((k) => k.id !== kbId).map((k) => k.id);
    const entryIds = (detail.knowledge_entries || []).map((e) => e.id);
    await persistKnowledgeLinks(kbIds, entryIds);
  }

  async function removeEntryAssociation(entryId: number) {
    if (!detail) return;
    const kbIds = (detail.knowledge_bases || []).map((k) => k.id);
    const entryIds = (detail.knowledge_entries || []).filter((e) => e.id !== entryId).map((e) => e.id);
    await persistKnowledgeLinks(kbIds, entryIds);
  }

  function kbDisplayName(kbId: number) {
    return allKbs.find((k) => k.id === kbId)?.name || detail?.knowledge_bases?.find((k) => k.id === kbId)?.name || `#${kbId}`;
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

  if (!detail) return <main className="app-page text-app-secondary">加载中...</main>;

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
  const primaryKbId = detail.knowledge_bases?.[0]?.id;

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "数据源", href: "/datasources" },
          ...(detail.table.datasource_id
            ? [{ label: detail.table.datasource_name || String(detail.table.datasource_id), href: `/datasources/${detail.table.datasource_id}` }]
            : []),
          ...(detail.table.datasource_id && detail.table.database_name
            ? [{ label: detail.table.database_name, href: `/datasources/${detail.table.datasource_id}/database/${encodeURIComponent(detail.table.database_name)}` }]
            : []),
          { label: detail.table.table_name },
        ]}
        title={detail.table.table_name}
        subtitle={`${detail.table.datasource_name || ""}${detail.table.datasource_name ? " / " : ""}${detail.table.database_name}`}
        meta={
          <span className="flex flex-wrap items-center gap-3">
            <span>行数：{detail.table.row_count?.toLocaleString() ?? "—"}</span>
            {detail.table.domain_names.length > 0 ? (
              <span className="flex flex-wrap gap-1">
                {detail.table.domain_names.map((d) => (
                  <span key={d} className="rounded-full border border-app-activeBorder bg-app-activeBg px-2 py-0.5 text-xs font-medium text-app-link">
                    {d}
                  </span>
                ))}
              </span>
            ) : (
              <span className="text-xs text-app-muted">暂未关联业务域</span>
            )}
          </span>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {primaryKbId ? (
              <CopilotValidatePanel
                kbId={primaryKbId}
                tableId={Number(params.id)}
                compact
                onApplied={() => {
                  api<Detail>(`/api/table/${params.id}`).then((d) => setDetail(d));
                }}
              />
            ) : null}
            <a className="app-button" href={`/copilot?table=${encodeURIComponent(params.id)}`}>
              去 Copilot 分析
            </a>
          </div>
        }
      />

      <section className="app-card mt-6 p-4">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3"
          onClick={() => setKnowledgeExpanded((v) => !v)}
        >
          <div className="flex items-center gap-2">
            <h2 className="app-section-title">关联知识</h2>
            {!knowledgeExpanded && (
              <span className="text-xs text-app-muted">
                {(detail.knowledge_bases?.length || 0) + (detail.knowledge_entries?.length || 0) > 0
                  ? `${detail.knowledge_bases?.length || 0} 个知识库、${detail.knowledge_entries?.length || 0} 个条目`
                  : "暂无关联"}
              </span>
            )}
          </div>
          <svg
            className={`h-4 w-4 shrink-0 text-app-secondary transition-transform ${knowledgeExpanded ? "rotate-180" : ""}`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          >
            <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {knowledgeExpanded && (
          <>
            <p className="app-text-muted mt-2 text-xs">
              关联整库后，Copilot 在本表上下文中对该库做语义检索；关联条目则全文注入。
            </p>
            {!(detail.knowledge_bases?.length || detail.knowledge_entries?.length) ? (
              <p className="mt-3 rounded-lg border border-dashed border-app-border bg-app-hover px-4 py-5 text-center text-sm text-app-muted">
                点击「添加知识」选择知识库或具体条目。
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-app-subtle rounded-xl border border-app-border bg-[var(--app-card-bg)]">
                {(detail.knowledge_bases || []).map((kb) => (
                  <li key={`kb-${kb.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-app-activeBorder bg-app-activeBg px-2 py-0.5 text-[11px] font-medium text-app-chipText">知识库</span>
                        <span className="font-medium text-app-ink text-sm">{kb.name}</span>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <Link className="app-button-secondary text-xs no-underline" href={`/knowledge-bases/${kb.id}`}>查看</Link>
                      <button type="button" className="app-control-button text-xs text-app-secondary hover:app-text-danger" disabled={savingLinks} onClick={() => removeKbAssociation(kb.id)}>移除</button>
                    </div>
                  </li>
                ))}
                {(detail.knowledge_entries || []).map((en) => (
                  <li key={`ent-${en.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badgeExclusive}`}>条目</span>
                        <span className="font-medium text-app-ink text-sm">{en.title}</span>
                        <span className="text-xs text-app-muted">（{kbDisplayName(en.knowledge_base_id)}）</span>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <Link className="app-button-secondary text-xs no-underline" href={`/knowledge-bases/${en.knowledge_base_id}#entry-${en.id}`}>查看</Link>
                      <button type="button" className="app-control-button text-xs text-app-secondary hover:app-text-danger" disabled={savingLinks} onClick={() => removeEntryAssociation(en.id)}>移除</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <button type="button" className="app-button mt-3" onClick={openLinkModal}>
              添加知识
            </button>
          </>
        )}
      </section>

      {linkModalOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => !savingLinks && setLinkModalOpen(false)}>
          <div
            className="app-card max-h-[88vh] w-full max-w-lg overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between gap-2">
              <h2 className="app-section-title">添加知识</h2>
              <button type="button" className="app-control-button shrink-0" onClick={() => !savingLinks && setLinkModalOpen(false)}>
                关闭
              </button>
            </div>
            <div className="mb-4 flex rounded-lg border border-app-border p-0.5">
              <button
                type="button"
                className={`flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  linkModalTab === "kb" ? "bg-app-primary text-white" : "text-app-secondary hover:text-app-ink"
                }`}
                onClick={() => setLinkModalTab("kb")}
              >
                关联整库
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  linkModalTab === "entry" ? "bg-app-primary text-white" : "text-app-secondary hover:text-app-ink"
                }`}
                onClick={() => setLinkModalTab("entry")}
              >
                关联条目
              </button>
            </div>

            {linkModalTab === "kb" ? (
              !allKbs.length ? (
                <p className="text-sm text-app-muted">暂无知识库，请先在「知识库」中创建。</p>
              ) : (
                <KnowledgeBasePicker
                  mode="multiple"
                  options={allKbs}
                  selectedIds={modalKbIds}
                  onChange={setModalKbIds}
                  searchPlaceholder="搜索并选择关联知识库"
                />
              )
            ) : (
              <>
                <label className="app-form-label">
                  <span className="text-xs">选择知识库以列出条目</span>
                  <select
                    className="app-input"
                    value={modalEntryKbId}
                    onChange={(e) => setModalEntryKbId(e.target.value)}
                    disabled={!allKbs.length}
                  >
                    {!allKbs.length && <option value="">暂无知识库</option>}
                    {allKbs.map((kb) => (
                      <option key={kb.id} value={kb.id}>
                        {kb.name}
                      </option>
                    ))}
                  </select>
                </label>
                <ul className="mt-3 max-h-[44vh] space-y-2 overflow-y-auto">
                  {modalEntryRows.map((e) => (
                    <li key={e.id}>
                      <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-app-border px-3 py-2.5 text-sm hover:bg-app-hover">
                        <input
                          type="checkbox"
                          className="mt-0.5"
                          checked={!!modalEntryPick[e.id]}
                          onChange={() => toggleModalEntry(e.id)}
                        />
                        <span>{e.title}</span>
                      </label>
                    </li>
                  ))}
                  {!modalEntryRows.length && modalEntryKbId && (
                    <li className="py-4 text-center text-sm text-app-muted">该库暂无条目或加载中…</li>
                  )}
                </ul>
              </>
            )}

            <div className="mt-5 flex gap-2 border-t border-app-subtle pt-4">
              <button type="button" className={`app-button flex-1 ${savingLinks ? "is-loading" : ""}`} disabled={savingLinks} onClick={saveLinkModal}>
                {savingLinks ? "保存中…" : "保存"}
              </button>
              <button type="button" className="app-button-secondary flex-1" disabled={savingLinks} onClick={() => setLinkModalOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Summary tabs */}
      {visibleTabs.length > 0 && (
        <div className="mt-8">
          {/* Tab bar */}
          <div className="flex gap-1 overflow-x-auto border-b border-app-border pb-px">
            {visibleTabs.map((tab) => {
              const isActive = activeTab === tab;
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
                    isActive
                      ? "border-app-primary text-app-primary"
                      : "border-transparent text-app-secondary hover:text-app-ink"
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
                return <p className="whitespace-pre-wrap break-words text-sm leading-7 text-app-ink">{detail.summary.summary}</p>;
              }

              return (
                <ul className="divide-y divide-app-subtle rounded-xl border border-app-border bg-app-card">
                  {items.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-3 px-4 py-3">
                      <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-app-hover text-[10px] font-semibold text-app-secondary">
                        {idx + 1}
                      </span>
                      <span className="break-words text-sm leading-6 text-app-ink">{item}</span>
                    </li>
                  ))}
                </ul>
              );
            })()}
          </div>
        </div>
      )}

      {/* Columns */}
      <div className="mt-10">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="app-section-title">
            字段列表
            <span className="ml-2 text-sm font-normal text-app-secondary">({filteredColumns.length} / {detail.columns.length})</span>
          </h2>
          <input
            className="app-input w-full max-w-xs"
            placeholder="搜索字段名 / 类型 / 语义"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        {filteredColumns.length > 0 ? (
          <div className="overflow-hidden rounded-xl border border-app-border bg-[var(--app-card-bg)]">
            {filteredColumns.map((c, i) => (
              <ColumnCard col={c} key={`${c.column_name}-${i}`} isLast={i === filteredColumns.length - 1} />
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-app-secondary">未匹配到字段</p>
        )}
      </div>
    </main>
  );
}
