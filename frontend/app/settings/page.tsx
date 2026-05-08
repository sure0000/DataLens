"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Breadcrumbs from "../../components/Breadcrumbs";
import PageHeader from "../../components/PageHeader";
import Toast from "../../components/Toast";
import { api } from "../../lib/api";

type Catalog = {
  auto_id: string;
  auto_label: string;
  auto_resolved: string;
  auto_resolved_label?: string;
  models: {
    id: string;
    label: string;
    provider: string;
    kind_label: string;
    connection_name: string;
    model_id: string;
    model_short_label?: string;
    model_family?: string;
  }[];
  has_llm: boolean;
};

type LlmConfig = {
  semantic_llm_model: string;
  semantic_llm_model_resolved: string;
  deepseek_base_url: string;
  openai_base_url: string;
  deepseek_connection_name: string;
  openai_connection_name: string;
  deepseek_api_key_configured: boolean;
  openai_api_key_configured: boolean;
  deepseek_base_url_effective: string;
  openai_base_url_effective: string;
};

type Channel = "openai" | "deepseek";

type VendorDef = {
  id: string;
  name: string;
  subtitle?: string;
  channel: Channel;
  presetBaseUrl?: string;
  /** 填入预设时写入连接名称（若当前名称为空或用户未改过时可配合使用） */
  presetConnectionName?: string;
  badge: "直连" | "OpenAI 兼容";
};

