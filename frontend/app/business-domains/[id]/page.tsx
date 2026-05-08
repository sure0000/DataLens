"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../../lib/api";
import ConfirmDialog from "../../../components/ConfirmDialog";
import EmptyState from "../../../components/EmptyState";
import ListPagination from "../../../components/ListPagination";
import LoadingSkeletonList from "../../../components/LoadingSkeletonList";
import PageHeader from "../../../components/PageHeader";
import Toast from "../../../components/Toast";

type OptionTable = { name: string; comment?: string };
type OptionDatabase = { name: string; tables: OptionTable[] };
type OptionSource = { id: number; name: string; source_type: string; databases: OptionDatabase[] };
type DomainDescription = { id: number; content: string; created_at: string };
type DomainTable = {
  datasource_id: number;
  datasource_name: string;
  database_name: string;
  table_name: string;
  table_comment: string;
  table_description: string;
  table_id?: number;
};
type DomainKb = { id: number; name: string; description: string };
type DomainDetail = {
  domain: { id: number; name: string; created_at: string };
  description?: DomainDescription | null;
  tables: DomainTable[];
  knowledge_bases?: DomainKb[];
};

export default function DomainDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [detail, setDetail] = useState<DomainDetail | null>(null);
  const [options, setOptions] = useState<OptionSource[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const [isDescModalOpen, setIsDescModalOpen] = useState(false);
  const [descDraft, setDescDraft] = useState("");
  const descEditorRef = useRef<HTMLDivElement | null>(null);

  const [isBatchModalOpen, setIsBatchModalOpen] = useState(false);
  const [tableKeyword, setTableKeyword] = useState("");
  const [tablePage, setTablePage] = useState(1);
  const [tablePageSize, setTablePageSize] = useState(10);
  const [selectedDatabases, setSelectedDatabases] = useState<Record<string, boolean>>({});
  const [selectedTables, setSelectedTables] = useState<Record<string, boolean>>({});
  const [batchKeyword, setBatchKeyword] = useState("");
  const [batchPage, setBatchPage] = useState(1);
  const [batchPageSize, setBatchPageSize] = useState(5);
  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [allKnowledgeBases, setAllKnowledgeBases] = useState<{ id: number; name: string }[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<number[]>([]);
  const [savingKb, setSavingKb] = useState(false);
  const [kbModalOpen, setKbModalOpen] = useState(false);
  const [kbPickerPick, setKbPickerPick] = useState<Record<number, boolean>>({});

  async function loadDetail() {
    setLoading(true);
    try {
      const res = await api<DomainDetail>(`/api/business-domains/${params.id}`);
      setDetail(res);
      setSelectedKbIds((res.knowledge_bases || []).map((k) => k.id));
    } finally {
      setLoading(false);
    }
  }

  async function loadOptions() {
    const res = await api<{ datasources: OptionSource[] }>("/api/business-domains/options");
    setOptions(res.datasources);
  }

  useEffect(() => {
    loadDetail();
    loadOptions();
  }, [params.id]);

  useEffect(() => {
    api<{ knowledge_bases: { id: number; name: string }[] }>("/api/knowledge-bases")
      .then((r) => setAllKnowledgeBases(r.knowledge_bases || []))
      .catch(() => setAllKnowledgeBases([]));
  }, []);

  useEffect(() => {
    const hasOpenModal = isDescModalOpen || isBatchModalOpen;
    if (!hasOpenModal) return;
    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key !== "Escape") return;
      if (isDescModalOpen) setIsDescModalOpen(false);
      if (isBatchModalOpen) setIsBatchModalOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isDescModalOpen, isBatchModalOpen]);

  function formatDesc(command: "bold" | "italic" | "insertUnorderedList") {
    if (typeof document !== "undefined") document.execCommand(command);
  }

  function openEditDescriptionModal() {
    setDescDraft(detail?.description?.content || "");
    setIsDescModalOpen(true);
  }

  useEffect(() => {
    if (!isDescModalOpen || !descEditorRef.current) return;
    descEditorRef.current.innerHTML = descDraft;
    descEditorRef.current.focus();
  }, [isDescModalOpen, descDraft]);

  async function saveDescription() {
    const content = (descEditorRef.current?.innerHTML || descDraft).trim();
    if (!content) return;
    setConfirmState({
      title: "确认更新描述？",
      description: "业务域只保留一条描述，保存后将覆盖旧内容。",
      confirmText: "确认更新",
      action: async () => {
        await api(`/api/business-domains/${params.id}/description`, {
          method: "PUT",
          body: JSON.stringify({ content })
        });
        setMessage("描述已更新");
        setIsDescModalOpen(false);
        setDescDraft("");
        loadDetail();
      }
    });
  }

  function toggleDatabase(dsId: number, dbName: string, checked: boolean) {
    const key = `${dsId}::${dbName}`;
    setSelectedDatabases((prev) => ({ ...prev, [key]: checked }));
    if (checked) {
      setSelectedTables((prev) => {
        const next = { ...prev };
        Object.keys(next).forEach((k) => {
          if (k.startsWith(`${key}::`)) delete next[k];
        });
        return next;
      });
    }
  }

  function toggleTable(dsId: number, dbName: string, tableName: string, checked: boolean) {
    const dbKey = `${dsId}::${dbName}`;
    const tableKey = `${dbKey}::${tableName}`;
    setSelectedTables((prev) => ({ ...prev, [tableKey]: checked }));
    if (checked) setSelectedDatabases((prev) => ({ ...prev, [dbKey]: false }));
  }

  function clearBatchSelections() {
    setSelectedDatabases({});
    setSelectedTables({});
  }

  async function saveBatchSelections() {
    const selectionsMap = new Map<string, { datasource_id: number; database_name: string; table_names: string[] }>();
    Object.entries(selectedDatabases).forEach(([key, checked]) => {
      if (!checked) return;
      const [ds, db] = key.split("::");
      selectionsMap.set(key, { datasource_id: Number(ds), database_name: db, table_names: [] });
    });
    Object.entries(selectedTables).forEach(([key, checked]) => {
      if (!checked) return;
      const [ds, db, table] = key.split("::");
      const dbKey = `${ds}::${db}`;
      if (selectedDatabases[dbKey]) return;
      const current = selectionsMap.get(dbKey) ?? { datasource_id: Number(ds), database_name: db, table_names: [] };
      current.table_names.push(table);
      selectionsMap.set(dbKey, current);
    });
    setConfirmState({
      title: "确认保存数据表选择？",
      description: "这将修改当前业务域的数据表范围。",
      confirmText: "确认保存",
      action: async () => {
        await api(`/api/business-domains/${params.id}/selections`, {
          method: "POST",
          body: JSON.stringify(Array.from(selectionsMap.values()))
        });
        setMessage("数据表已批量添加");
        setIsBatchModalOpen(false);
        clearBatchSelections();
        setBatchKeyword("");
        loadDetail();
      }
    });
  }

  const sortedTables = useMemo(() => {
    if (!detail) return [];
    return [...detail.tables].sort((a, b) => {
      const tableDiff = a.table_name.localeCompare(b.table_name, "zh-Hans-CN");
      if (tableDiff !== 0) return tableDiff;
      return a.database_name.localeCompare(b.database_name, "zh-Hans-CN");
    });
  }, [detail]);
  const filteredTables = useMemo(() => {
    const q = tableKeyword.trim().toLowerCase();
    if (!q) return sortedTables;
    return sortedTables.filter((t) =>
      [t.database_name, t.table_name, t.table_comment, t.table_description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [sortedTables, tableKeyword]);
  const pagedTables = useMemo(() => {
    const start = (tablePage - 1) * tablePageSize;
    return filteredTables.slice(start, start + tablePageSize);
  }, [filteredTables, tablePage, tablePageSize]);

  const filteredOptions = useMemo(() => {
    const keyword = batchKeyword.trim().toLowerCase();
    if (!keyword) return options;

    return options
      .map((source) => {
        const sourceMatched = source.name.toLowerCase().includes(keyword) || source.source_type.toLowerCase().includes(keyword);
        const databases = source.databases
          .map((db) => {
            if (sourceMatched) return db;
            const dbMatched = db.name.toLowerCase().includes(keyword);
            const tables = dbMatched
              ? db.tables
              : db.tables.filter(
                  (t) =>
                    t.name.toLowerCase().includes(keyword) ||
                    (t.comment || "").toLowerCase().includes(keyword)
                );
            return { ...db, tables: [...tables].sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN")) };
          })
          .filter((db) => db.tables.length > 0)
          .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));

        const sourceDatabases = sourceMatched
          ? source.databases
              .map((db) => ({ ...db, tables: [...db.tables].sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN")) }))
              .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"))
          : databases;
        return { ...source, databases: sourceDatabases };
      })
      .filter((source) => source.databases.length > 0)
      .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  }, [options, batchKeyword]);
  const pagedBatchOptions = useMemo(() => {
    const start = (batchPage - 1) * batchPageSize;
    return filteredOptions.slice(start, start + batchPageSize);
  }, [filteredOptions, batchPage, batchPageSize]);

  const batchStats = useMemo(() => {
    const visibleDatabases = filteredOptions.reduce((acc, source) => acc + source.databases.length, 0);
    const visibleTables = filteredOptions.reduce(
      (acc, source) => acc + source.databases.reduce((dbAcc, db) => dbAcc + db.tables.length, 0),
      0
    );
    const selectedDatabaseCount = Object.values(selectedDatabases).filter(Boolean).length;
    const selectedTableCount = Object.entries(selectedTables).reduce((acc, [key, checked]) => {
      if (!checked) return acc;
      const [ds, db] = key.split("::");
      if (selectedDatabases[`${ds}::${db}`]) return acc;
      return acc + 1;
    }, 0);
    return {
      visibleDatabases,
      visibleTables,
      selectedDatabaseCount,
      selectedTableCount,
      hasSelection: selectedDatabaseCount + selectedTableCount > 0
    };
  }, [filteredOptions, selectedDatabases, selectedTables]);

  useEffect(() => {
    setTablePage(1);
  }, [tableKeyword, tablePageSize, detail?.tables.length]);

  useEffect(() => {
    setBatchPage(1);
  }, [batchKeyword, batchPageSize, filteredOptions.length]);

  function selectAllVisibleDatabases() {
    const nextDatabases = { ...selectedDatabases };
    const nextTables = { ...selectedTables };
    filteredOptions.forEach((source) => {
      source.databases.forEach((db) => {
        const dbKey = `${source.id}::${db.name}`;
        nextDatabases[dbKey] = true;
        Object.keys(nextTables).forEach((tableKey) => {
          if (tableKey.startsWith(`${dbKey}::`)) delete nextTables[tableKey];
        });
      });
    });
    setSelectedDatabases(nextDatabases);
    setSelectedTables(nextTables);
  }

  function selectAllVisibleTables() {
    const nextDatabases = { ...selectedDatabases };
    const nextTables = { ...selectedTables };
    filteredOptions.forEach((source) => {
      source.databases.forEach((db) => {
        const dbKey = `${source.id}::${db.name}`;
        nextDatabases[dbKey] = false;
        db.tables.forEach((table) => {
          nextTables[`${dbKey}::${table.name}`] = true;
        });
      });
    });
    setSelectedDatabases(nextDatabases);
    setSelectedTables(nextTables);
  }

  function clearVisibleSelections() {
    const nextDatabases = { ...selectedDatabases };
    const nextTables = { ...selectedTables };
    filteredOptions.forEach((source) => {
      source.databases.forEach((db) => {
        const dbKey = `${source.id}::${db.name}`;
        delete nextDatabases[dbKey];
        Object.keys(nextTables).forEach((tableKey) => {
          if (tableKey.startsWith(`${dbKey}::`)) delete nextTables[tableKey];
        });
      });
    });
    setSelectedDatabases(nextDatabases);
    setSelectedTables(nextTables);
  }

  function openKbPickerModal() {
    const next: Record<number, boolean> = {};
    allKnowledgeBases.forEach((kb) => {
      next[kb.id] = selectedKbIds.includes(kb.id);
    });
    setKbPickerPick(next);
    setKbModalOpen(true);
  }

  function confirmKbPicker() {
    const picked = allKnowledgeBases.filter((kb) => kbPickerPick[kb.id]).map((kb) => kb.id);
    setSelectedKbIds(picked);
    setKbModalOpen(false);
  }

  async function saveDomainKnowledgeBases() {
    setSavingKb(true);
    try {
      await api(`/api/business-domains/${params.id}/knowledge-bases`, {
        method: "PUT",
        body: JSON.stringify({ knowledge_base_ids: selectedKbIds })
      });
      setMessage("已保存关联知识库");
      loadDetail();
    } finally {
      setSavingKb(false);
    }
  }

  async function removeDomain() {
    setConfirmState({
      title: "确认删除业务域？",
      description: `将删除「${detail?.domain.name || params.id}」，该操作不可撤销。`,
      confirmText: "确认删除",
      danger: true,
      action: async () => {
        await api(`/api/business-domains/${params.id}`, { method: "DELETE" });
        router.push("/");
      }
    });
  }

  async function handleConfirm() {
    if (!confirmState) return;
    setConfirmLoading(true);
    try {
      await confirmState.action();
      setConfirmState(null);
    } finally {
      setConfirmLoading(false);
    }
  }

  if (!detail) return <main className="app-page text-app-secondary">正在加载业务域详情...</main>;

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", href: "/" }, { label: "业务域", href: "/" }, { label: detail.domain.name }]}
        title={detail.domain.name}
        meta={`创建时间：${new Date(detail.domain.created_at).toLocaleString()}`}
        actions={
          <div className="app-toolbar">
            <button className="app-button-secondary" onClick={openEditDescriptionModal}>
              编辑描述
            </button>
            <button className="app-button-danger" onClick={removeDomain}>
              删除业务域
            </button>
          </div>
        }
      />

      <Toast message={message} tone="success" onClose={() => setMessage("")} />
      {loading && <LoadingSkeletonList count={2} />}

      <section className="app-card mt-4 p-4">
        <h2 className="app-section-title">业务描述</h2>
        <div className="mt-3 space-y-2">
          <div className="rounded-lg border border-app-border bg-white p-3">
            {detail.description?.content ? (
              <div className="prose prose-sm max-w-none text-sm" dangerouslySetInnerHTML={{ __html: detail.description.content }} />
            ) : (
              <p className="app-text-muted text-sm">暂无描述</p>
            )}
          </div>
        </div>
      </section>

      <section className="app-card mt-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="app-section-title">关联知识库</h2>
          <button type="button" className={`app-button ${savingKb ? "is-loading" : ""}`} onClick={saveDomainKnowledgeBases} disabled={savingKb}>
            {savingKb ? "保存中…" : "保存"}
          </button>
        </div>
        <p className="app-text-muted mt-1 text-xs">
          Copilot 会话可选择本业务域后，将自动在这些知识库中做语义检索，并结合表侧关联的知识库与固定条目。
        </p>
        <div className="mt-3 rounded-lg border border-app-border bg-app-hover p-3">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="app-button-secondary text-xs" onClick={openKbPickerModal}>
              添加知识库
            </button>
          </div>
          {!selectedKbIds.length ? (
            <p className="mt-2 text-xs text-app-muted">未选择知识库</p>
          ) : (
            <p className="mt-2 text-xs text-app-secondary">
              已选择 {selectedKbIds.length} 个：
              {selectedKbIds.map((id) => allKnowledgeBases.find((kb) => kb.id === id)?.name || `#${id}`).join("、")}
            </p>
          )}
        </div>
      </section>

      {kbModalOpen && (
        <div
          className="app-modal-backdrop"
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
            {!allKnowledgeBases.length ? (
              <p className="text-sm text-app-muted">暂无知识库，请先在「知识库」中创建。</p>
            ) : (
              <ul className="max-h-[56vh] space-y-2 overflow-y-auto">
                {allKnowledgeBases.map((kb) => (
                  <li key={kb.id}>
                    <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-app-border px-3 py-2 text-sm hover:bg-app-hover">
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

      <section className="app-card mt-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="app-section-title">数据表列表</h2>
          <div className="app-toolbar">
            <input
              className="app-input app-toolbar-input"
              placeholder="搜索数据库/数据表/说明"
              value={tableKeyword}
              onChange={(e) => setTableKeyword(e.target.value)}
            />
            <button
              className="app-button app-toolbar-action"
              onClick={() => {
                setBatchKeyword("");
                setIsBatchModalOpen(true);
              }}
            >
              批量添加数据表
            </button>
          </div>
        </div>
        <div className="mt-3 overflow-x-auto rounded-lg border border-app-border">
          <table className="app-table min-w-[640px] md:min-w-[860px]">
            <thead>
              <tr>
                <th>数据库</th>
                <th>数据表</th>
                <th>备注</th>
                <th>数据表描述</th>
              </tr>
            </thead>
            <tbody>
              {pagedTables.map((t) => (
                <tr key={`${t.datasource_id}-${t.database_name}-${t.table_name}`}>
                  <td>
                    <Link
                      className="app-link"
                      href={`/datasources/${t.datasource_id}/database/${encodeURIComponent(t.database_name)}`}
                    >
                      {t.database_name}
                    </Link>
                  </td>
                  <td>
                    {t.table_id ? (
                      <Link className="app-link" href={`/table/${t.table_id}`}>
                        {t.table_name}
                      </Link>
                    ) : (
                      <span>{t.table_name}</span>
                    )}
                  </td>
                  <td className="app-text-secondary-strong">{t.table_comment || "-"}</td>
                  <td className="app-text-secondary-strong">{t.table_description || "-"}</td>
                </tr>
              ))}
              {!filteredTables.length && (
                <tr>
                  <td className="app-text-muted" colSpan={4}>
                    暂无匹配数据表，请调整关键词或点击右上角“批量添加数据表”
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {!!filteredTables.length && (
          <ListPagination
            page={tablePage}
            pageSize={tablePageSize}
            total={filteredTables.length}
            onPageChange={setTablePage}
            onPageSizeChange={setTablePageSize}
          />
        )}
      </section>

      {isDescModalOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setIsDescModalOpen(false)}>
          <div
            className="app-card w-full max-w-2xl max-h-[88vh] overflow-auto p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-domain-desc-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 id="edit-domain-desc-title" className="app-section-title">
                编辑业务描述
              </h3>
              <button className="app-control-button" onClick={() => setIsDescModalOpen(false)}>
                关闭
              </button>
            </div>
            <div className="mt-3 flex gap-2">
              <button className="app-button-secondary app-button-xs" onClick={() => formatDesc("bold")}>
                粗体
              </button>
              <button className="app-button-secondary app-button-xs" onClick={() => formatDesc("italic")}>
                斜体
              </button>
              <button className="app-button-secondary app-button-xs" onClick={() => formatDesc("insertUnorderedList")}>
                列表
              </button>
            </div>
            <div
              ref={descEditorRef}
              className="mt-2 min-h-[180px] rounded-lg border border-app-border bg-white p-3 text-sm text-app-primary outline-none"
              contentEditable
              suppressContentEditableWarning
            />
            <button className="app-button mt-3" onClick={saveDescription}>
              保存描述
            </button>
          </div>
        </div>
      )}

      {isBatchModalOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setIsBatchModalOpen(false)}>
          <div
            className="app-card w-full max-w-5xl max-h-[88vh] overflow-hidden p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="batch-select-table-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 id="batch-select-table-title" className="app-section-title">
                批量添加数据表
              </h3>
              <button className="app-control-button" onClick={() => setIsBatchModalOpen(false)}>
                关闭
              </button>
            </div>

            <div className="mt-3 grid gap-3">
              <div className="flex flex-col gap-2 rounded-lg border border-app-border bg-app-hover p-3 sm:flex-row sm:items-center sm:justify-between">
                <input
                  className="app-input sm:max-w-sm"
                  value={batchKeyword}
                  onChange={(e) => setBatchKeyword(e.target.value)}
                  placeholder="搜索数据源 / 数据库 / 数据表 / 备注"
                />
                <div className="flex flex-wrap gap-2">
                  <button className="app-button-secondary app-button-xs" onClick={selectAllVisibleDatabases}>
                    选中当前结果的整库
                  </button>
                  <button className="app-button-secondary app-button-xs" onClick={selectAllVisibleTables}>
                    选中当前结果的全部表
                  </button>
                  <button className="app-button-secondary app-button-xs" onClick={clearVisibleSelections}>
                    清空当前结果选择
                  </button>
                </div>
              </div>

              <div className="app-text-muted flex flex-wrap items-center gap-2 text-xs">
                <span>当前展示：{filteredOptions.length} 个数据源</span>
                <span>•</span>
                <span>{batchStats.visibleDatabases} 个数据库</span>
                <span>•</span>
                <span>{batchStats.visibleTables} 张数据表</span>
                <span className="ml-2 rounded-full border border-emerald-300/50 bg-emerald-50 px-2 py-1 text-emerald-700">
                  已选择：整库 {batchStats.selectedDatabaseCount} / 单表 {batchStats.selectedTableCount}
                </span>
              </div>
            </div>

            <div className="mt-3 max-h-[52vh] space-y-3 overflow-auto pr-1">
              {pagedBatchOptions.map((s) => (
                <div key={s.id} className="rounded-lg border border-app-border bg-white p-3">
                  <p className="font-medium text-app-primary">
                    {s.name} <span className="text-xs text-app-secondary">({s.source_type})</span>
                  </p>
                  <div className="mt-2 space-y-2">
                    {s.databases.map((db) => {
                      const dbKey = `${s.id}::${db.name}`;
                      const tableSelectedCount = db.tables.reduce((acc, table) => {
                        const tableKey = `${dbKey}::${table.name}`;
                        if (!selectedTables[tableKey] || selectedDatabases[dbKey]) return acc;
                        return acc + 1;
                      }, 0);
                      return (
                        <div key={dbKey} className="rounded-lg border border-app-soft bg-app-hover p-2.5">
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={!!selectedDatabases[dbKey]}
                              onChange={(e) => toggleDatabase(s.id, db.name, e.target.checked)}
                            />
                            <span className="font-medium">{db.name}</span>
                            <span className="app-text-muted text-xs">整库选择</span>
                            {!selectedDatabases[dbKey] && tableSelectedCount > 0 && (
                              <span className="rounded-full border border-sky-300/50 bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700">
                                已选 {tableSelectedCount} 张表
                              </span>
                            )}
                            {selectedDatabases[dbKey] && (
                              <span className="rounded-full border border-emerald-300/50 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">
                                整库已选
                              </span>
                            )}
                          </label>
                          <div className="mt-2 ml-6 grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                            {db.tables.map((t) => {
                              const tableKey = `${dbKey}::${t.name}`;
                              return (
                                <label key={tableKey} className="flex items-start gap-2 rounded-md border border-app-border bg-white px-2 py-1.5 text-xs text-app-ink">
                                  <input
                                    type="checkbox"
                                    checked={!!selectedTables[tableKey]}
                                    disabled={!!selectedDatabases[dbKey]}
                                    onChange={(e) => toggleTable(s.id, db.name, t.name, e.target.checked)}
                                  />
                                  <span className="min-w-0">
                                    <span className="block break-all">{t.name}</span>
                                    {!!t.comment && <span className="mt-0.5 block text-[11px] text-app-muted">{t.comment}</span>}
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
              {!filteredOptions.length && (
                <EmptyState title="未匹配到可选数据表" description="你可以更换关键词，或先在数据源中完成表分析后再回来选择。" />
              )}
            </div>
            {!!filteredOptions.length && (
              <ListPagination
                page={batchPage}
                pageSize={batchPageSize}
                total={filteredOptions.length}
                onPageChange={setBatchPage}
                onPageSizeChange={setBatchPageSize}
                pageSizeOptions={[3, 5, 10]}
              />
            )}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-app-border bg-app-hover p-3">
              <p className="app-text-secondary-strong text-sm">
                将添加 <span className="font-semibold text-app-primary">{batchStats.selectedDatabaseCount}</span> 个整库选择和{" "}
                <span className="font-semibold text-app-primary">{batchStats.selectedTableCount}</span> 张单表选择
              </p>
              <div className="flex flex-wrap gap-2">
                <button className="app-button-secondary" onClick={clearBatchSelections}>
                  清空全部选择
                </button>
                <button className="app-button-secondary" onClick={() => setIsBatchModalOpen(false)}>
                  取消
                </button>
                <button className="app-button" onClick={saveBatchSelections} disabled={!batchStats.hasSelection}>
                  保存选择
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || ""}
        description={confirmState?.description}
        confirmText={confirmState?.confirmText}
        danger={!!confirmState?.danger}
        loading={confirmLoading}
        onCancel={() => setConfirmState(null)}
        onConfirm={handleConfirm}
      />
    </main>
  );
}
