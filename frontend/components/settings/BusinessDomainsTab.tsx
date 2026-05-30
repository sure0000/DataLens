"use client";

import { useEffect, useState } from "react";
import ConfirmDialog from "../ConfirmDialog";
import EmptyState from "../EmptyState";
import LoadingSkeletonList from "../LoadingSkeletonList";
import ListPagination from "../ListPagination";
import Toast from "../Toast";
import { useToast } from "../../hooks/useToast";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { api, ApiError, formatApiError } from "../../lib/api";
import { emitBusinessDomainUpdated } from "../../lib/businessDomain";

type Domain = { id: number; name: string; description: string; created_at: string; is_builtin?: boolean };

export default function BusinessDomainsTab() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const { toast, notify, dismiss } = useToast();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [editingDomain, setEditingDomain] = useState<Domain | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [confirmDeleteDomain, setConfirmDeleteDomain] = useState<Domain | null>(null);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  async function loadDomains() {
    setLoading(true);
    try {
      const res = await api<{ domains: Domain[] }>("/api/business-domains");
      setDomains(res.domains);
    } catch (e: unknown) {
      notify(
        e instanceof ApiError
          ? formatApiError(e)
          : e instanceof Error
            ? e.message
            : "加载业务域失败：请确认后端已启动（默认 http://127.0.0.1:8000）且 NEXT_PUBLIC_API_URL 配置正确。",
        "error"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDomains();
  }, []);

  useEffect(() => {
    setPage(1);
  }, [keyword, pageSize]);

  useEscapeKey(() => setIsCreateOpen(false), isCreateOpen);
  useEscapeKey(() => setEditingDomain(null), !!editingDomain);

  async function createDomain() {
    if (!newName.trim()) {
      notify("请先填写业务域名称", "error");
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
      notify("业务域创建成功");
      await loadDomains();
      emitBusinessDomainUpdated();
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "创建失败", "error");
    } finally {
      setSaving(false);
    }
  }

  function openEditModal(domain: Domain) {
    setEditingDomain(domain);
    setEditName(domain.name);
    setEditDesc(domain.description || "");
  }

  async function updateDomain() {
    if (!editingDomain) return;
    if (!editName.trim()) {
      notify("请先填写业务域名称", "error");
      return;
    }
    setSaving(true);
    try {
      await api(`/api/business-domains/${editingDomain.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: editName.trim(), description: editDesc.trim() })
      });
      setEditingDomain(null);
      notify("业务域更新成功");
      await loadDomains();
      emitBusinessDomainUpdated();
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "更新失败", "error");
    } finally {
      setSaving(false);
    }
  }

  async function deleteDomain(domain: Domain) {
    setSaving(true);
    try {
      await api(`/api/business-domains/${domain.id}`, { method: "DELETE" });
      setConfirmDeleteDomain(null);
      notify("业务域删除成功");
      await loadDomains();
      emitBusinessDomainUpdated();
    } catch (e: unknown) {
      notify(e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "删除失败", "error");
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
    <>
      <section className="space-y-5">
        <div className="rounded-2xl border border-app-border bg-app-surface p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-app-ink">业务域管理</h2>
              <p className="mt-1.5 text-sm text-app-muted">业务域的新增、编辑、删除都在这里统一维护。</p>
            </div>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
              <input
                className="app-input min-w-0 flex-1 sm:w-72"
                placeholder="搜索名称或描述"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
              <button type="button" className="app-button shrink-0 whitespace-nowrap" onClick={() => setIsCreateOpen(true)}>
                新增业务域
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {loading && <LoadingSkeletonList count={3} />}
          {pagedDomains.map((d) => (
            <div key={d.id} className="app-card app-card-interactive app-list-item p-5 sm:p-6">
              <div className="app-list-item-main">
                <p className="break-all text-lg font-semibold text-app-ink">{d.name}</p>
                <p className="app-text-muted mt-2 text-sm">创建时间：{d.created_at ? new Date(d.created_at).toLocaleString() : "-"}</p>
                <p className="app-text-secondary-strong mt-2 text-[0.95rem] leading-relaxed">{d.description || "暂无描述"}</p>
              </div>
              <div className="app-list-item-actions self-start sm:self-center">
                <button
                  type="button"
                  className="app-button-secondary whitespace-nowrap"
                  disabled={!!d.is_builtin}
                  onClick={() => openEditModal(d)}
                >
                  编辑
                </button>
                <button
                  type="button"
                  className="app-button-danger whitespace-nowrap"
                  disabled={!!d.is_builtin}
                  onClick={() => setConfirmDeleteDomain(d)}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
          {!filteredDomains.length && (
            <EmptyState
              title="还没有业务域"
              description="建议先创建 1-2 个核心业务域（如订单、用户），再逐步补充描述与数据范围。"
              actionLabel="新增业务域"
              onAction={() => setIsCreateOpen(true)}
            />
          )}
          {!!filteredDomains.length && (
            <div className="rounded-2xl border border-app-border bg-app-surface p-3 sm:p-4">
              <ListPagination
                page={page}
                pageSize={pageSize}
                total={filteredDomains.length}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
              />
            </div>
          )}
        </div>
      </section>

      {isCreateOpen && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setIsCreateOpen(false)}>
          <div
            className="app-card max-h-[85vh] w-full max-w-xl overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-domain-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 id="create-domain-title" className="app-section-title">
                新增业务域
              </h3>
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
                <button className={`app-button flex-1 ${saving ? "is-loading" : ""}`} onClick={() => void createDomain()} disabled={saving || !newName.trim()}>
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

      {editingDomain && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => setEditingDomain(null)}>
          <div
            className="app-card max-h-[85vh] w-full max-w-xl overflow-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-domain-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 id="edit-domain-title" className="app-section-title">
                编辑业务域
              </h3>
              <button className="app-control-button" onClick={() => setEditingDomain(null)}>
                关闭
              </button>
            </div>
            <div className="grid gap-3">
              <label className="app-form-label">
                <span>业务域名称（必填）</span>
                <input className="app-input" value={editName} onChange={(e) => setEditName(e.target.value)} />
              </label>
              <label className="app-form-label">
                <span>业务描述（选填）</span>
                <textarea className="app-input min-h-[120px]" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
              </label>
              <div className="flex gap-2">
                <button className={`app-button flex-1 ${saving ? "is-loading" : ""}`} onClick={() => void updateDomain()} disabled={saving || !editName.trim()}>
                  {saving ? "保存中..." : "保存"}
                </button>
                <button className="app-button-secondary flex-1" onClick={() => setEditingDomain(null)}>
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDeleteDomain !== null}
        title="确认删除业务域？"
        description={confirmDeleteDomain ? `将删除「${confirmDeleteDomain.name}」，该操作不可撤销。` : ""}
        confirmText="删除"
        cancelText="取消"
        danger
        loading={saving}
        onCancel={() => setConfirmDeleteDomain(null)}
        onConfirm={() => {
          if (confirmDeleteDomain) {
            void deleteDomain(confirmDeleteDomain);
          }
        }}
      />

      <Toast message={toast.message} tone={toast.tone} duration={toast.durationMs} onClose={dismiss} />
    </>
  );
}
