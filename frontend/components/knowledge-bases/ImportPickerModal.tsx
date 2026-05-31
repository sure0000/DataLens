"use client";

import { useEffect, useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { api, apiForm, ApiError, formatApiError } from "../../lib/api";
import GitSourceForm, { defaultGitFormData, type GitSourceFormData } from "./GitSourceForm";
import { gitSourceValidationError } from "../../lib/parseGitRepoUrl";
import type { ApiSource } from "./types";
import {
  assetKindLabelsForConnector,
  CONNECTOR_LABELS,
  defaultAssetKindsForConnector,
  type ConnectorKind,
} from "./ingestionTypes";

type WizardStep = "connector" | "configure";

interface ImportPickerModalProps {
  open: boolean;
  kbId: number;
  apiSources: ApiSource[];
  onClose: () => void;
  onSuccess: (opts?: { databaseImportId?: number }) => void;
  notifyUser: (msg: string, tone?: "success" | "error" | "info", opts?: { persist?: boolean }) => void;
}

const WIZARD_STEPS: { id: WizardStep; label: string }[] = [
  { id: "connector", label: "连接器" },
  { id: "configure", label: "配置" },
];

export default function ImportPickerModal({
  open,
  kbId,
  apiSources,
  onClose,
  onSuccess,
  notifyUser,
}: ImportPickerModalProps) {
  const [wizardStep, setWizardStep] = useState<WizardStep>("connector");
  const [connector, setConnector] = useState<ConnectorKind | null>(null);

  const [fileKey, setFileKey] = useState(0);
  const [saving, setSaving] = useState(false);

  const [gitData, setGitData] = useState<GitSourceFormData>(defaultGitFormData());
  const [apiImportObjectId, setApiImportObjectId] = useState("");
  const [apiImportingId, setApiImportingId] = useState<number | null>(null);

  const [dbDatasources, setDbDatasources] = useState<{ id: number; name: string; source_type: string }[]>([]);
  const [dbSelectedDsId, setDbSelectedDsId] = useState<number | null>(null);
  const [dbDatabases, setDbDatabases] = useState<{ name: string; description: string }[]>([]);
  const [dbSelectedNames, setDbSelectedNames] = useState<Set<string>>(new Set());
  const [dbLoadingDs, setDbLoadingDs] = useState(false);
  const [dbImporting, setDbImporting] = useState(false);

  const [manualTitle, setManualTitle] = useState("");
  const [manualBody, setManualBody] = useState("");
  const [ttlContent, setTtlContent] = useState("");

  useEscapeKey(onClose, open);

  useEffect(() => {
    if (open) {
      setWizardStep("connector");
      setConnector(null);
      setGitData(defaultGitFormData());
      setDbDatasources([]);
      setDbSelectedDsId(null);
      setDbDatabases([]);
      setDbSelectedNames(new Set());
      setManualTitle("");
      setManualBody("");
      setTtlContent("");
    }
  }, [open]);

  const stepIndex = WIZARD_STEPS.findIndex((s) => s.id === wizardStep);

  function goBack() {
    if (wizardStep === "configure") {
      setWizardStep("connector");
    } else {
      onClose();
    }
  }

  function selectConnector(c: ConnectorKind) {
    setConnector(c);
    if (c === "database") {
      void loadDatasourcesForDbImport();
    }
    if (c === "git" && defaultAssetKindsForConnector(c).includes("relation_lineage")) {
      setGitData((prev) => ({
        ...prev,
        includeGlobs: "*.sql,*.py,*.yml,*.yaml",
      }));
    }
    setWizardStep("configure");
  }

  async function handleFiles(files: FileList | File[], isTtl = false) {
    const arr = Array.from(files);
    if (!arr.length) return;

    if (isTtl) {
      const file = arr[0];
      try {
        const text = await file.text();
        await api(`/api/ontology/knowledge-bases/${kbId}/import`, {
          method: "POST",
          body: JSON.stringify({ ttl: text, kb_id: kbId, replace: false }),
        });
        notifyUser("TTL 本体已导入", "success");
        onClose();
        onSuccess();
      } catch (err: unknown) {
        notifyUser(err instanceof Error ? err.message : "TTL 导入失败", "error");
      }
      return;
    }

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
          "error",
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

  async function handleGitSave() {
    const validationError = gitSourceValidationError(gitData, { requireToken: true });
    if (validationError) {
      notifyUser(validationError);
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
          enable_document_indexing: gitData.enableDocumentIndexing,
          extraction_config: {
            extraction_profile: gitData.extractionProfile,
            enable_regex_extractors: true,
            enable_llm_fallback: true,
            min_body_chars: 50,
          },
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
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  async function loadDatasourcesForDbImport() {
    setDbLoadingDs(true);
    try {
      const res = await api<{ datasources: { id: number; name: string; source_type: string }[] }>(
        "/api/datasources",
      );
      setDbDatasources(res.datasources ?? []);
    } catch {
      setDbDatasources([]);
    } finally {
      setDbLoadingDs(false);
    }
  }

  async function selectDbDatasource(dsId: number) {
    setDbSelectedDsId(dsId);
    try {
      const res = await api<{ databases: { name: string; description: string }[] }>(
        `/api/datasources/${dsId}/catalog`,
      );
      setDbDatabases(res.databases ?? []);
      setDbSelectedNames(new Set());
    } catch {
      setDbDatabases([]);
      notifyUser("加载数据库列表失败", "error");
    }
  }

  async function handleDatabaseImport() {
    if (!dbSelectedDsId || dbSelectedNames.size === 0) return;
    setDbImporting(true);
    try {
      const res = await api<{ id: number }>(`/api/knowledge-bases/${kbId}/database-imports`, {
        method: "POST",
        body: JSON.stringify({
          datasource_id: dbSelectedDsId,
          database_names: Array.from(dbSelectedNames),
        }),
      });
      notifyUser("数据库已登记为证据包，正在自动触发语义清洗…", "info");
      onClose();
      onSuccess({ databaseImportId: res.id });
    } catch (e: unknown) {
      notifyUser(
        e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "导入失败",
        "error",
      );
    } finally {
      setDbImporting(false);
    }
  }

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
        },
      );
      notifyUser(`已导入 ${res.entries_created ?? 0} 个条目`, "success", { persist: true });
      onSuccess();
      onClose();
    } catch (e: unknown) {
      let detail = e instanceof ApiError ? formatApiError(e) : e instanceof Error ? e.message : "导入失败";
      notifyUser((detail || "").trim() || "导入失败", "error", { persist: true });
    } finally {
      setApiImportingId(null);
    }
  }

  async function handleManualSave() {
    if (!manualTitle.trim()) {
      notifyUser("请填写条目标题");
      return;
    }
    setSaving(true);
    try {
      await api(`/api/knowledge-bases/${kbId}/entries`, {
        method: "POST",
        body: JSON.stringify({ title: manualTitle.trim(), body: manualBody.trim() }),
      });
      notifyUser("手动条目已登记");
      onClose();
      onSuccess();
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleTtlPasteImport() {
    if (!ttlContent.trim()) {
      notifyUser("请粘贴或上传 TTL 内容");
      return;
    }
    setSaving(true);
    try {
      await api(`/api/ontology/knowledge-bases/${kbId}/import`, {
        method: "POST",
        body: JSON.stringify({ ttl: ttlContent.trim(), kb_id: kbId, replace: false }),
      });
      notifyUser("TTL 本体已导入");
      onClose();
      onSuccess();
    } catch (e: unknown) {
      notifyUser(e instanceof Error ? e.message : "导入失败", "error");
    } finally {
      setSaving(false);
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
        <div className="mb-5 flex items-center justify-between">
          <div>
            {wizardStep !== "connector" && (
              <button
                type="button"
                className="app-control-button mb-1 text-xs text-app-muted"
                onClick={goBack}
              >
                ← 返回
              </button>
            )}
            <h2 className="app-section-title">导入数据</h2>
            <p className="text-xs text-app-muted mt-0.5">
              选择连接器并配置；导入完成后由系统自动登记证据包。数据源导入将自动语义清洗，其他源请在导入源卡片上触发语义清洗
            </p>
          </div>
          <button className="app-control-button" onClick={onClose}>
            关闭
          </button>
        </div>

        {/* Step indicator */}
        <div className="mb-6 flex items-center gap-2 text-xs">
          {WIZARD_STEPS.map((s, i) => (
            <div key={s.id} className="flex items-center gap-2">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full border ${
                  i <= stepIndex
                    ? "border-indigo-500 bg-indigo-500 text-white"
                    : "border-app-border text-app-muted"
                }`}
              >
                {i + 1}
              </span>
              <span className={i <= stepIndex ? "text-app-primary font-medium" : "text-app-muted"}>
                {s.label}
              </span>
              {i < WIZARD_STEPS.length - 1 && <span className="text-app-muted">—</span>}
            </div>
          ))}
        </div>

        {/* Step 1: Connector */}
        {wizardStep === "connector" && (
          <div>
            <p className="text-sm text-app-secondary mb-4">选择接入连接器：</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {(Object.keys(CONNECTOR_LABELS) as ConnectorKind[]).map((c) => (
                <button
                  key={c}
                  type="button"
                  className="app-card app-card-interactive p-4 text-left"
                  onClick={() => selectConnector(c)}
                >
                  <span className="font-semibold text-sm text-app-primary">{CONNECTOR_LABELS[c]}</span>
                  <span className="mt-1 block text-xs text-app-muted">
                    {assetKindLabelsForConnector(c).join("、")}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Configure */}
        {wizardStep === "configure" && connector && (
          <div className="space-y-4">
            <p className="text-sm text-app-muted">{CONNECTOR_LABELS[connector]}</p>

            {connector === "file" && (
              <>
                <p className="text-xs text-app-muted">
                  支持 .md .txt .html .docx .pdf .xlsx .csv，单文件最大 12MB。
                </p>
                <label className="flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-app-border bg-app-hover p-8 cursor-pointer hover:border-indigo-400 transition-colors">
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
              </>
            )}

            {connector === "api" && (
              <div className="space-y-4">
                {apiSources.length === 0 && (
                  <p className="text-sm text-app-muted">暂无 API 源，请前往「设置 → API 源」添加。</p>
                )}
                {apiSources.map((s) => (
                  <div key={s.id} className="app-card p-4 space-y-3">
                    <p className="font-medium text-sm">{s.name}</p>
                    <p className="text-xs text-app-muted">{s.integration}</p>
                    <div className="flex gap-2">
                      <input
                        className="app-input flex-1 h-8 text-xs font-mono"
                        placeholder="Page / Database / Doc ID"
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

            {connector === "git" && (
              <div className="space-y-4">
                {defaultAssetKindsForConnector("git").includes("relation_lineage") && (
                  <p className="text-xs text-amber-700 bg-amber-500/10 rounded-lg px-3 py-2">
                    建议 include 模式包含 *.sql；同步后在源卡片触发「语义清洗」以抽取血缘与 JOIN。
                  </p>
                )}
                <GitSourceForm
                  data={gitData}
                  onChange={(patch) => setGitData((prev) => ({ ...prev, ...patch }))}
                  disabled={saving}
                />
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={gitData.enabled}
                    onChange={(e) => setGitData((prev) => ({ ...prev, enabled: e.target.checked }))}
                    disabled={saving}
                  />
                  启用
                </label>
                <button
                  className={`app-button w-full ${saving ? "is-loading" : ""}`}
                  type="button"
                  disabled={
                    saving || gitSourceValidationError(gitData, { requireToken: true }) !== null
                  }
                  onClick={handleGitSave}
                >
                  {saving ? "保存中…" : "保存代码源"}
                </button>
              </div>
            )}

            {connector === "database" && (
              <div className="space-y-4">
                {!dbSelectedDsId ? (
                  <>
                    <p className="text-sm text-app-muted">选择数据源并勾选数据库（引用已有 TableMeta，不重复采集）。</p>
                    {dbLoadingDs && <p className="text-sm text-app-muted">加载中…</p>}
                    <div className="grid gap-2 max-h-64 overflow-auto">
                      {dbDatasources.map((ds) => (
                        <button
                          key={ds.id}
                          type="button"
                          className="app-card app-card-interactive p-3 text-left"
                          onClick={() => selectDbDatasource(ds.id)}
                        >
                          <p className="font-medium text-sm">{ds.name}</p>
                          <p className="text-xs text-app-muted">{ds.source_type}</p>
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="app-control-button text-xs text-app-muted"
                      onClick={() => {
                        setDbSelectedDsId(null);
                        setDbDatabases([]);
                        setDbSelectedNames(new Set());
                      }}
                    >
                      ← 重新选择数据源
                    </button>
                    <div className="grid gap-2 max-h-64 overflow-auto">
                      {dbDatabases.map((db) => {
                        const checked = dbSelectedNames.has(db.name);
                        return (
                          <label
                            key={db.name}
                            className={`app-card flex items-center gap-3 p-3 cursor-pointer ${checked ? "ring-2 ring-cyan-400" : ""}`}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => {
                                const next = new Set(dbSelectedNames);
                                if (checked) next.delete(db.name);
                                else next.add(db.name);
                                setDbSelectedNames(next);
                              }}
                            />
                            <span className="text-sm font-medium">{db.name}</span>
                          </label>
                        );
                      })}
                    </div>
                    <button
                      className={`app-button w-full ${dbImporting ? "is-loading" : ""}`}
                      type="button"
                      disabled={dbImporting || dbSelectedNames.size === 0}
                      onClick={handleDatabaseImport}
                    >
                      {dbImporting ? "导入中…" : `登记 ${dbSelectedNames.size} 个数据库`}
                    </button>
                  </>
                )}
              </div>
            )}

            {connector === "manual" && (
              <div className="space-y-3">
                {defaultAssetKindsForConnector("manual").includes("governance") && (
                  <p className="text-xs text-app-muted">
                    业务域与组织绑定请在「业务域」页面配置；此处可添加治理说明条目。
                  </p>
                )}
                <input
                  className="app-input w-full"
                  placeholder="条目标题"
                  value={manualTitle}
                  onChange={(e) => setManualTitle(e.target.value)}
                />
                <textarea
                  className="app-input w-full min-h-[120px]"
                  placeholder="正文内容（制度说明、域划分备注等）"
                  value={manualBody}
                  onChange={(e) => setManualBody(e.target.value)}
                />
                <button
                  className={`app-button w-full ${saving ? "is-loading" : ""}`}
                  type="button"
                  disabled={saving || !manualTitle.trim()}
                  onClick={handleManualSave}
                >
                  保存条目
                </button>
              </div>
            )}

            {connector === "ttl" && (
              <div className="space-y-3">
                <textarea
                  className="app-input w-full min-h-[160px] font-mono text-xs"
                  placeholder="@prefix dl: &lt;https://datalens.local/ontology/&gt; …"
                  value={ttlContent}
                  onChange={(e) => setTtlContent(e.target.value)}
                />
                <label className="app-button-secondary inline-block cursor-pointer">
                  或上传 .ttl 文件
                  <input
                    type="file"
                    className="sr-only"
                    accept=".ttl,.trig"
                    onChange={async (e) => {
                      const f = e.target.files?.[0];
                      if (f) setTtlContent(await f.text());
                    }}
                  />
                </label>
                <button
                  className={`app-button w-full ${saving ? "is-loading" : ""}`}
                  type="button"
                  disabled={saving || !ttlContent.trim()}
                  onClick={handleTtlPasteImport}
                >
                  导入到 RDF 生产图
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
