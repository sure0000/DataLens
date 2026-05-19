"use client";

import { useEffect, useState } from "react";
import { api, apiForm, ApiError, formatApiError } from "../../lib/api";
import GitSourceForm, { defaultGitFormData, type GitSourceFormData } from "./GitSourceForm";
import type { ApiSource } from "./types";

type ImportStep = "pick" | "file" | "api" | "git";

interface ImportPickerModalProps {
  open: boolean;
  kbId: number;
  apiSources: ApiSource[];
  onClose: () => void;
  onSuccess: () => void;
  notifyUser: (msg: string, tone?: "success" | "error" | "info", opts?: { persist?: boolean }) => void;
}

export default function ImportPickerModal({
  open,
  kbId,
  apiSources,
  onClose,
  onSuccess,
  notifyUser,
}: ImportPickerModalProps) {
  const [step, setStep] = useState<ImportStep>("pick");
  const [fileKey, setFileKey] = useState(0);
  const [saving, setSaving] = useState(false);

  // Git 表单
  const [gitData, setGitData] = useState<GitSourceFormData>(defaultGitFormData());

  // API 导入
  const [apiImportObjectId, setApiImportObjectId] = useState("");
  const [apiImportingId, setApiImportingId] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      setStep("pick");
      setGitData(defaultGitFormData());
    }
  }, [open]);

  // ── File upload ──
  async function handleFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    if (!arr.length) return;
    const importBatch = crypto.randomUUID();
    let successCount = 0;
    for (const file of arr) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("import_batch", importBatch);
        await apiForm(`/api/knowledge-bases/${kbId}/entries/import-file`, fd);
        successCount++;
      } catch (err: unknown) {
        notifyUser(
          `${file.name} 导入失败：${err instanceof Error ? err.message : "未知错误"}`,
          "error"
        );
      }
    }
    if (successCount > 0) {
      notifyUser(`成功导入 ${successCount} 个文件，流水线处理中…`, "success");
      setFileKey((k) => k + 1);
      onClose();
      onSuccess();
    }
  }

  // ── Git save ──
  async function handleGitSave() {
    if (!gitData.name.trim() || !gitData.owner.trim() || !gitData.repo.trim()) {
      notifyUser("请填写显示名称、owner 与仓库名");
      return;
    }
    if (!gitData.token.trim()) {
      notifyUser("新建代码源时必须填写访问令牌");
      return;
    }
    setSaving(true);
    try {
      await api(`/api/knowledge-bases/${kbId}/git-sources`, {
        method: "POST",
        body: JSON.stringify({
          name: gitData.name.trim(),
          provider: gitData.provider,
          api_base: gitData.apiBase.trim() || null,
          owner: gitData.owner.trim(),
          repo: gitData.repo.trim(),
          branch: gitData.branch.trim(),
          path_prefix: gitData.pathPrefix.trim(),
          token: gitData.token.trim(),
          include_globs: gitData.includeGlobs.trim(),
          max_file_kb: gitData.maxFileKb,
          max_files: gitData.maxFiles,
          cron_expression: gitData.cron.trim() || null,
          enabled: gitData.enabled,
        }),
      });
      notifyUser("代码源已添加，可点击「立即同步」拉取文件");
      onClose();
      onSuccess();
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "保存失败",
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  // ── API import ──
  async function handleApiImport(sourceId: number, objectId: string) {
    if (!objectId.trim()) return;
    setApiImportingId(sourceId);
    notifyUser("正在从 API 源导入内容…", "info");
    try {
      const res = await api<{ ok?: boolean; entries_created?: number; message?: string }>(
        `/api/knowledge-bases/${kbId}/api-sources/${sourceId}/import`,
        {
          method: "POST",
          body: JSON.stringify({ object_id: objectId.trim() }),
        }
      );
      notifyUser(`已导入 ${res.entries_created ?? 0} 个条目`, "success", { persist: true });
      onSuccess();
    } catch (e: unknown) {
      let detail = e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "导入失败";
      detail = (detail || "").trim() || "导入失败";
      notifyUser(detail, "error", { persist: true });
    } finally {
      setApiImportingId(null);
    }
  }

  if (!open) return null;

  return (
    <div className="app-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="app-card w-full max-w-2xl max-h-[90vh] overflow-auto p-6"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <div>
            {step !== "pick" && (
              <button
                type="button"
                className="app-control-button mb-1 text-xs text-app-muted"
                onClick={() => setStep("pick")}
              >
                ← 返回
              </button>
            )}
            <h2 className="app-section-title">
              {step === "pick" && "选择导入方式"}
              {step === "file" && "文档导入"}
              {step === "api" && "官方 API 导入"}
              {step === "git" && "代码库同步"}
            </h2>
          </div>
          <button className="app-control-button" onClick={onClose}>
            关闭
          </button>
        </div>

        {/* Step 1: Pick */}
        {step === "pick" && (
          <div className="grid grid-cols-3 gap-4">
            {([
              {
                key: "file" as ImportStep,
                icon: (
                  <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                  </svg>
                ),
                title: "文档导入",
                desc: "上传 md / pdf / docx / xlsx / csv / txt",
              },
              {
                key: "api" as ImportStep,
                icon: (
                  <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="2" y1="12" x2="22" y2="12" />
                    <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
                  </svg>
                ),
                title: "官方 API",
                desc: "Notion / Confluence / 飞书",
              },
              {
                key: "git" as ImportStep,
                icon: (
                  <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="18" cy="18" r="3" />
                    <circle cx="6" cy="6" r="3" />
                    <path d="M13 6h3a2 2 0 012 2v7" />
                    <line x1="6" y1="9" x2="6" y2="21" />
                  </svg>
                ),
                title: "代码库",
                desc: "GitHub / GitLab 仓库同步",
              },
            ] as { key: ImportStep; icon: React.ReactNode; title: string; desc: string }[]).map((item) => (
              <button
                key={item.key}
                type="button"
                className="app-card app-card-interactive flex flex-col items-center gap-3 p-5 text-center"
                onClick={() => setStep(item.key)}
              >
                <span className="text-indigo-500">{item.icon}</span>
                <span className="font-semibold text-sm text-app-primary">{item.title}</span>
                <span className="text-xs text-app-muted leading-relaxed">{item.desc}</span>
              </button>
            ))}
          </div>
        )}

        {/* Step 2a: File */}
        {step === "file" && (
          <div className="space-y-4">
            <p className="app-text-muted text-sm">支持 .md .txt .html .docx .pdf .xlsx .csv，单文件最大 12MB。</p>
            <label className="flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-app-border bg-app-hover p-8 cursor-pointer hover:border-indigo-400 transition-colors">
              <svg className="h-10 w-10 text-app-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 16 12 12 8 16" />
                <line x1="12" y1="12" x2="12" y2="21" />
                <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3" />
              </svg>
              <span className="text-sm text-app-secondary">点击选择文件或拖拽到此处</span>
              <input
                key={fileKey}
                type="file"
                className="sr-only"
                accept=".md,.txt,.html,.htm,.docx,.pdf,.xlsx,.csv"
                multiple
                onChange={(e) => handleFiles(e.target.files ?? [])}
              />
            </label>
          </div>
        )}

        {/* Step 2b: API */}
        {step === "api" && (
          <div className="space-y-4">
            {apiSources.length === 0 && (
              <p className="app-text-muted text-sm">暂无已配置的 API 源，请前往「设置 → API 源」添加。</p>
            )}
            {apiSources.map((s) => (
              <div key={s.id} className="app-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-sm text-app-primary">{s.name}</p>
                    <p className="text-xs text-app-muted">{s.integration}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    className="app-input flex-1 h-8 text-xs font-mono"
                    placeholder={
                      s.integration === "notion"
                        ? "Notion Page / Database ID"
                        : s.integration === "confluence"
                        ? "Confluence Page ID"
                        : "飞书 Doc Token"
                    }
                    value={apiImportObjectId}
                    onChange={(e) => setApiImportObjectId(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleApiImport(s.id, apiImportObjectId);
                    }}
                  />
                  <button
                    className={`app-button text-xs h-8 ${apiImportingId === s.id ? "is-loading" : ""}`}
                    type="button"
                    disabled={!apiImportObjectId.trim() || apiImportingId === s.id}
                    onClick={() => handleApiImport(s.id, apiImportObjectId)}
                  >
                    {apiImportingId === s.id ? "导入中…" : "导入"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Step 2c: Git */}
        {step === "git" && (
          <div className="space-y-4">
            <GitSourceForm data={gitData} onChange={(patch) => setGitData((prev) => ({ ...prev, ...patch }))} disabled={saving} />
            <label className="flex cursor-pointer items-center gap-2 text-sm text-app-secondary">
              <input
                type="checkbox"
                checked={gitData.enabled}
                onChange={(e) => setGitData((prev) => ({ ...prev, enabled: e.target.checked }))}
                disabled={saving}
              />
              启用
            </label>
            <div className="flex gap-2 pt-1">
              <button
                className={`app-button flex-1 ${saving ? "is-loading" : ""}`}
                type="button"
                disabled={saving || !gitData.name.trim() || !gitData.owner.trim() || !gitData.repo.trim() || !gitData.token.trim()}
                onClick={handleGitSave}
              >
                {saving ? "保存中…" : "保存"}
              </button>
              <button className="app-button-secondary flex-1" type="button" onClick={() => setStep("pick")}>
                返回
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
