"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import EmptyState from "../components/EmptyState";
import LoadingSkeletonList from "../components/LoadingSkeletonList";
import PageHeader from "../components/PageHeader";
import Toast from "../components/Toast";
import { api, ApiError, formatApiError } from "../lib/api";
import ListPagination from "../components/ListPagination";

type Domain = { id: number; name: string; description: string; created_at: string };

export default function Home() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [message, setMessage] = useState("");
  const [toastTone, setToastTone] = useState<"success" | "error">("success");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  async function loadDomains() {
    setLoading(true);
    try {
      const res = await api<{ domains: Domain[] }>("/api/business-domains");
      setDomains(res.domains);
    } catch (e: unknown) {
      setToastTone("error");
      setMessage(
        e instanceof ApiError
          ? formatApiError(e)
          : e instanceof Error
            ? e.message
            : "加载业务域失败：请确认后端已启动（默认 http://localhost:8000）且 NEXT_PUBLIC_API_URL 配置正确。"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDomains();
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

  async function createDomain() {
    if (!newName.trim()) {
      setToastTone("error");
      setMessage("请先填写业务域名称");
      return;
    }
    setSaving(true);
    try {
      await api<{ id: number }>("/api/business-domains", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() })
      });
      setIsCreateOpen(false);
      setNewName("");
      setNewDesc("");
      setToastTone("success");
      setMessage("业务域创建成功");
      loadDomains();
    } catch (e: unknown) {
      setToastTone("error");
      setMessage(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "创建失败");
    } finally {
      setSaving(false);
    }
  }

  const filteredDomains = domains
    .filter((d) => {
      const q = keyword.trim().toLowerCase();
      if (!q) return true;
      return d.name.toLowerCase().includes(q) || (d.description || "").toLowerCase().includes(q);
    })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
  const start = (page - 1) * pageSize;
  const pagedDomains = filteredDomains.slice(start, start + pageSize);

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[{ label: "首页" }, { label: "业务域" }]}
        title="业务域"
        subtitle="在这里维护业务域定义，并关联数据表范围与业务描述。"
        actionsBelowSubtitle
        actions={
          <div className="app-toolbar !flex-nowrap w-full min-w-0 md:w-auto">
            <input
              className="app-input app-toolbar-input min-w-0 w-full max-w-[13.5rem] sm:max-w-[15rem]"
              placeholder="搜索业务域名称/描述"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button type="button" className="app-button app-toolbar-action shrink-0" onClick={() => setIsCreateOpen(true)}>
              新增业务域
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
        <h2 className="app-section-title">已创建业务域</h2>
        {loading && <LoadingSkeletonList count={3} />}
        {pagedDomains.map((d) => (
          <div key={d.id} className="app-card app-card-interactive app-list-item p-4">
            <div className="app-list-item-main">
              <Link className="app-link break-all text-base font-semibold" href={`/business-domains/${d.id}`}>
                {d.name}
              </Link>
              <p className="app-text-muted mt-1 text-xs">创建时间：{d.created_at ? new Date(d.created_at).toLocaleString() : "-"}</p>
              <p className="app-text-secondary-strong text-sm">{d.description || "暂无描述"}</p>
            </div>
          </div>
        ))}
        {!filteredDomains.length && (
          <EmptyState
            title="还没有业务域"
            description="建议先创建 1-2 个核心业务域（如订单、用户），再逐步补充描述和关联数据表。"
            actionLabel="新增业务域"
            onAction={() => setIsCreateOpen(true)}
          />
        )}
        {!!filteredDomains.length && (
          <ListPagination
            page={page}
            pageSize={pageSize}
            total={filteredDomains.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </section>

      {isCreateOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setIsCreateOpen(false)}>
          <div
            className="app-card w-full max-w-xl max-h-[85vh] overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-domain-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 id="create-domain-title" className="app-section-title">
                新增业务域
              </h2>
              <button className="app-control-button" onClick={() => setIsCreateOpen(false)}>
                关闭
              </button>
            </div>
            <div className="grid gap-3">
              <label className="app-form-label">
                <span>业务域名称（必填）</span>
                <input className="app-input" placeholder="例如：订单履约域" value={newName} onChange={(e) => setNewName(e.target.value)} />
              </label>
              <label className="app-form-label">
                <span>业务描述（选填）</span>
                <textarea
                  className="app-input min-h-[120px]"
                  placeholder="说明该业务域的边界、核心指标、使用场景"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                />
              </label>
              <div className="flex gap-2">
                <button className={`app-button flex-1 ${saving ? "is-loading" : ""}`} onClick={createDomain} disabled={saving || !newName.trim()}>
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
