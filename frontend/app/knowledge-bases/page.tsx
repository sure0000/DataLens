"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import EmptyState from "../../components/EmptyState";
import ListPagination from "../../components/ListPagination";
import LoadingSkeletonList from "../../components/LoadingSkeletonList";
import PageHeader from "../../components/PageHeader";
import Toast from "../../components/Toast";
import { api, ApiError, formatApiError } from "../../lib/api";

type KnowledgeBase = { id: number; name: string; description: string; created_at: string };

export default function KnowledgeBasesPage() {
  const [list, setList] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [toastTone, setToastTone] = useState<"success" | "error">("success");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  async function load() {
    setLoading(true);
    try {
      const res = await api<{ knowledge_bases: KnowledgeBase[] }>("/api/knowledge-bases");
      setList(res.knowledge_bases);
    } catch (e: unknown) {
      setToastTone("error");
      setMessage(
        e instanceof ApiError
          ? formatApiError(e)
          : e instanceof Error
            ? e.message
            : "加载知识库失败：请确认后端已启动且 NEXT_PUBLIC_API_URL 正确。"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [keyword, pageSize]);

  useEffect(() => {
    if (!isCreateOpen) return;
    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") setIsCreateOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isCreateOpen]);

  async function createKb() {
    if (!newName.trim()) {
      setToastTone("error");
      setMessage("请先填写知识库名称");
      return;
    }
    setSaving(true);
    try {
      await api("/api/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() })
      });
      setIsCreateOpen(false);
      setNewName("");
      setNewDesc("");
      setToastTone("success");
      setMessage("知识库创建成功");
      load();
    } catch (e: unknown) {
      setToastTone("error");
      setMessage(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "创建失败");
    } finally {
      setSaving(false);
    }
  }

  const filtered = list
    .filter((k) => {
      const q = keyword.trim().toLowerCase();
      if (!q) return true;
      return k.name.toLowerCase().includes(q) || (k.description || "").toLowerCase().includes(q);
    })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  const start = (page - 1) * pageSize;
  const paged = filtered.slice(start, start + pageSize);

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[{ label: "首页", href: "/" }, { label: "知识库" }]}
        title="知识库"
        subtitle="按主题维护 Markdown 条目，支持向量语义检索，便于协作者编辑与大模型/RAG 引用。"
        actionsBelowSubtitle
        actions={
          <div className="app-toolbar !flex-nowrap w-full min-w-0 md:w-auto">
            <input
              className="app-input app-toolbar-input min-w-0 w-full max-w-[13.5rem] sm:max-w-[15rem]"
              placeholder="搜索知识库名称/描述"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button type="button" className="app-button app-toolbar-action shrink-0" onClick={() => setIsCreateOpen(true)}>
              新增知识库
            </button>
          </div>
        }
      />
      <Toast
        message={message}
        tone={toastTone}
        duration={toastTone === "error" ? 8000 : 4000}
        onClose={() => {
          setMessage("");
          setToastTone("success");
        }}
      />

      <section className="mt-6 space-y-3">
        <h2 className="app-section-title">已创建知识库</h2>
        {loading && <LoadingSkeletonList count={3} />}
        {paged.map((k) => (
          <div key={k.id} className="app-card app-card-interactive app-list-item p-4">
            <div className="app-list-item-main">
              <Link className="app-link break-all text-base font-semibold" href={`/knowledge-bases/${k.id}`}>
                {k.name}
              </Link>
              <p className="app-text-muted mt-1 text-xs">创建时间：{k.created_at ? new Date(k.created_at).toLocaleString() : "-"}</p>
              <p className="app-text-secondary-strong text-sm">{k.description || "暂无描述"}</p>
            </div>
          </div>
        ))}
        {!filtered.length && (
          <EmptyState
            title="还没有知识库"
            description="可创建如「产品术语」「数据口径」「运维手册」等库，在详情页添加条目并试用语义检索。"
            actionLabel="新增知识库"
            onAction={() => setIsCreateOpen(true)}
          />
        )}
        {!!filtered.length && (
          <ListPagination
            page={page}
            pageSize={pageSize}
            total={filtered.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </section>

      {isCreateOpen && (
        <div
          className="app-modal-backdrop"
          role="presentation"
          onClick={() => setIsCreateOpen(false)}
        >
          <div
            className="app-card w-full max-w-xl max-h-[85vh] overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-kb-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 id="create-kb-title" className="app-section-title">
                新增知识库
              </h2>
              <button className="app-control-button" onClick={() => setIsCreateOpen(false)}>
                关闭
              </button>
            </div>
            <div className="grid gap-3">
              <label className="app-form-label">
                <span>名称（必填）</span>
                <input className="app-input" placeholder="例如：指标口径说明" value={newName} onChange={(e) => setNewName(e.target.value)} />
              </label>
              <label className="app-form-label">
                <span>描述（选填）</span>
                <textarea
                  className="app-input min-h-[100px]"
                  placeholder="说明收录范围、读者对象、更新约定"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                />
              </label>
              <div className="flex gap-2">
                <button
                  className={`app-button flex-1 ${saving ? "is-loading" : ""}`}
                  onClick={createKb}
                  disabled={saving || !newName.trim()}
                >
                  {saving ? "保存中..." : "保存"}
                </button>
                <button className="app-button-secondary flex-1" onClick={() => setIsCreateOpen(false)}>
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
