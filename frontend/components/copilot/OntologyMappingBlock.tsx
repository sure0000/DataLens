"use client";

import { useState } from "react";
import type { OntologyMapping } from "../../lib/chatSessions";

const KIND_LABEL: Record<string, string> = {
  metric: "指标",
  term: "术语",
  concept: "概念",
  table: "物理表",
};

const DEFAULT_VISIBLE = 5;

type Props = {
  mapping: OntologyMapping;
  /** 若 API 未带回 question，用对话中的用户原问兜底 */
  fallbackQuestion?: string;
};

export default function OntologyMappingBlock({ mapping, fallbackQuestion }: Props) {
  const [showAll, setShowAll] = useState(false);

  if (mapping.skipped || (!mapping.summary?.trim() && !mapping.mappings?.length)) {
    return null;
  }

  const question = (mapping.question || fallbackQuestion || "").trim();
  const allMappings = mapping.mappings || [];
  const mappings = showAll ? allMappings : allMappings.slice(0, DEFAULT_VISIBLE);
  const hiddenCount = allMappings.length - DEFAULT_VISIBLE;
  const matched = mapping.matched;

  return (
    <section
      className={`mb-3 rounded-lg border px-3 py-2.5 text-xs leading-relaxed ${
        matched
          ? "border-app-activeBorder/60 bg-app-activeBg/30"
          : "border-amber-500/40 bg-amber-500/5"
      }`}
      aria-label="问题到本体知识的映射"
    >
      <h4 className="text-[13px] font-semibold text-app-primary">问题 → 本体知识映射</h4>

      {question ? (
        <p className="mt-2 text-app-secondary">
          <span className="font-medium text-app-primary">您的问题：</span>
          {question}
        </p>
      ) : null}

      {matched && mappings.length > 0 ? (
        <div className="mt-2">
          <p className="font-medium text-app-primary">映射关系</p>
          <p className="mt-0.5 text-app-muted">下列说明描述问题语义如何对应到知识库中已建模的术语、指标与物理表。</p>
          <ol className="mt-2 list-decimal space-y-1.5 pl-4 text-app-secondary">
            {mappings.map((row, idx) => (
              <li key={`${row.target_label}-${idx}`}>
                <p>{row.description || formatMappingFallback(row)}</p>
              </li>
            ))}
          </ol>
          {hiddenCount > 0 && !showAll ? (
            <button
              type="button"
              className="mt-1 text-xs text-app-primary underline hover:opacity-80"
              onClick={() => setShowAll(true)}
            >
              展开全部 {allMappings.length} 条映射
            </button>
          ) : null}
          {showAll && allMappings.length > DEFAULT_VISIBLE ? (
            <button
              type="button"
              className="mt-1 text-xs text-app-primary underline hover:opacity-80"
              onClick={() => setShowAll(false)}
            >
              收起
            </button>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-app-secondary">
          <span className="font-medium text-app-primary">映射结果：</span>
          未在本体知识库中找到与问题语义匹配的术语、指标或物理表。请先在知识库完成语义建模，或在提问中使用已建模的资产名称。
        </p>
      )}
    </section>
  );
}

function formatMappingFallback(row: {
  target_kind?: string;
  target_label?: string;
  target_definition?: string;
  physical_tables?: string;
}): string {
  const kind = KIND_LABEL[row.target_kind || ""] || "概念";
  const label = row.target_label || "—";
  let s = `本体${kind}「${label}」`;
  if (row.target_definition) {
    s += `：${row.target_definition}`;
  }
  if (row.physical_tables) {
    s += ` → ${row.physical_tables}`;
  }
  return s;
}
