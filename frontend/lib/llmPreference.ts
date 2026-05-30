/** Copilot / 设置页共用：大模型目录展示与对话模型偏好 */

export type LlmCatalogModel = {
  id: string;
  label: string;
  provider: string;
  kind_label: string;
  connection_name: string;
  model_id: string;
  model_short_label?: string;
  model_family?: string;
};

export type LlmCatalogLike = {
  auto_id: string;
  auto_label: string;
  models: LlmCatalogModel[];
  has_llm: boolean;
};

/** 对话模型下拉：仅展示用户新增的接入，不含环境变量内置条目 */
export function listPreferenceChatModels(catalog: LlmCatalogLike | null | undefined): LlmCatalogModel[] {
  if (!catalog?.has_llm) return [];
  return catalog.models.filter((m) => m.model_family === "custom" || m.id.startsWith("conn:"));
}

export function formatPreferenceModelDisplay(m: LlmCatalogModel): string {
  const name = (m.connection_name || "").trim();
  const mid = (m.model_id || "").trim();
  if (name && mid) return `${name} · ${mid}`;
  if (name) return name;
  if (mid) return mid;
  return m.label;
}

export function resolveChatModelPreference(catalog: LlmCatalogLike | null | undefined, pref: string): string {
  if (!catalog) return pref?.trim() || "auto";
  const ids = new Set([catalog.auto_id, ...listPreferenceChatModels(catalog).map((m) => m.id)]);
  const trimmed = pref?.trim() || "auto";
  return ids.has(trimmed) ? trimmed : catalog.auto_id;
}

export function chatModelForAsk(pref: string): string | null {
  const trimmed = pref?.trim();
  if (!trimmed || trimmed === "auto") return null;
  return trimmed;
}
