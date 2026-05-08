"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Breadcrumbs from "../../components/Breadcrumbs";
import ConfirmDialog from "../../components/ConfirmDialog";
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
    vendor_id?: string;
  }[];
  has_llm: boolean;
};

/** 语义分析展示：名称（接入自定义名）、厂商、具体模型 ID */
function tripletFromCatalogModel(m: Catalog["models"][number] | undefined): { name: string; vendor: string; model: string } {
  if (!m) return { name: "—", vendor: "—", model: "—" };
  return {
    name: (m.connection_name || "").trim() || "—",
    vendor: (m.kind_label || "").trim() || "—",
    model: (m.model_id || "").trim() || "—"
  };
}

function tripletForModelRef(catalog: Catalog, ref: string): { name: string; vendor: string; model: string } {
  const m = catalog.models.find((x) => x.id === ref);
  if (m) return tripletFromCatalogModel(m);
  return { name: "—", vendor: "—", model: ref || "—" };
}

function formatTripletLine(t: { name: string; vendor: string; model: string }) {
  return `${t.name} · ${t.vendor} · ${t.model}`;
}

type LlmConfig = {
  semantic_llm_model: string;
  semantic_llm_model_resolved: string;
};

type LlmConnPublic = {
  id: string;
  catalog_id: string;
  vendor_id: string;
  vendor_label: string;
  custom_name: string;
  base_url: string;
  provider: string;
  model_id: string;
  created_at: string;
};

type LlmConnDetail = LlmConnPublic & { api_key_configured?: boolean; api_key?: string };

type Channel = "openai" | "deepseek";

type VendorDef = {
  id: string;
  name: string;
  subtitle?: string;
  channel: Channel;
  presetBaseUrl?: string;
  presetConnectionName?: string;
  badge: "直连" | "OpenAI 兼容";
};

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

const DEEPSEEK_MODEL_IDS: { id: string; label: string }[] = [
  { id: "deepseek-v4-flash", label: "deepseek-v4-flash（V4 Flash）" },
  { id: "deepseek-v4-pro", label: "deepseek-v4-pro（V4 Pro）" },
  { id: "deepseek-chat", label: "deepseek-chat（兼容别名）" },
  { id: "deepseek-reasoner", label: "deepseek-reasoner（兼容别名）" }
];

