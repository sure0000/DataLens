"use client";

import { useMemo, useState } from "react";

export type KnowledgeBasePickerOption = {
  id: number;
  name: string;
  description?: string;
};

type KnowledgeBasePickerProps = {
  options: KnowledgeBasePickerOption[];
  selectedIds: number[];
  mode: "single" | "multiple";
  loading?: boolean;
  emptyText?: string;
  searchPlaceholder?: string;
  className?: string;
  onChange: (nextIds: number[]) => void;
};

export default function KnowledgeBasePicker({
  options,
  selectedIds,
  mode,
  loading = false,
  emptyText = "暂无可选知识库",
  searchPlaceholder = "搜索知识库…",
  className = "",
  onChange,
}: KnowledgeBasePickerProps) {
  const [keyword, setKeyword] = useState("");

  const filtered = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    if (!q) return options;
    return options.filter((item) =>
      `${item.name} ${item.description ?? ""} ${item.id}`.toLowerCase().includes(q),
    );
  }, [keyword, options]);

  function toggle(id: number) {
    if (mode === "single") {
      onChange([id]);
      return;
    }
    const has = selectedIds.includes(id);
    if (has) {
      onChange(selectedIds.filter((item) => item !== id));
      return;
    }
    onChange([...selectedIds, id]);
  }

  return (
    <div className={className}>
      <input
        type="search"
        className="app-input mb-2 w-full"
        placeholder={searchPlaceholder}
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        disabled={loading || options.length === 0}
      />
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((idx) => (
            <div key={idx} className="h-12 animate-pulse rounded-lg bg-app-hover" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <p className="py-3 text-sm text-app-muted">{emptyText}</p>
      ) : (
        <ul className="max-h-[56vh] space-y-2 overflow-y-auto">
          {filtered.map((kb) => {
            const checked = selectedIds.includes(kb.id);
            return (
              <li key={kb.id}>
                <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-app-border px-3 py-2 text-sm hover:bg-app-hover">
                  <input
                    type={mode === "single" ? "radio" : "checkbox"}
                    name={mode === "single" ? "knowledge-base-single" : undefined}
                    className="mt-0.5"
                    checked={checked}
                    onChange={() => toggle(kb.id)}
                  />
                  <span className="min-w-0">
                    <span className="block text-app-primary">{kb.name}</span>
                    {kb.description ? (
                      <span className="mt-0.5 block text-[11px] text-app-muted line-clamp-2">
                        {kb.description}
                      </span>
                    ) : null}
                    <span className="mt-0.5 block text-[10px] text-app-muted">ID {kb.id}</span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

