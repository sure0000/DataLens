"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PageHeader from "../../components/PageHeader";
import Toast from "../../components/Toast";
import { api, ApiError, formatApiError } from "../../lib/api";

type KnowledgeBase = { id: number; name: string; description: string; created_at: string };

export default function KnowledgeBasesPage() {
  const [list, setList] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [toastTone, setToastTone] = useState<"success" | "error">("success");

  // 新建 Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await api<{ knowledge_bases: KnowledgeBase[] }>("/api/knowledge-bases");
      setList(res.knowledge_bases);
    } catch (e: unknown) {
      setToastTone("error");
      setMessage(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!isCreateOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") setIsCreateOpen(false); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isCreateOpen]);

  async function createKb() {
    if (!newName.trim()) { setToastTone("error"); setMessage("请填写知识库名称"); return; }
    setSaving(true);
    try {
      await api("/api/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() }),
      });
      setIsCreateOpen(false);
      setNewName(""); setNewDesc("");
      setToastTone("success"); setMessage("知识库创建成功");
      load();
    } catch (e: unknown) {
      setToastTone("error");
      setMessage(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "创建失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", href: "/" }, { label: "语义知识库" }]}
        title="语义知识库"
        subtitle="文档经过清洗、分块、向量化后进入语义索引，支持混合检索（向量 + 关键词），供 Copilot 和 RAG 引用。"
        actions={
          <div className="app-toolbar">
            <button type="button" className="app-button app-toolbar-action" onClick={() => setIsCreateOpen(true)}>
              新建知识库
            </button>
          </div>
        }
      />

      <Toast
        message={message}
        tone={toastTone}
        duration={toastTone === "error" ? 8000 : 4000}
        onClose={() => { setMessage(""); setToastTone("success"); }}
      />

      {loading && <p className="app-text-muted mt-6 text-sm">加载中…</p>}

      {!loading && list.length === 0 && (
        <div className="mt-10 text-center">
          <p className="app-text-muted text-sm">还没有知识库，点击「新建知识库」开始。</p>
        </div>
      )}

      {!loading && list.length > 0 && (
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {list.map((kb) => (
            <Link
              key={kb.id}
              href={`/knowledge-bases/${kb.id}`}
              className="app-card app-card-interactive flex flex-col items-start gap-2 p-4 aspect-square no-underline group"
            >
              <span className="text-indigo-500 group-hover:text-indigo-600 transition-colors">
                <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 4h5a2 2 0 012 2v14a2 2 0 00-2-2H6V4zM13 4h5v14h-5a2 2 0 00-2 2V6a2 2 0 012-2z" />
                </svg>
              </span>
              <p className="app-text-primary font-semibold text-sm leading-snug line-clamp-2 break-all">{kb.name}</p>
              {kb.description && (
                <p className="app-text-muted text-xs line-clamp-2 leading-relaxed">{kb.description}</p>
              )}
              <p className="mt-auto app-text-muted text-[11px]">{new Date(kb.created_at).toLocaleDateString()}</p>
            </Link>
          ))}
        </div>
      )}

      {/* 新建知识库 Modal */}
      {isCreateOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setIsCreateOpen(false)}>
          <div
            className="app-card w-full max-w-lg max-h-[85vh] overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-kb-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 id="create-kb-title" className="app-section-title">新建知识库</h2>
              <button className="app-control-button" onClick={() => setIsCreateOpen(false)}>关闭</button>
            </div>
            <div className="grid gap-3">
              <label className="app-form-label">
                <span>名称（必填）</span>
                <input className="app-input" placeholder="例如：指标口径说明" value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") createKb(); }} />
              </label>
              <label className="app-form-label">
                <span>描述（选填）</span>
                <textarea className="app-input min-h-[80px]" placeholder="说明收录范围、读者对象" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
              </label>
              <div className="flex gap-2 pt-1">
                <button className={`app-button flex-1 ${saving ? "is-loading" : ""}`} onClick={createKb} disabled={saving || !newName.trim()}>
                  {saving ? "保存中…" : "保存"}
                </button>
                <button className="app-button-secondary flex-1" onClick={() => setIsCreateOpen(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