const OPENAI_MODEL_IDS: { id: string; label: string }[] = [
  { id: "gpt-4o-mini", label: "gpt-4o-mini" },
  { id: "gpt-4o", label: "gpt-4o" },
  { id: "gpt-4-turbo", label: "gpt-4-turbo" }
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

function IconEye({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

function IconEyeOff({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.1A10.3 10.3 0 0112 5c6 0 10 7 10 7a18.4 18.4 0 01-2.9 3.1M6.2 6.2C3.9 8.2 2 12 2 12s4 7 10 7a9.7 9.7 0 004.1-.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function SettingsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [connections, setConnections] = useState<LlmConnPublic[]>([]);
  const [semantic, setSemantic] = useState("auto");
  const [savedSemantic, setSavedSemantic] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingConn, setSavingConn] = useState(false);
  const [toast, setToast] = useState<{ message: string; tone?: "success" | "error" } | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addVendorId, setAddVendorId] = useState(LLM_VENDORS[0].id);
  const [addModelId, setAddModelId] = useState(OPENAI_MODEL_IDS[0].id);
  const [addName, setAddName] = useState("");
  const [addUrl, setAddUrl] = useState("");
  const [addKey, setAddKey] = useState("");

  const [viewConnId, setViewConnId] = useState<string | null>(null);
  const [viewDetail, setViewDetail] = useState<LlmConnDetail | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewKeyVisible, setViewKeyVisible] = useState(false);
  const [viewKeyLoading, setViewKeyLoading] = useState(false);

  const [deleteConnId, setDeleteConnId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const connectRef = useRef<HTMLElement>(null);

  const addVendor = useMemo(() => LLM_VENDORS.find((v) => v.id === addVendorId) ?? LLM_VENDORS[0], [addVendorId]);
  const addChannel = addVendor.channel;
  const modelIdOptions = useMemo(() => (addChannel === "deepseek" ? DEEPSEEK_MODEL_IDS : OPENAI_MODEL_IDS), [addChannel]);

  useEffect(() => {
    setAddModelId((prev) => (modelIdOptions.some((o) => o.id === prev) ? prev : modelIdOptions[0].id));
  }, [modelIdOptions]);

  useEffect(() => {
    if (!addOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAddOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [addOpen]);

  useEffect(() => {
    if (!viewConnId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setViewConnId(null);
        setViewDetail(null);
        setViewKeyVisible(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewConnId]);

  async function load() {
    setLoading(true);
    try {
      const [cat, c, connRes] = await Promise.all([
        api<Catalog>("/api/llm/catalog"),
        api<LlmConfig>("/api/llm/config"),
        api<{ connections: LlmConnPublic[] }>("/api/llm/connections")
      ]);
      setCatalog(cat);
      setCfg(c);
      setSemantic(c.semantic_llm_model || "auto");
      setSavedSemantic(c.semantic_llm_model_resolved || "");
      setConnections(connRes.connections || []);
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
      const cat = await api<Catalog>("/api/llm/catalog");
      setCatalog(cat);
      setToast({ message: "已保存语义分析模型", tone: "success" });
    } catch {
      setToast({ message: "保存失败，请从可用模型中选择或选择自动", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  function openAddModal(vendorId?: string) {
    const vid = vendorId && LLM_VENDORS.some((v) => v.id === vendorId) ? vendorId : "openai";
    setAddVendorId(vid);
    const v = LLM_VENDORS.find((x) => x.id === vid) ?? LLM_VENDORS[0];
    setAddUrl(v.presetBaseUrl || "");
    setAddName(v.presetConnectionName || "");
    setAddKey("");
    setAddModelId(v.channel === "deepseek" ? DEEPSEEK_MODEL_IDS[0].id : OPENAI_MODEL_IDS[0].id);
    setAddOpen(true);
  }

  function applyVendorPresetInModal() {
    if (addVendor.presetBaseUrl) setAddUrl(addVendor.presetBaseUrl);
    if (addVendor.presetConnectionName) setAddName((n) => (n.trim() ? n : addVendor.presetConnectionName!));
  }

  async function submitNewConnection() {
    if (!addName.trim() || !addUrl.trim() || !addKey.trim()) {
      setToast({ message: "请填写自定义名称、Endpoint 与 API Key", tone: "error" });
      return;
    }
    setSavingConn(true);
    try {
      await api<LlmConnPublic>("/api/llm/connections", {
        method: "POST",
        body: JSON.stringify({
          vendor_id: addVendor.id,
          vendor_label: addVendor.name,
          custom_name: addName.trim(),
          base_url: addUrl.trim(),
          api_key: addKey.trim(),
          provider: addChannel === "deepseek" ? "deepseek" : "openai",
          model_id: addModelId
        })
      });
      setAddOpen(false);
      setAddKey("");
      await load();
      setToast({ message: "已保存接入", tone: "success" });
    } catch {
      setToast({ message: "保存失败，请检查 Endpoint 与模型名是否与厂商一致", tone: "error" });
    } finally {
      setSavingConn(false);
    }
  }

  async function openViewConnection(id: string) {
    setViewConnId(id);
    setViewDetail(null);
    setViewKeyVisible(false);
    setViewLoading(true);
    try {
      const d = await api<LlmConnDetail>(`/api/llm/connections/${id}`);
      setViewDetail(d);
    } catch {
      setToast({ message: "加载详情失败", tone: "error" });
      setViewConnId(null);
    } finally {
      setViewLoading(false);
    }
  }

  async function toggleViewApiKeyPlaintext() {
    if (!viewConnId || !viewDetail) return;
    if (viewKeyVisible) {
      setViewKeyVisible(false);
      return;
    }
    if (viewDetail.api_key !== undefined && viewDetail.api_key !== "") {
      setViewKeyVisible(true);
      return;
    }
    setViewKeyLoading(true);
    try {
      const d = await api<LlmConnDetail>(`/api/llm/connections/${viewConnId}?reveal_secret=true`);
      setViewDetail(d);
      setViewKeyVisible(true);
    } catch {
      setToast({ message: "无法获取密钥", tone: "error" });
    } finally {
      setViewKeyLoading(false);
    }
  }

  async function confirmDeleteConnection() {
    const id = deleteConnId;
    if (!id) return;
    setDeleting(true);
    try {
      const res = await api<{ catalog: Catalog; semantic_llm_model: string; semantic_llm_model_resolved: string }>(
        `/api/llm/connections/${id}`,
        { method: "DELETE" }
      );
      setDeleteConnId(null);
      setCatalog(res.catalog);
      if (cfg) {
        setCfg({
          ...cfg,
          semantic_llm_model: res.semantic_llm_model,
          semantic_llm_model_resolved: res.semantic_llm_model_resolved
        });
      }
      setSemantic(res.semantic_llm_model || "auto");
      setSavedSemantic(res.semantic_llm_model_resolved || "");
      const connRes = await api<{ connections: LlmConnPublic[] }>("/api/llm/connections");
      setConnections(connRes.connections || []);
      setToast({ message: "已从列表中删除该接入", tone: "success" });
    } catch {
      setToast({ message: "删除失败", tone: "error" });
    } finally {
      setDeleting(false);
    }
  }

  const semanticCustomModels = catalog
    ? catalog.models.filter((m) => m.model_family === "custom" || m.id.startsWith("conn:"))
    : [];

  const semanticSelectIds = useMemo(() => new Set(semanticCustomModels.map((m) => m.id)), [semanticCustomModels]);

  const hasSemanticConnections = connections.length > 0;

  const semanticOrphanOption =
    Boolean(catalog) &&
    semantic &&
    semantic !== "auto" &&
    !semanticSelectIds.has(semantic);

  const effectiveTriplet =
    catalog && savedSemantic ? tripletForModelRef(catalog, savedSemantic) : null;

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
                hasSemanticConnections ? "border-app-primary bg-app-activeBg text-app-primary" : "border-app-border bg-app-hover text-app-muted"
              }`}
              aria-hidden
            >
              2
            </div>
          </div>

          <div className="space-y-6">
            <section ref={connectRef} className="app-card rounded-2xl p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
                    <IconPlug />
                  </span>
                  <div>
                    <h2 className="app-card-title text-base">大模型接入</h2>
                    <p className="mt-1 text-[11px] text-app-muted">新增后写入数据库，并出现在下方「可用大模型」与语义分析/Copilot 可选列表中。</p>
                  </div>
                </div>
                <button type="button" className="app-button shrink-0 rounded-xl px-4 py-2 text-sm font-medium" onClick={() => openAddModal()}>
                  新增接入
                </button>
              </div>

              {loading ? (
                <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                  加载中
                </div>
              ) : (
                <div className="mt-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-app-muted">可用大模型</h3>
                  {connections.length === 0 ? (
                    <div className="mt-3 rounded-xl border border-dashed border-app-border bg-app-hover/30 px-4 py-8 text-center text-sm text-app-muted">
                      暂无接入，请点击右上角「新增接入」。
                    </div>
                  ) : (
                    <ul className="mt-3 divide-y divide-app-border overflow-hidden rounded-xl border border-app-border bg-white">
                      {connections.map((row) => (
                        <li key={row.id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-4">
                          <div className="min-w-0 flex-1 space-y-1">
                            <p className="truncate text-sm font-semibold text-app-ink">{row.custom_name}</p>
                            <p className="text-[11px] text-app-secondary">
                              <span className="text-app-muted">厂商</span> {row.vendor_label}
                              <span className="mx-1.5 text-app-border">·</span>
                              <span className="text-app-muted">模型</span>{" "}
                              <span className="font-mono text-app-ink">{row.model_id}</span>
                            </p>
                            <p className="truncate font-mono text-[10px] text-app-muted" title={row.base_url}>
                              {row.base_url}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            <button
                              type="button"
                              className="app-button-secondary rounded-lg px-3 py-1.5 text-xs font-medium"
                              onClick={() => void openViewConnection(row.id)}
                            >
                              查看
                            </button>
                            <button
                              type="button"
                              className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
                              onClick={() => setDeleteConnId(row.id)}
                            >
                              删除
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>

            <section className="app-card rounded-2xl p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
                  <IconColumns />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="app-card-title text-base">语义分析</h2>
                </div>
              </div>

              {loading ? (
                <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                  加载中
                </div>
              ) : !hasSemanticConnections ? (
                <div className="mt-6 flex flex-col items-center gap-4 rounded-2xl border border-dashed border-app-border bg-app-hover/30 px-4 py-10">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100/80 text-amber-700">
                    <IconColumns className="h-7 w-7" />
                  </div>
                  <p className="text-center text-sm text-app-secondary">尚未配置可用大模型，请先新增一条接入。</p>
                  <button type="button" className="app-button rounded-xl px-4 py-2 text-sm font-medium" onClick={() => openAddModal()}>
                    新增接入
                  </button>
                </div>
              ) : !catalog ? (
                <p className="mt-6 text-sm text-app-muted">模型目录加载中…</p>
              ) : (
                <div className="mt-5 space-y-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                    <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs font-medium text-app-secondary">
                      可选模型
                      <select
                        className="app-input rounded-xl px-3 py-2.5 text-sm focus-visible:ring-2 focus-visible:ring-app-border focus-visible:ring-offset-1"
                        value={semantic}
                        onChange={(e) => setSemantic(e.target.value)}
                      >
                        <option value={catalog.auto_id}>自动</option>
                        {semanticOrphanOption ? (
                          <option value={semantic} disabled>
                            （已不在列表）{formatTripletLine(tripletForModelRef(catalog, semantic))}
                          </option>
                        ) : null}
                        {semanticCustomModels.map((m) => (
                          <option key={m.id} value={m.id}>
                            {formatTripletLine(tripletFromCatalogModel(m))}
                          </option>
                        ))}
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
                  {effectiveTriplet ? (
                    <div className="rounded-xl border border-app-border bg-app-hover/40 px-3 py-3 text-sm">
                      <p className="text-[11px] font-medium text-app-muted">当前生效</p>
                      <dl className="mt-2 grid gap-2 sm:grid-cols-3">
                        <div>
                          <dt className="text-[10px] font-medium uppercase tracking-wide text-app-muted">名称</dt>
                          <dd className="mt-0.5 font-medium text-app-ink">{effectiveTriplet.name}</dd>
                        </div>
                        <div>
                          <dt className="text-[10px] font-medium uppercase tracking-wide text-app-muted">厂商</dt>
                          <dd className="mt-0.5 text-app-ink">{effectiveTriplet.vendor}</dd>
                        </div>
                        <div>
                          <dt className="text-[10px] font-medium uppercase tracking-wide text-app-muted">模型</dt>
                          <dd className="mt-0.5 font-mono text-xs text-app-ink">{effectiveTriplet.model}</dd>
                        </div>
                      </dl>
                    </div>
                  ) : null}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>

      {addOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div className="app-modal-backdrop app-modal-backdrop--front" role="presentation" onClick={() => setAddOpen(false)}>
            <div
              className="app-modal-surface app-chatgpt-dialog mx-4 max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl p-5 sm:p-6"
              role="dialog"
              aria-modal="true"
              aria-labelledby="llm-add-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 id="llm-add-title" className="text-base font-semibold text-app-ink">
                新增大模型接入
              </h3>
              <div className="mt-4 space-y-3">
                <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                  模型厂商
                  <select
                    className="app-input rounded-xl px-3 py-2.5 text-sm"
                    value={addVendorId}
                    onChange={(e) => {
                      const id = e.target.value;
                      setAddVendorId(id);
                      const v = LLM_VENDORS.find((x) => x.id === id);
                      if (v?.presetBaseUrl) setAddUrl(v.presetBaseUrl);
                      if (v?.presetConnectionName) setAddName(v.presetConnectionName);
                    }}
                  >
                    {LLM_VENDORS.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}（{v.badge}）
                      </option>
                    ))}
                  </select>
                </label>
                {addVendor.subtitle ? <p className="text-[11px] text-app-muted">{addVendor.subtitle}</p> : null}
                <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                  模型
                  <select className="app-input rounded-xl px-3 py-2.5 text-sm" value={addModelId} onChange={(e) => setAddModelId(e.target.value)}>
                    {modelIdOptions.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                  自定义名称
                  <input
                    className="app-input rounded-xl px-3 py-2 text-sm"
                    value={addName}
                    onChange={(e) => setAddName(e.target.value)}
                    placeholder="在列表中展示的名称"
                    autoComplete="off"
                  />
                </label>
                <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                  Endpoint（Base URL）
                  <input
                    className="app-input rounded-xl px-3 py-2 text-sm font-mono"
                    value={addUrl}
                    onChange={(e) => setAddUrl(e.target.value)}
                    placeholder="https://…"
                    autoComplete="off"
                  />
                </label>
                {addVendor.presetBaseUrl ? (
                  <button type="button" className="app-button-secondary rounded-lg px-3 py-1.5 text-xs" onClick={applyVendorPresetInModal}>
                    填入推荐 Base URL
                  </button>
                ) : null}
                <label className="flex flex-col gap-1.5 text-xs font-medium text-app-secondary">
                  API Key
                  <input
                    type="password"
                    className="app-input rounded-xl px-3 py-2 text-sm font-mono"
                    value={addKey}
                    onChange={(e) => setAddKey(e.target.value)}
                    autoComplete="off"
                    placeholder="保存后仅服务端存储，界面不回显"
                  />
                </label>
              </div>
              <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button type="button" className="app-dialog-btn app-dialog-btn-secondary w-full sm:w-auto" onClick={() => setAddOpen(false)} disabled={savingConn}>
                  取消
                </button>
                <button type="button" className="app-dialog-btn app-dialog-btn-primary w-full sm:w-auto" disabled={savingConn} onClick={() => void submitNewConnection()}>
                  {savingConn ? "保存中…" : "保存"}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}

      {viewConnId &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="app-modal-backdrop app-modal-backdrop--front"
            role="presentation"
            onClick={() => {
              setViewConnId(null);
              setViewDetail(null);
              setViewKeyVisible(false);
            }}
          >
            <div
              className="app-modal-surface app-chatgpt-dialog mx-4 max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl p-5 sm:p-6"
              role="dialog"
              aria-modal="true"
              aria-labelledby="llm-conn-view-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 id="llm-conn-view-title" className="text-base font-semibold text-app-ink">
                接入详情
              </h3>
              {viewLoading ? (
                <p className="mt-4 text-sm text-app-muted">加载中…</p>
              ) : viewDetail ? (
                <dl className="mt-4 space-y-3 text-sm">
                  <div>
                    <dt className="text-[11px] font-medium text-app-muted">自定义名称</dt>
                    <dd className="mt-0.5 font-medium text-app-ink">{viewDetail.custom_name}</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] font-medium text-app-muted">厂商</dt>
                    <dd className="mt-0.5 text-app-ink">{viewDetail.vendor_label}</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] font-medium text-app-muted">模型</dt>
                    <dd className="mt-0.5 font-mono text-xs text-app-secondary">{viewDetail.model_id}</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] font-medium text-app-muted">Endpoint</dt>
                    <dd className="mt-0.5 break-all font-mono text-xs text-app-secondary">{viewDetail.base_url}</dd>
                  </div>
                  <div>
                    <dt className="flex items-center justify-between gap-2 text-[11px] font-medium text-app-muted">
                      <span className="flex items-center gap-2">
                        API Key
                        <StatusDot ok={Boolean(viewDetail.api_key_configured)} />
                      </span>
                      {viewDetail.api_key_configured ? (
                        <button
                          type="button"
                          className="inline-flex shrink-0 rounded-lg p-1.5 text-app-secondary hover:bg-app-hover hover:text-app-ink"
                          onClick={() => void toggleViewApiKeyPlaintext()}
                          disabled={viewKeyLoading}
                          aria-label={viewKeyVisible ? "隐藏 API Key" : "显示 API Key 明文"}
                          aria-pressed={viewKeyVisible}
                          title={viewKeyVisible ? "隐藏" : "查看明文"}
                        >
                          {viewKeyLoading ? (
                            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
                          ) : viewKeyVisible ? (
                            <IconEyeOff className="h-4 w-4" />
                          ) : (
                            <IconEye className="h-4 w-4" />
                          )}
                        </button>
                      ) : null}
                    </dt>
                    <dd className="mt-1 break-all font-mono text-xs text-app-ink">
                      {!viewDetail.api_key_configured ? (
                        "未配置"
                      ) : viewKeyVisible && viewDetail.api_key !== undefined ? (
                        <span className="select-all">{viewDetail.api_key || "（空）"}</span>
                      ) : (
                        <span className="text-app-muted">············ 点击眼睛图标查看明文</span>
                      )}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="mt-4 text-sm text-app-muted">无数据</p>
              )}
              <button
                type="button"
                className="app-dialog-btn app-dialog-btn-secondary mt-6 w-full"
                onClick={() => {
                  setViewConnId(null);
                  setViewDetail(null);
                  setViewKeyVisible(false);
                }}
              >
                关闭
              </button>
            </div>
          </div>,
          document.body
        )}

      <ConfirmDialog
        open={deleteConnId !== null}
        title="删除该接入？"
        description="将从数据库中删除此条配置，并从可用大模型列表中移除。若语义分析正使用该模型，将自动改回「自动」。"
        confirmText="删除"
        cancelText="取消"
        danger
        loading={deleting}
        onCancel={() => setDeleteConnId(null)}
        onConfirm={() => {
          const id = deleteConnId;
          if (id) void confirmDeleteConnection();
        }}
      />

      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </main>
  );
}
