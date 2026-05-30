"use client";

import { useEffect, useMemo, useState } from "react";
import {
  formatPreferenceModelDisplay,
  listPreferenceChatModels,
  resolveChatModelPreference,
  type LlmCatalogLike,
  type LlmCatalogModel,
} from "../../lib/llmPreference";
import { readUserPreferences, writeUserPreferences } from "../../lib/userPreferences";

function IconSpark({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M12 2l1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5z" strokeLinejoin="round" />
      <circle cx="6" cy="19" r="2.2" />
    </svg>
  );
}

function selectedModelLine(catalog: LlmCatalogLike, chatModel: string): string {
  if (chatModel === catalog.auto_id) {
    return `自动 · ${catalog.auto_label}`;
  }
  const m = catalog.models.find((x) => x.id === chatModel);
  return m ? formatPreferenceModelDisplay(m) : chatModel;
}

interface ChatModelTabProps {
  loading: boolean;
  catalog: LlmCatalogLike | null;
  hasConnections: boolean;
  onAdd: () => void;
}

export default function ChatModelTab({ loading, catalog, hasConnections, onAdd }: ChatModelTabProps) {
  const [chatModel, setChatModel] = useState("auto");
  const preferenceChatModels = listPreferenceChatModels(catalog);

  const chatOrphanOption = useMemo(() => {
    if (!catalog || chatModel === catalog.auto_id) return false;
    return !preferenceChatModels.some((m) => m.id === chatModel);
  }, [catalog, chatModel, preferenceChatModels]);

  useEffect(() => {
    setChatModel(resolveChatModelPreference(catalog, readUserPreferences().chatModel));
  }, [catalog]);

  useEffect(() => {
    const onPrefs = () => {
      setChatModel(resolveChatModelPreference(catalog, readUserPreferences().chatModel));
    };
    window.addEventListener("datalens-user-prefs-updated", onPrefs);
    return () => window.removeEventListener("datalens-user-prefs-updated", onPrefs);
  }, [catalog]);

  function onChatModelChange(value: string) {
    setChatModel(value);
    writeUserPreferences({ chatModel: value });
  }

  return (
    <section className="app-card rounded-2xl p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
          <IconSpark />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="app-card-title text-base">Copilot 对话模型</h2>
          <p className="mt-1 text-[11px] text-app-muted">
            配置助手对话时默认使用的大模型。选择「自动」时由系统按语义策略与路由选择。
          </p>
        </div>
      </div>

      {loading ? (
        <div className="mt-6 flex items-center gap-2 text-sm text-app-muted" role="status">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-app-border border-t-app-primary" />
          加载中
        </div>
      ) : !hasConnections ? (
        <div className="mt-6 flex flex-col items-center gap-4 rounded-2xl border border-dashed border-app-border bg-app-hover/30 px-4 py-10">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-app-border bg-app-surfaceMuted text-app-secondary">
            <IconSpark className="h-7 w-7" />
          </div>
          <p className="text-center text-sm text-app-secondary">尚未配置可用大模型，请先在「模型与连接」中新增接入。</p>
          <button type="button" className="app-button" onClick={onAdd}>
            新增接入
          </button>
        </div>
      ) : !catalog ? (
        <p className="mt-6 text-sm text-app-muted">模型目录加载中…</p>
      ) : (
        <div className="mt-5 space-y-4">
          <label className="flex max-w-md flex-col gap-1.5 text-xs font-medium text-app-secondary">
            默认对话模型
            <select
              className="app-input text-sm"
              value={chatModel}
              onChange={(e) => onChatModelChange(e.target.value)}
            >
              <option value={catalog.auto_id}>自动</option>
              {chatOrphanOption ? (
                <option value={chatModel} disabled>
                  （已不在列表）{selectedModelLine(catalog, chatModel)}
                </option>
              ) : null}
              {preferenceChatModels.map((m: LlmCatalogModel) => (
                <option key={m.id} value={m.id}>
                  {formatPreferenceModelDisplay(m)}
                </option>
              ))}
            </select>
          </label>
          <div className="rounded-xl border border-app-border bg-app-hover/40 px-3 py-3 text-sm">
            <p className="text-xs text-app-muted">当前生效</p>
            <p className="mt-1 font-medium text-app-primary">{selectedModelLine(catalog, chatModel)}</p>
          </div>
        </div>
      )}
    </section>
  );
}
