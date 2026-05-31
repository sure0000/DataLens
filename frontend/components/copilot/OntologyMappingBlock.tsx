"use client";

import { useState } from "react";
import type { OntologyMapping } from "../../lib/chatSessions";

const KIND_LABEL: Record<string, string> = {
  metric: "指标",
  term: "术语",
  concept: "概念",
  table: "物理表",
};

const MATCH_TYPE_LABEL: Record<string, { text: string; className: string }> = {
  exact: { text: "字面命中", className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" },
  semantic: { text: "语义推断", className: "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300" },
};

const KIND_SQL_HINT: Record<string, string> = {
  metric: "通常对应 SELECT 聚合（SUM/AVG/COUNT）与 GROUP BY",
  term: "通常对应 WHERE 过滤、JOIN 条件或 CASE WHEN 分类",
  concept: "可用于表选择或维度分组",
  table: "作为 FROM / JOIN 主表或维表",
};

const DEFAULT_VISIBLE = 5;

type Props = {
  mapping: OntologyMapping;
  /** 若 API 未带回 question，用对话中的用户原问兜底 */
  fallbackQuestion?: string;
  /** 嵌入 SqlDerivationPanel 时使用，去掉外层卡片样式 */
  embedded?: boolean;
};

export default function OntologyMappingBlock({ mapping, fallbackQuestion, embedded = false }: Props) {
  const [showAll, setShowAll] = useState(false);

  if (mapping.skipped || (!mapping.summary?.trim() && !mapping.mappings?.length)) {
    return null;
  }

  const question = (mapping.question || fallbackQuestion || "").trim();
  const allMappings = mapping.mappings || [];
  const mappings = showAll ? allMappings : allMappings.slice(0, DEFAULT_VISIBLE);
  const hiddenCount = allMappings.length - DEFAULT_VISIBLE;
  const matched = mapping.matched;

  const shellCls = embedded
    ? ""
    : `mb-3 rounded-lg border px-3 py-2.5 text-xs leading-relaxed ${
        matched
          ? "border-app-activeBorder/60 bg-app-activeBg/30"
          : "border-amber-500/40 bg-amber-500/5"
      }`;

  return (
    <section className={shellCls} aria-label="问题到本体知识的映射">
      {!embedded ? (
        <h4 className="text-[13px] font-semibold text-app-primary">问题 → 本体知识映射</h4>
      ) : null}

      {question && !embedded ? (
        <p className="mt-2 text-app-secondary">
          <span className="font-medium text-app-primary">您的问题：</span>
          {question}
        </p>
      ) : null}

      {matched && mappings.length > 0 ? (
        <div className={embedded ? "" : "mt-2"}>
          {!embedded ? (
            <>
              <p className="font-medium text-app-primary">映射关系</p>
              <p className="mt-0.5 text-app-muted">下列说明描述问题语义如何对应到知识库中已建模的术语、指标与物理表。</p>
            </>
          ) : null}
          <ol className={`list-decimal space-y-2 pl-4 text-app-secondary ${embedded ? "" : "mt-2"}`}>
            {mappings.map((row, idx) => (
              <li key={`${row.target_label}-${idx}`}>
                <div className="flex flex-wrap items-center gap-1.5">
                  {row.match_type && MATCH_TYPE_LABEL[row.match_type] ? (
                    <span
                      className={`inline-flex rounded border px-1.5 py-0 text-[10px] font-medium ${MATCH_TYPE_LABEL[row.match_type].className}`}
                    >
                      {MATCH_TYPE_LABEL[row.match_type].text}
                    </span>
                  ) : null}
                  {row.target_kind && KIND_LABEL[row.target_kind] ? (
                    <span className="text-[10px] text-app-muted">{KIND_LABEL[row.target_kind]}</span>
                  ) : null}
                </div>
                <p className="mt-0.5">{row.description || formatMappingFallback(row)}</p>
                {row.target_definition ? (
                  <p className="mt-0.5 text-[11px] text-app-muted">
                    <span className="font-medium text-app-secondary">口径：</span>
                    {truncateDef(row.target_definition)}
                  </p>
                ) : null}
                {row.physical_tables ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {row.physical_tables.split(/[、,]/).map((t) => t.trim()).filter(Boolean).map((table) => (
                      <span
                        key={`${row.target_label}-${table}`}
                        className="inline-flex rounded-md border border-app-border bg-app-hover px-1.5 py-0.5 font-mono text-[10px] text-app-primary"
                      >
                        {table}
                      </span>
                    ))}
                  </div>
                ) : null}
                {row.target_kind && KIND_SQL_HINT[row.target_kind] ? (
                  <p className="mt-0.5 text-[10px] italic text-app-muted">{KIND_SQL_HINT[row.target_kind]}</p>
                ) : null}
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
        <p className={`text-app-secondary ${embedded ? "" : "mt-2"}`}>
          <span className="font-medium text-app-primary">映射结果：</span>
          未在本体知识库中找到与问题语义匹配的术语、指标或物理表。请先在知识库完成语义建模，或在提问中使用已建模的资产名称。
        </p>
      )}
    </section>
  );
}

function truncateDef(def: string, max = 120): string {
  const t = def.trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
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
    s += `：${truncateDef(row.target_definition, 80)}`;
  }
  if (row.physical_tables) {
    s += ` → ${row.physical_tables}`;
  }
  return s;
}
