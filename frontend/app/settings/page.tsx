"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import Breadcrumbs from "../../components/Breadcrumbs";
import ConfirmDialog from "../../components/ConfirmDialog";
import PageHeader from "../../components/PageHeader";
import Toast from "../../components/Toast";
import ApiSourcesTab from "../../components/settings/ApiSourcesTab";
import ModelsTab from "../../components/settings/ModelsTab";
import SemanticTab from "../../components/settings/SemanticTab";
import { api } from "../../lib/api";
import { useToast } from "../../hooks/useToast";
import { useEscapeKey } from "../../hooks/useEscapeKey";

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

const SILICONFLOW_MODEL_IDS: { id: string; label: string }[] = [
  { id: "deepseek-ai/DeepSeek-V4-Flash", label: "DeepSeek-V4-Flash（284B MoE）" },
  { id: "Qwen/Qwen3.6-27B", label: "Qwen3.6-27B（Dense 27B）" },
  { id: "Pro/moonshotai/Kimi-K2.6", label: "Kimi-K2.6（1T MoE）" },
  { id: "Qwen/Qwen3.6-35B-A3B", label: "Qwen3.6-35B-A3B（35B MoE）" },
  { id: "Pro/zai-org/GLM-5.1", label: "GLM-5.1（754B MoE）" },
  { id: "Pro/zai-org/GLM-5", label: "GLM-5（754B MoE）" },
  { id: "MiniMaxAI/MiniMax-M2.5", label: "MiniMax-M2.5" },
  { id: "Pro/MiniMaxAI/MiniMax-M2.5", label: "MiniMax-M2.5 Pro" },
  { id: "Qwen/Qwen3.5-397B-A17B", label: "Qwen3.5-397B-A17B（397B MoE）" },
  { id: "Qwen/Qwen3.5-122B-A10B", label: "Qwen3.5-122B-A10B（122B MoE）" },
  { id: "Qwen/Qwen3.5-35B-A3B", label: "Qwen3.5-35B-A3B（35B MoE）" },
  { id: "Pro/moonshotai/Kimi-K2.5", label: "Kimi-K2.5（1T MoE）" },
  { id: "Pro/zai-org/GLM-4.7", label: "GLM-4.7（754B MoE）" },
  { id: "deepseek-ai/DeepSeek-V3.2", label: "DeepSeek-V3.2" },
  { id: "Pro/deepseek-ai/DeepSeek-V3.2", label: "DeepSeek-V3.2 Pro" },
  { id: "deepseek-ai/DeepSeek-V3.1-Terminus", label: "DeepSeek-V3.1-Terminus" },
  { id: "Pro/deepseek-ai/DeepSeek-V3.1-Terminus", label: "DeepSeek-V3.1-Terminus Pro" },
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
  const [activeTab, setActiveTab] = useState<"models" | "semantic" | "api_sources">("models");
  const [connections, setConnections] = useState<LlmConnPublic[]>([]);
  const [semantic, setSemantic] = useState("auto");
  const [savedSemantic, setSavedSemantic] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingConn, setSavingConn] = useState(false);
  const { toast, notify, dismiss } = useToast();

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

  const addVendor = useMemo(() => LLM_VENDORS.find((v) => v.id === addVendorId) ?? LLM_VENDORS[0], [addVendorId]);
  const addChannel = addVendor.channel;
  const modelIdOptions = useMemo(() => {
    if (addVendorId === "siliconflow") return SILICONFLOW_MODEL_IDS;
    if (addChannel === "deepseek") return DEEPSEEK_MODEL_IDS;
    return OPENAI_MODEL_IDS;
  }, [addChannel, addVendorId]);

  useEffect(() => {
    setAddModelId((prev) => (modelIdOptions.some((o) => o.id === prev) ? prev : modelIdOptions[0].id));
  }, [modelIdOptions]);

  useEscapeKey(() => setAddOpen(false), addOpen);
  useEscapeKey(() => { setViewConnId(null); setViewDetail(null); setViewKeyVisible(false); }, viewConnId !== null);

  async function load() {
    setLoading(true);
    try {
      const [cat, c, connRes] = await Promise.all([
        api<Catalog>("/api/llm/catalog"),
        api<LlmConfig>("/api/llm/config"),
        api<{ connections: LlmConnPublic[] }>("/api/llm/connections"),
      ]);
      setCatalog(cat);
      setCfg(c);
      setSemantic(c.semantic_llm_model || "auto");
      setSavedSemantic(c.semantic_llm_model_resolved || "");
      setConnections(connRes.connections || []);
    } catch {
      notify("加载失败，请确认后端已启动", "error");
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
      notify("已保存语义分析模型");
    } catch {
      notify("保存失败，请从可用模型中选择或选择自动", "error");
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
    setAddModelId(v.id === "siliconflow" ? SILICONFLOW_MODEL_IDS[0].id : v.channel === "deepseek" ? DEEPSEEK_MODEL_IDS[0].id : OPENAI_MODEL_IDS[0].id);
    setAddOpen(true);
  }

  function applyVendorPresetInModal() {
    if (addVendor.presetBaseUrl) setAddUrl(addVendor.presetBaseUrl);
    if (addVendor.presetConnectionName) setAddName((n) => (n.trim() ? n : addVendor.presetConnectionName!));
  }

  async function submitNewConnection() {
    if (!addName.trim() || !addUrl.trim() || !addKey.trim()) {
      notify("请填写自定义名称、Endpoint 与 API Key", "error");
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
      notify("已保存接入");
    } catch {
      notify("保存失败，请检查 Endpoint 与模型名是否与厂商一致", "error");
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
      notify("加载详情失败", "error");
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
      notify("无法获取密钥", "error");
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
      notify("已从列表中删除该接入");
    } catch {
      notify("删除失败", "error");
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
        <div className="flex gap-4">
          {/* ── 左侧 Tab 栏 ── */}
          <nav className="w-36 shrink-0 flex flex-col gap-1" role="tablist" aria-label="偏好设置分类">
            <button
              role="tab"
              aria-selected={activeTab === "models"}
              onClick={() => setActiveTab("models")}
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-left transition-colors ${
                activeTab === "models"
                  ? "bg-app-activeBg text-app-primary border border-app-primary/20"
                  : "text-app-secondary hover:bg-app-hover hover:text-app-ink"
              }`}
            >
              <IconPlug className="h-4 w-4 shrink-0" />
              模型管理
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "semantic"}
              onClick={() => setActiveTab("semantic")}
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-left transition-colors ${
                activeTab === "semantic"
                  ? "bg-app-activeBg text-app-primary border border-app-primary/20"
                  : "text-app-secondary hover:bg-app-hover hover:text-app-ink"
              }`}
            >
              <IconColumns className="h-4 w-4 shrink-0" />
              语义分析
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "api_sources"}
              onClick={() => setActiveTab("api_sources")}
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-left transition-colors ${
                activeTab === "api_sources"
                  ? "bg-app-activeBg text-app-primary border border-app-primary/20"
                  : "text-app-secondary hover:bg-app-hover hover:text-app-ink"
              }`}
            >
              <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
              API 源
            </button>
          </nav>

          {/* ── 右侧内容面板 ── */}
          <div className="min-w-0 flex-1">
            {activeTab === "models" && (
              <ModelsTab
                loading={loading}
                connections={connections}
                onAdd={() => openAddModal()}
                onView={(id) => { void openViewConnection(id); }}
                onDelete={setDeleteConnId}
              />
            )}

            {activeTab === "semantic" && (
              <SemanticTab
                loading={loading}
                catalog={catalog}
                semantic={semantic}
                onSemanticChange={setSemantic}
                saving={saving}
                hasSemanticConnections={hasSemanticConnections}
                semanticCustomModels={semanticCustomModels}
                semanticOrphanOption={!!semanticOrphanOption}
                effectiveTriplet={effectiveTriplet}
                onSave={() => { void saveSemantic(); }}
                onAdd={() => openAddModal()}
              />
            )}

            {activeTab === "api_sources" && <ApiSourcesTab />}

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



      <Toast message={toast.message} tone={toast.tone} duration={toast.durationMs} onClose={dismiss} />
    </main>
  );
}
