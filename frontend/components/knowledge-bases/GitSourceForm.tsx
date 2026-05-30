"use client";

import { useState } from "react";

interface GitSourceFormData {
  name: string;
  provider: "github" | "gitlab";
  apiBase: string;
  owner: string;
  repo: string;
  branch: string;
  pathPrefix: string;
  token: string;
  includeGlobs: string;
  maxFileKb: number;
  maxFiles: number;
  enableDocumentIndexing: boolean;
  extractionProfile: "mixed" | "data_warehouse";
  cron: string;
  enabled: boolean;
}

interface GitSourceFormProps {
  data: GitSourceFormData;
  onChange: (patch: Partial<GitSourceFormData>) => void;
  disabled?: boolean;
  isEditing?: boolean;
}

export type { GitSourceFormData };

export function defaultGitFormData(): GitSourceFormData {
  return {
    name: "",
    provider: "github",
    apiBase: "",
    owner: "",
    repo: "",
    branch: "",
    pathPrefix: "",
    token: "",
    includeGlobs: "*.sql,*.py,*.yml,*.yaml,*.hql",
    maxFileKb: 512,
    maxFiles: 200,
    enableDocumentIndexing: false,
    extractionProfile: "mixed",
    cron: "",
    enabled: true,
  };
}

export default function GitSourceForm({ data, onChange, disabled, isEditing }: GitSourceFormProps) {
  const [showToken, setShowToken] = useState(false);

  const f = (patch: Partial<GitSourceFormData>) => onChange(patch);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <label className="app-form-label sm:col-span-2">
        <span>显示名称</span>
        <input
          className="app-input"
          value={data.name}
          onChange={(e) => f({ name: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>平台</span>
        <select
          className="app-input"
          value={data.provider}
          onChange={(e) => f({ provider: e.target.value as "github" | "gitlab" })}
          disabled={disabled}
        >
          <option value="github">GitHub</option>
          <option value="gitlab">GitLab（含自建，填 API Base）</option>
        </select>
      </label>

      <label className="app-form-label">
        <span>API Base（可选）</span>
        <input
          className="app-input font-mono text-xs"
          placeholder={data.provider === "gitlab" ? "https://gitlab.com/api/v4" : "https://api.github.com"}
          value={data.apiBase}
          onChange={(e) => f({ apiBase: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>Owner</span>
        <input
          className="app-input font-mono text-sm"
          placeholder="org 或 user"
          value={data.owner}
          onChange={(e) => f({ owner: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>仓库名</span>
        <input
          className="app-input font-mono text-sm"
          placeholder="repo"
          value={data.repo}
          onChange={(e) => f({ repo: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>分支（可选）</span>
        <input
          className="app-input font-mono text-sm"
          placeholder="留空 = 默认分支"
          value={data.branch}
          onChange={(e) => f({ branch: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>子路径前缀（可选）</span>
        <input
          className="app-input font-mono text-sm"
          placeholder="例如 docs/"
          value={data.pathPrefix}
          onChange={(e) => f({ pathPrefix: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label sm:col-span-2">
        <span>访问令牌 {isEditing ? "（留空则不修改）" : ""}</span>
        <div className="app-field">
          <input
            className="app-input app-input--adorn-end font-mono text-sm"
            type={showToken ? "text" : "password"}
            autoComplete="off"
            placeholder={data.provider === "gitlab" ? "glpat-… 或 Private Token" : "ghp_… 或 fine-grained PAT"}
            value={data.token}
            onChange={(e) => f({ token: e.target.value })}
            disabled={disabled}
          />
          <button
            type="button"
            className="app-field__action text-app-muted hover:text-app-primary"
            tabIndex={-1}
            onClick={() => setShowToken((v) => !v)}
            aria-label={showToken ? "隐藏令牌" : "显示令牌"}
          >
            {showToken ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            )}
          </button>
        </div>
      </label>

      <label className="app-form-label sm:col-span-2">
        <span>包含 glob（逗号分隔）</span>
        <input
          className="app-input font-mono text-xs"
          value={data.includeGlobs}
          onChange={(e) => f({ includeGlobs: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>单文件上限 KB</span>
        <input
          className="app-input"
          type="number"
          min={8}
          max={4096}
          value={data.maxFileKb}
          onChange={(e) => f({ maxFileKb: Number(e.target.value) || 512 })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>最多文件数</span>
        <input
          className="app-input"
          type="number"
          min={1}
          max={5000}
          value={data.maxFiles}
          onChange={(e) => f({ maxFiles: Number(e.target.value) || 200 })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>Cron（可选）</span>
        <input
          className="app-input font-mono text-sm"
          placeholder="例 0 */6 * * * 每 6 小时"
          value={data.cron}
          onChange={(e) => f({ cron: e.target.value })}
          disabled={disabled}
        />
      </label>

      <label className="app-form-label">
        <span>抽取配置</span>
        <select
          className="app-input"
          value={data.extractionProfile}
          onChange={(e) => f({ extractionProfile: e.target.value as "mixed" | "data_warehouse" })}
          disabled={disabled}
        >
          <option value="mixed">mixed — 宽范围（含多语言代码）</option>
          <option value="data_warehouse">data_warehouse — 数仓优先（跳过 .ts/.tsx/.jsx）</option>
        </select>
      </label>

      <label className="app-form-label sm:col-span-2">
        <span>文档索引</span>
        <label className="mt-2 inline-flex items-center gap-2 text-sm text-app-secondary">
          <input
            type="checkbox"
            checked={data.enableDocumentIndexing}
            onChange={(e) => f({ enableDocumentIndexing: e.target.checked })}
            disabled={disabled}
          />
          启用文档分块与向量索引（用于语义检索；关闭时仅做代码解析）
        </label>
      </label>
    </div>
  );
}
