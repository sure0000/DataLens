"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import ConfirmDialog from "../../../components/ConfirmDialog";
import EmptyState from "../../../components/EmptyState";
import PageHeader from "../../../components/PageHeader";
import Toast from "../../../components/Toast";
import { api } from "../../../lib/api";

type KB = { id: number; name: string; description: string; created_at: string };
type Entry = {
  id: number;
  knowledge_base_id: number;
  title: string;
  body: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type Hit = { entry_id: number; title: string; snippet: string; score_hint: string };

export default function KnowledgeBaseDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const kbId = Number(params.id);
  const [kb, setKb] = useState<KB | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);
  const [entryKeyword, setEntryKeyword] = useState("");

  const [isKbEditOpen, setIsKbEditOpen] = useState(false);
  const [kbNameDraft, setKbNameDraft] = useState("");
  const [kbDescDraft, setKbDescDraft] = useState("");

  const [isEntryModalOpen, setIsEntryModalOpen] = useState(false);
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  const [entryTitle, setEntryTitle] = useState("");
  const [entryBody, setEntryBody] = useState("");
  const [entrySaving, setEntrySaving] = useState(false);

  const [confirmState, setConfirmState] = useState<{
    title: string;
    description?: string;
    confirmText?: string;
    danger?: boolean;
    action: () => Promise<void> | void;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  async function load() {
    if (!Number.isFinite(kbId)) return;
    setLoading(true);
    try {
      const res = await api<{ knowledge_base: KB; entries: Entry[] }>(`/api/knowledge-bases/${kbId}`);
      setKb(res.knowledge_base);
      setEntries(res.entries);
    } catch {
      setKb(null);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [kbId]);

  useEffect(() => {
    const open = isKbEditOpen || isEntryModalOpen;
    if (!open) return;
    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") {
        setIsKbEditOpen(false);
        setIsEntryModalOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isKbEditOpen, isEntryModalOpen]);

  function openKbEdit() {
    if (!kb) return;
    setKbNameDraft(kb.name);
    setKbDescDraft(kb.description || "");
    setIsKbEditOpen(true);
  }

  async function saveKbMeta() {
    if (!kbNameDraft.trim()) return;
    await api(`/api/knowledge-bases/${kbId}`, {
      method: "PUT",
      body: JSON.stringify({ name: kbNameDraft.trim(), description: kbDescDraft.trim() })
    });
    setMessage("知识库信息已更新");
    setIsKbEditOpen(false);
    load();
  }

  function openNewEntry() {
    setEditingEntryId(null);
    setEntryTitle("");
    setEntryBody("");
    setIsEntryModalOpen(true);
  }

  function openEditEntry(e: Entry) {
    setEditingEntryId(e.id);
    setEntryTitle(e.title);
    setEntryBody(e.body);
    setIsEntryModalOpen(true);
  }

  async function saveEntry() {
    if (!entryTitle.trim()) return;
    setEntrySaving(true);
    try {
      if (editingEntryId) {
        await api(`/api/knowledge-bases/${kbId}/entries/${editingEntryId}`, {
          method: "PUT",
          body: JSON.stringify({ title: entryTitle.trim(), body: entryBody })
        });
        setMessage("条目已更新");
      } else {
        await api(`/api/knowledge-bases/${kbId}/entries`, {
          method: "POST",
          body: JSON.stringify({ title: entryTitle.trim(), body: entryBody })
        });
        setMessage("条目已添加");
      }
      setIsEntryModalOpen(false);
      load();
    } finally {
      setEntrySaving(false);
    }
  }

  function confirmDeleteEntry(id: number) {
    const target = entries.find((e) => e.id === id);
    setConfirmState({
      title: "确认删除该条目？",
      description: `将删除「${target?.title || id}」及其向量索引，不可撤销。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}/entries/${id}`, { method: "DELETE" });
        setMessage("条目已删除");
        load();
      }
    });
  }

  function confirmDeleteKb() {
    if (!kb) return;
    setConfirmState({
      title: "确认删除整个知识库？",
      description: `将删除「${kb.name}」及其中全部条目与索引。`,
      confirmText: "删除",
      danger: true,
      action: async () => {
        await api(`/api/knowledge-bases/${kbId}`, { method: "DELETE" });
        router.push("/knowledge-bases");
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

  async function runSemanticSearch() {
    const q = searchQuery.trim();
    if (!q) return;
    setSearching(true);
    try {
      const res = await api<{ hits: Hit[] }>(`/api/knowledge-bases/${kbId}/search`, {
        method: "POST",
        body: JSON.stringify({ query: q, top_k: 10 })
      });
      setHits(res.hits);
    } finally {
      setSearching(false);
    }
  }

  const filteredEntries = useMemo(() => {
    const q = entryKeyword.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) => e.title.toLowerCase().includes(q) || e.body.toLowerCase().includes(q)
    );
  }, [entries, entryKeyword]);

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  if (!loading && !kb) {
    return (
      <main className="app-page">
        <p className="text-app-secondary">知识库不存在或已删除。</p>
        <Link className="app-link mt-2 inline-block" href="/knowledge-bases">
          返回列表
        </Link>
      </main>
    );
  }

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "首页", href: "/" },
          { label: "知识库", href: "/knowledge-bases" },
          { label: kb?.name || "…" }
        ]}
        title={kb?.name || "知识库"}
        subtitle={kb?.description || "在此维护条目；保存条目时会写入向量索引，供语义检索与下游 RAG 使用。"}
        actions={
          <div className="app-toolbar flex-wrap">
            <button className="app-button-secondary app-toolbar-action" type="button" onClick={openKbEdit}>
              编辑库信息
            </button>
            <button className="app-button app-toolbar-action" type="button" onClick={openNewEntry}>
              新增条目
            </button>
            <button className="app-button-danger app-toolbar-action" type="button" onClick={confirmDeleteKb}>
              删除知识库
            </button>
          </div>
        }
      />
      <Toast message={message} tone="success" onClose={() => setMessage("")} />

      {loading && <p className="app-text-muted mt-4 text-sm">加载中…</p>}

      {!loading && kb && (
        <>
          <section className="app-card mt-6 p-4">
            <h2 className="app-section-title">语义检索（向量）</h2>
            <p className="app-text-muted mt-1 text-xs">
              与常见 RAG 知识库一致：用自然语言提问，按向量相似度返回最相关条目。未配置 OPENAI_API_KEY 时使用确定性本地向量，仅适合联调。
            </p>
            <div className="app-toolbar mt-3 flex-wrap">
              <input
                className="app-input app-toolbar-input min-w-[200px] flex-1"
                placeholder="例如：退款口径如何定义？"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runSemanticSearch();
                }}
              />
              <button className={`app-button app-toolbar-action ${searching ? "is-loading" : ""}`} type="button" onClick={runSemanticSearch} disabled={searching}>
                检索
              </button>
            </div>
            {hits.length > 0 && (
              <ul className="mt-4 space-y-2">
                {hits.map((h) => (
                  <li key={`${h.entry_id}-${h.snippet.slice(0, 20)}`} className="rounded-lg border border-app-border bg-app-hover p-3 text-sm">
                    <p className="font-semibold text-app-primary">{h.title}</p>
                    <p className="app-text-secondary mt-1 line-clamp-4 whitespace-pre-wrap break-words">{h.snippet}</p>
                    <button
                      type="button"
                      className="app-link mt-2 text-xs"
                      onClick={() => {
                        const found = entries.find((x) => x.id === h.entry_id);
                        if (found) openEditEntry(found);
                      }}
                    >
                      编辑此条目
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-6 space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="app-section-title mb-0">知识条目</h2>
              <input
                className="app-input max-w-md"
                placeholder="在当前库内过滤标题/正文"
                value={entryKeyword}
                onChange={(e) => setEntryKeyword(e.target.value)}
              />
            </div>
            {!filteredEntries.length && (
              <EmptyState
                title={entries.length ? "没有匹配的条目" : "还没有条目"}
                description="使用 Markdown 编写说明、口径、FAQ 等；每条保存后自动参与语义检索。"
                actionLabel="新增条目"
                onAction={openNewEntry}
              />
            )}
            {filteredEntries.map((e) => (
              <div key={e.id} id={`entry-${e.id}`} className="app-card app-list-item p-4">
                <div className="app-list-item-main min-w-0">
                  <p className="text-base font-semibold text-app-primary">{e.title}</p>
                  <p className="app-text-muted mt-1 text-xs">
                    更新：{e.updated_at ? new Date(e.updated_at).toLocaleString() : "-"}
                  </p>
                  <pre className="app-text-secondary-strong mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words font-sans text-sm">{e.body || "（空正文）"}</pre>
                </div>
                <div className="app-list-item-actions shrink-0">
                  <button className="app-button-secondary" type="button" onClick={() => openEditEntry(e)}>
                    编辑
                  </button>
                  <button className="app-button-danger" type="button" onClick={() => confirmDeleteEntry(e.id)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </section>
        </>
      )}

      {isKbEditOpen && (
        <div
          className="app-modal-backdrop"
          role="presentation"
          onClick={() => setIsKbEditOpen(false)}
        >
          <div className="app-card w-full max-w-lg p-5" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">编辑知识库</h2>
              <button className="app-control-button" type="button" onClick={() => setIsKbEditOpen(false)}>
                关闭
              </button>
            </div>
            <label className="app-form-label">
              <span>名称</span>
              <input className="app-input" value={kbNameDraft} onChange={(ev) => setKbNameDraft(ev.target.value)} />
            </label>
            <label className="app-form-label mt-2">
              <span>描述</span>
              <textarea className="app-input min-h-[88px]" value={kbDescDraft} onChange={(ev) => setKbDescDraft(ev.target.value)} />
            </label>
            <div className="mt-3 flex gap-2">
              <button className="app-button flex-1" type="button" onClick={saveKbMeta} disabled={!kbNameDraft.trim()}>
                保存
              </button>
              <button className="app-button-secondary flex-1" type="button" onClick={() => setIsKbEditOpen(false)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {isEntryModalOpen && (
        <div
          className="app-modal-backdrop"
          role="presentation"
          onClick={() => setIsEntryModalOpen(false)}
        >
          <div
            className="app-card max-h-[90vh] w-full max-w-2xl overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-section-title">{editingEntryId ? "编辑条目" : "新增条目"}</h2>
              <button className="app-control-button" type="button" onClick={() => setIsEntryModalOpen(false)}>
                关闭
              </button>
            </div>
            <label className="app-form-label">
              <span>标题</span>
              <input className="app-input" placeholder="简短标题" value={entryTitle} onChange={(ev) => setEntryTitle(ev.target.value)} />
            </label>
            <label className="app-form-label mt-2">
              <span>正文（支持 Markdown）</span>
              <textarea
                className="app-input min-h-[220px] font-mono text-sm"
                placeholder={"## 说明\n- 要点一\n- 要点二"}
                value={entryBody}
                onChange={(ev) => setEntryBody(ev.target.value)}
              />
            </label>
            <div className="mt-3 flex gap-2">
              <button className={`app-button flex-1 ${entrySaving ? "is-loading" : ""}`} type="button" onClick={saveEntry} disabled={entrySaving || !entryTitle.trim()}>
                {entrySaving ? "保存中…" : "保存"}
              </button>
              <button className="app-button-secondary flex-1" type="button" onClick={() => setIsEntryModalOpen(false)}>
                取消
              </button>
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