/** 与后端能力对齐：DeepSeek 直连一条；其余厂商走 OpenAI 兼容单槽（官方文档中的兼容 Base URL 作预设） */
const LLM_VENDORS: VendorDef[] = [
  { id: "openai", name: "OpenAI", channel: "openai", presetBaseUrl: "https://api.openai.com/v1", presetConnectionName: "OpenAI 官方", badge: "OpenAI 兼容" },
  { id: "azure", name: "Microsoft Azure OpenAI", channel: "openai", subtitle: "Azure 资源中的 OpenAI 兼容端点", presetConnectionName: "Azure OpenAI", badge: "OpenAI 兼容" },
  { id: "anthropic", name: "Anthropic (Claude)", channel: "openai", subtitle: "经 OpenAI 兼容网关或中转", presetConnectionName: "Claude 网关", badge: "OpenAI 兼容" },
  { id: "google", name: "Google (Gemini)", channel: "openai", subtitle: "经 OpenAI 兼容网关", presetConnectionName: "Gemini 网关", badge: "OpenAI 兼容" },
  { id: "deepseek", name: "DeepSeek", channel: "deepseek", presetBaseUrl: "https://api.deepseek.com", presetConnectionName: "DeepSeek 官方", badge: "直连" },
  { id: "moonshot", name: "月之暗面 Moonshot (Kimi)", channel: "openai", presetBaseUrl: "https://api.moonshot.cn/v1", presetConnectionName: "Kimi", badge: "OpenAI 兼容" },
  { id: "dashscope", name: "阿里通义 DashScope", channel: "openai", presetBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", presetConnectionName: "通义", badge: "OpenAI 兼容" },
  { id: "volcengine", name: "字节火山引擎方舟", channel: "openai", subtitle: "方舟控制台提供的 OpenAI 兼容地址", presetConnectionName: "火山方舟", badge: "OpenAI 兼容" },
  { id: "baidu", name: "百度千帆", channel: "openai", subtitle: "千帆 OpenAI 兼容接口地址", presetConnectionName: "千帆", badge: "OpenAI 兼容" },
  { id: "zhipu", name: "智谱 AI (GLM)", channel: "openai", presetBaseUrl: "https://open.bigmodel.cn/api/paas/v4", presetConnectionName: "智谱", badge: "OpenAI 兼容" },
  { id: "openrouter", name: "OpenRouter", channel: "openai", presetBaseUrl: "https://openrouter.ai/api/v1", presetConnectionName: "OpenRouter", badge: "OpenAI 兼容" },
  { id: "mistral", name: "Mistral AI", channel: "openai", presetBaseUrl: "https://api.mistral.ai/v1", presetConnectionName: "Mistral", badge: "OpenAI 兼容" },
  { id: "groq", name: "Groq", channel: "openai", presetBaseUrl: "https://api.groq.com/openai/v1", presetConnectionName: "Groq", badge: "OpenAI 兼容" },
  { id: "cohere", name: "Cohere", channel: "openai", subtitle: "按控制台提供的兼容 REST 根路径填写", presetConnectionName: "Cohere", badge: "OpenAI 兼容" },
  { id: "siliconflow", name: "硅基流动 SiliconFlow", channel: "openai", presetBaseUrl: "https://api.siliconflow.cn/v1", presetConnectionName: "硅基流动", badge: "OpenAI 兼容" },
  { id: "bedrock", name: "Amazon Bedrock", channel: "openai", subtitle: "经 OpenAI 兼容代理或自定义网关", presetConnectionName: "Bedrock", badge: "OpenAI 兼容" },
  { id: "tencent", name: "腾讯云混元 / LKEAP", channel: "openai", subtitle: "控制台提供的 OpenAI 兼容根地址", presetConnectionName: "腾讯云", badge: "OpenAI 兼容" },
  { id: "custom", name: "自定义 / 其他", channel: "openai", subtitle: "任意提供 OpenAI 风格 /v1 的网关", badge: "OpenAI 兼容" }
];

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${ok ? "bg-emerald-500" : "bg-app-border"}`}
      aria-hidden
    />
  );
}

function IconPlug({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M12 22v-9" strokeLinecap="round" />
      <path d="M9 7V5a3 3 0 016 0v2" strokeLinecap="round" />
      <path d="M5 10h14v4a4 4 0 01-4 4H9a4 4 0 01-4-4v-4z" strokeLinejoin="round" />
    </svg>
  );
}

function IconColumns({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18M15 9h.01M15 15h.01" />
    </svg>
  );
}

function IconCopilotLink({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconChevron({ className = "h-4 w-4", open }: { className?: string; open?: boolean }) {
  return (
    <svg
      className={`${className} shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
    >
      <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function SettingsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [semantic, setSemantic] = useState("auto");
  const [savedSemantic, setSavedSemantic] = useState("");
  const [dsUrl, setDsUrl] = useState("");
  const [oaUrl, setOaUrl] = useState("");
  const [dsKey, setDsKey] = useState("");
  const [oaKey, setOaKey] = useState("");
  const [dsName, setDsName] = useState("");
  const [oaName, setOaName] = useState("");
  const [selectedVendorId, setSelectedVendorId] = useState<string>(LLM_VENDORS[0].id);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingApi, setSavingApi] = useState(false);
  const [toast, setToast] = useState<{ message: string; tone?: "success" | "error" } | null>(null);
  const connectRef = useRef<HTMLElement>(null);

  async function load() {
    setLoading(true);
    try {
      const [cat, c] = await Promise.all([api<Catalog>("/api/llm/catalog"), api<LlmConfig>("/api/llm/config")]);
      setCatalog(cat);
      setCfg(c);
      setSemantic(c.semantic_llm_model || "auto");
      setSavedSemantic(c.semantic_llm_model_resolved || "");
      setDsUrl(c.deepseek_base_url || "");
      setOaUrl(c.openai_base_url || "");
      setDsName(c.deepseek_connection_name || "");
      setOaName(c.openai_connection_name || "");
      setDsKey("");
      setOaKey("");
    } catch {
      setToast({ message: "加载失败，请确认后端已启动", tone: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function saveSemantic() {
    setSaving(true);
    try {
      const res = await api<LlmConfig>("/api/llm/config", {
        method: "PUT",
        body: JSON.stringify({ semantic_llm_model: semantic })
      });
      setSavedSemantic(res.semantic_llm_model_resolved || "");
      setCfg(res);
      setDsName(res.deepseek_connection_name || "");
      setOaName(res.openai_connection_name || "");
      const cat = await api<Catalog>("/api/llm/catalog");
      setCatalog(cat);
      setToast({ message: "已保存语义分析模型", tone: "success" });
    } catch {
      setToast({ message: "保存失败，请检查模型是否在可选列表中且至少一方 API 已配置", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function saveApiCredentials() {
    setSavingApi(true);
    try {
      const body: Record<string, string> = {
        deepseek_base_url: dsUrl,
        openai_base_url: oaUrl,
        deepseek_connection_name: dsName,
        openai_connection_name: oaName
      };
      if (dsKey.trim()) body.deepseek_api_key = dsKey.trim();
      if (oaKey.trim()) body.openai_api_key = oaKey.trim();
      const res = await api<LlmConfig>("/api/llm/config", { method: "PUT", body: JSON.stringify(body) });
      setCfg(res);
      setDsName(res.deepseek_connection_name || "");
      setOaName(res.openai_connection_name || "");
      setDsKey("");
      setOaKey("");
      const cat = await api<Catalog>("/api/llm/catalog");
      setCatalog(cat);
      setToast({ message: "已保存接入配置", tone: "success" });
    } catch {
      setToast({ message: "保存失败", tone: "error" });
    } finally {
      setSavingApi(false);
    }
  }

  async function clearDeepseekKey() {
    setSavingApi(true);
    try {
      const res = await api<LlmConfig>("/api/llm/config", {
        method: "PUT",
        body: JSON.stringify({ deepseek_api_key: "" })
      });
      setCfg(res);
      const cat = await api<Catalog>("/api/llm/catalog");
      setCatalog(cat);
      setToast({ message: "已清除 DeepSeek 库内密钥覆盖", tone: "success" });
    } catch {
      setToast({ message: "操作失败", tone: "error" });
    } finally {
      setSavingApi(false);
    }
  }

  async function clearOpenaiKey() {
    setSavingApi(true);
    try {
      const res = await api<LlmConfig>("/api/llm/config", {
        method: "PUT",
        body: JSON.stringify({ openai_api_key: "" })
      });
      setCfg(res);
      const cat = await api<Catalog>("/api/llm/catalog");
      setCatalog(cat);
      setToast({ message: "已清除 OpenAI 兼容侧库内密钥覆盖", tone: "success" });
    } catch {
      setToast({ message: "操作失败", tone: "error" });
    } finally {
      setSavingApi(false);
    }
  }

  const activeVendor = useMemo(
    () => LLM_VENDORS.find((v) => v.id === selectedVendorId) ?? LLM_VENDORS[0],
    [selectedVendorId]
  );
  const channel: Channel = activeVendor.channel;

  function goConfigureVendor(vendorId: string) {
    setSelectedVendorId(vendorId);
    requestAnimationFrame(() => {
      connectRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function applyVendorPreset() {
    if (activeVendor.channel === "deepseek" && activeVendor.presetBaseUrl) {
      setDsUrl(activeVendor.presetBaseUrl);
      if (activeVendor.presetConnectionName) setDsName((n) => (n.trim() ? n : activeVendor.presetConnectionName!));
      return;
    }
    if (activeVendor.channel === "openai" && activeVendor.presetBaseUrl) {
      setOaUrl(activeVendor.presetBaseUrl);
      if (activeVendor.presetConnectionName) setOaName((n) => (n.trim() ? n : activeVendor.presetConnectionName!));
    }
  }

  const catalogGroups = catalog
    ? {
        dsV4: catalog.models.filter((m) => m.provider === "deepseek" && m.model_family === "v4"),
        dsChat: catalog.models.filter((m) => m.provider === "deepseek" && m.model_family === "chat"),
        openai: catalog.models.filter((m) => m.provider === "openai")
      }
    : null;

  const autoSelectLabel = catalog
    ? `${catalog.auto_label}${
        catalog.auto_resolved_label || catalog.auto_resolved
          ? ` → ${catalog.auto_resolved_label || catalog.auto_resolved}`
          : ""
      }`
    : "";

  const resolvedHumanLabel =
    (catalog && savedSemantic && catalog.models.find((m) => m.id === savedSemantic)?.label) ||
    (semantic === "auto" && catalog?.auto_resolved_label) ||
    savedSemantic;

  const openaiKeyOk = Boolean(cfg?.openai_api_key_configured);
  const deepseekKeyOk = Boolean(cfg?.deepseek_api_key_configured);
  const modelCount = catalog?.models.length ?? 0;

  const providerChips =
    catalog?.has_llm && catalog.models.length
      ? Array.from(
          new Map(
            catalog.models.map((m) => {
              const conn = (m.connection_name || "").trim();
              const text = conn ? `${m.kind_label}「${conn}」` : m.kind_label;
              return [text, text] as const;
            })
          ).values()
        ).map((text) => (
          <span
            key={text}
            className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-hover px-2 py-0.5 text-[11px] font-medium text-app-secondary"
          >
            <StatusDot ok />
            {text}
          </span>
        ))
      : null;

  return (
    <main className="app-page">
      <div className="app-breadcrumb-strip">
        <Breadcrumbs items={[{ label: "首页", href: "/" }, { label: "偏好设置" }]} />
      </div>
      <PageHeader title="偏好设置" />

      <div className="mx-auto mt-6 max-w-2xl pb-16">
        <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 sm:gap-x-4">
          <div className="flex flex-col items-center pt-1">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-app-primary bg-app-activeBg text-xs font-bold text-app-primary"
              aria-hidden
            >
              1
            </div>
            <div className="my-2 min-h-[3rem] w-0 flex-1 border-l-2 border-dashed border-app-border sm:min-h-[4rem]" aria-hidden />
            <div
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold ${
                catalog?.has_llm ? "border-app-primary bg-app-activeBg text-app-primary" : "border-app-border bg-app-hover text-app-muted"
              }`}
              aria-hidden
            >
              2
            </div>
          </div>

          <div className="space-y-6">
            <section ref={connectRef} className="app-card rounded-2xl p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
                  <IconPlug />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="app-card-title text-base">大模型接入</h2>
                </div>
              </div>

              {loading ? (
                <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                  加载中
                </div>
              ) : (
                <div className="mt-5 flex flex-col gap-5 lg:flex-row lg:items-start">
                  <div className="lg:sticky lg:top-4 lg:max-h-[min(70vh,520px)] lg:w-[min(100%,300px)] lg:shrink-0 lg:overflow-y-auto">
                    <ul className="divide-y divide-app-border overflow-hidden rounded-xl border border-app-border bg-white">
                      {LLM_VENDORS.map((v) => {
                        const keyOk = v.channel === "deepseek" ? deepseekKeyOk : openaiKeyOk;
                        const selected = v.id === selectedVendorId;
                        return (
                          <li key={v.id}>
                            <button
                              type="button"
                              onClick={() => setSelectedVendorId(v.id)}
                              className={`flex w-full items-center gap-2 px-3 py-2.5 text-left transition sm:px-4 sm:py-3 ${
                                selected ? "border-l-[3px] border-l-app-primary bg-app-activeBg" : "border-l-[3px] border-l-transparent hover:bg-app-hover"
                              }`}
                            >
                              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                                <span className="flex flex-wrap items-center gap-1.5">
                                  <span className="truncate text-xs font-semibold text-app-ink">{v.name}</span>
                                  <span
                                    className={`shrink-0 rounded px-1.5 py-px text-[10px] font-medium ${
                                      v.badge === "直连"
                                        ? "bg-emerald-100 text-emerald-800"
                                        : "bg-slate-100 text-slate-600"
                                    }`}
                                  >
                                    {v.badge}
                                  </span>
                                </span>
                                {v.subtitle ? (
                                  <span className="line-clamp-2 text-[10px] leading-snug text-app-muted">{v.subtitle}</span>
                                ) : null}
                              </span>
                              <span className="flex shrink-0 items-center gap-1.5">
                                <StatusDot ok={keyOk} />
                                <IconChevron className="text-app-muted opacity-60" open={selected} />
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  <div className="min-w-0 flex-1 space-y-4">
                    <div className="rounded-xl border border-app-border bg-app-hover/30 px-3 py-2">
                      <p className="text-xs font-semibold text-app-ink">{activeVendor.name}</p>
                      {activeVendor.subtitle ? <p className="mt-0.5 text-[11px] text-app-muted">{activeVendor.subtitle}</p> : null}
                    </div>

                    {activeVendor.presetBaseUrl ? (
                      <button
                        type="button"
                        className="app-button-secondary w-full rounded-xl px-3 py-2 text-xs font-medium sm:w-auto"
                        disabled={savingApi}
                        onClick={applyVendorPreset}
                      >
                        填入推荐 Base URL
                      </button>
                    ) : null}

                    {channel === "openai" ? (
                      <div className="app-nested-panel space-y-3">
                        <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                          名称
                          <input
                            className="app-input rounded-xl px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                            value={oaName}
                            onChange={(e) => setOaName(e.target.value)}
                            placeholder="在语义分析中区分接入"
                            autoComplete="off"
                          />
                        </label>
                        <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                          Base URL
                          <input
                            className="app-input rounded-xl px-3 py-2 text-sm font-mono focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                            value={oaUrl}
                            onChange={(e) => setOaUrl(e.target.value)}
                            placeholder="https://…/v1"
                            autoComplete="off"
                          />
                        </label>
                        <p className="font-mono text-[11px] text-app-muted">
                          <span className="text-app-secondary">→</span> {cfg?.openai_base_url_effective || "—"}
                        </p>
                        <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                          API Key
                          <input
                            type="password"
                            className="app-input rounded-xl px-3 py-2 text-sm font-mono focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                            value={oaKey}
                            onChange={(e) => setOaKey(e.target.value)}
                            autoComplete="off"
                            placeholder={cfg?.openai_api_key_configured ? "········（留空不改）" : "sk-…"}
                          />
                        </label>
                        {cfg?.openai_api_key_configured && (
                          <button
                            type="button"
                            className="self-start rounded-lg px-2 py-1 text-[11px] text-rose-600 hover:bg-rose-50"
                            disabled={savingApi}
                            onClick={() => void clearOpenaiKey()}
                          >
                            清除库内覆盖
                          </button>
                        )}
                      </div>
                    ) : (
                      <div className="app-nested-panel space-y-3">
                        <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                          名称
                          <input
                            className="app-input rounded-xl px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                            value={dsName}
                            onChange={(e) => setDsName(e.target.value)}
                            placeholder="在语义分析中区分接入"
                            autoComplete="off"
                          />
                        </label>
                        <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                          Base URL
                          <input
                            className="app-input rounded-xl px-3 py-2 text-sm font-mono focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                            value={dsUrl}
                            onChange={(e) => setDsUrl(e.target.value)}
                            placeholder="https://api.deepseek.com"
                            autoComplete="off"
                          />
                        </label>
                        <p className="font-mono text-[11px] text-app-muted">
                          <span className="text-app-secondary">→</span> {cfg?.deepseek_base_url_effective || "—"}
                        </p>
                        <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                          API Key
                          <input
                            type="password"
                            className="app-input rounded-xl px-3 py-2 text-sm font-mono focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                            value={dsKey}
                            onChange={(e) => setDsKey(e.target.value)}
                            autoComplete="off"
                            placeholder={cfg?.deepseek_api_key_configured ? "········（留空不改）" : "填写密钥"}
                          />
                        </label>
                        {cfg?.deepseek_api_key_configured && (
                          <button
                            type="button"
                            className="self-start rounded-lg px-2 py-1 text-[11px] text-rose-600 hover:bg-rose-50"
                            disabled={savingApi}
                            onClick={() => void clearDeepseekKey()}
                          >
                            清除库内覆盖
                          </button>
                        )}
                      </div>
                    )}

                    <button
                      type="button"
                      className="app-button w-full rounded-xl px-4 py-2.5 text-sm font-medium sm:w-auto"
                      disabled={savingApi}
                      onClick={() => void saveApiCredentials()}
                    >
                      {savingApi ? "保存中…" : "保存接入"}
                    </button>
                  </div>
                </div>
              )}
            </section>

            <section className="app-card rounded-2xl p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
                    <IconColumns />
                  </span>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="app-card-title text-base">语义分析</h2>
                      {catalog?.has_llm && (
                        <span className="rounded-full border border-app-border bg-app-hover px-2 py-0.5 text-[11px] font-medium tabular-nums text-app-secondary">
                          {modelCount} 个模型
                        </span>
                      )}
                    </div>
                    {providerChips && <div className="mt-2 flex flex-wrap gap-1.5">{providerChips}</div>}
                  </div>
                </div>
                <Link
                  href="/copilot"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-transparent px-2 py-1.5 text-app-link hover:border-app-border hover:bg-app-hover"
                >
                  <IconCopilotLink />
                  <span className="text-xs font-medium">Copilot</span>
                </Link>
              </div>

              {loading ? (
                <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                  加载中
                </div>
              ) : !catalog?.has_llm ? (
                <div className="mt-6 flex flex-col items-center gap-4 rounded-2xl border border-dashed border-app-border bg-app-hover/30 px-4 py-10">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100/80 text-amber-700">
                    <IconColumns className="h-7 w-7" />
                  </div>
                  <div className="flex flex-wrap justify-center gap-2">
                    <button
                      type="button"
                      className="app-button rounded-xl px-4 py-2 text-sm font-medium"
                      onClick={() => goConfigureVendor("openai")}
                    >
                      去填 OpenAI 兼容
                    </button>
                    <button
                      type="button"
                      className="app-button-secondary rounded-xl px-4 py-2 text-sm font-medium"
                      onClick={() => goConfigureVendor("deepseek")}
                    >
                      去填 DeepSeek
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mt-5 space-y-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                    <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs font-medium text-app-secondary">
                      模型
                      <select
                        className="app-input rounded-xl px-3 py-2.5 text-sm focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                        value={semantic}
                        onChange={(e) => setSemantic(e.target.value)}
                      >
                        <option value={catalog.auto_id}>{autoSelectLabel}</option>
                        {catalogGroups && catalogGroups.dsV4.length > 0 ? (
                          <optgroup label="DeepSeek · V4">
                            {catalogGroups.dsV4.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.label}
                              </option>
                            ))}
                          </optgroup>
                        ) : null}
                        {catalogGroups && catalogGroups.dsChat.length > 0 ? (
                          <optgroup label="DeepSeek · Chat / Reasoner（兼容别名）">
                            {catalogGroups.dsChat.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.label}
                              </option>
                            ))}
                          </optgroup>
                        ) : null}
                        {catalogGroups && catalogGroups.openai.length > 0 ? (
                          <optgroup label="OpenAI 兼容">
                            {catalogGroups.openai.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.label}
                              </option>
                            ))}
                          </optgroup>
                        ) : null}
                      </select>
                    </label>
                    <button
                      type="button"
                      className="app-button shrink-0 rounded-xl px-4 py-2.5 text-sm font-medium"
                      disabled={saving}
                      onClick={() => void saveSemantic()}
                    >
                      {saving ? "保存中…" : "保存"}
                    </button>
                  </div>
                  {savedSemantic ? (
                    <div className="rounded-xl border border-app-border bg-app-hover/40 px-3 py-2 text-[11px] leading-snug text-app-secondary">
                      <span className="text-app-muted">当前生效</span>
                      <p className="mt-0.5 font-medium text-app-ink">{resolvedHumanLabel}</p>
                      <p className="mt-1 font-mono text-[10px] text-app-muted">{savedSemantic}</p>
                    </div>
                  ) : null}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </main>
  );
}
