"use client";

import { Fragment } from "react";
import type { ChunkRow, DocRow, Entry } from "./types";
import { docStatusChip } from "./utils";

type UnifiedItem = { kind: "doc"; data: DocRow } | { kind: "entry"; data: Entry };

interface DocumentTableProps {
  items: UnifiedItem[];
  selectedIds: Set<string>;
  onToggleSelect: (kind: "doc" | "entry", id: number) => void;
  onSelectAll: (checked: boolean) => void;
  allSelected: boolean;
  onViewEntry: (entry: Entry) => void;
  onDeleteDoc: (doc: DocRow) => void;
  onDeleteEntry: (entry: Entry) => void;
  onRetryDoc: (docId: number) => void;
  onViewChunks: (docId: number) => void;
  expandedDocId: number | null;
  chunks: ChunkRow[];
  chunksLoading: boolean;
  selectedDocId: number | null;
}

export type { UnifiedItem };

export default function DocumentTable({
  items,
  selectedIds,
  onToggleSelect,
  onSelectAll,
  allSelected,
  onViewEntry,
  onDeleteDoc,
  onDeleteEntry,
  onRetryDoc,
  onViewChunks,
  expandedDocId,
  chunks,
  chunksLoading,
  selectedDocId,
}: DocumentTableProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-app-border bg-white shadow-sm">
      <table className="app-table">
        <thead>
          <tr>
            <th className="w-10 px-3 py-2.5">
              <input
                type="checkbox"
                className="accent-indigo-500"
                checked={allSelected}
                onChange={() => onSelectAll(!allSelected)}
              />
            </th>
            <th className="px-3 py-2.5">标题</th>
            <th className="w-44 px-3 py-2.5">创建时间</th>
            <th className="w-52 px-3 py-2.5">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const key = item.kind === "doc" ? `doc-${item.data.id}` : `entry-${item.data.id}`;
            const isSelected = selectedIds.has(key);

            if (item.kind === "doc") {
              const doc = item.data;
              const chip = docStatusChip(doc.status);
              const isExpanded = expandedDocId === doc.id;
              return (
                <Fragment key={key}>
                  <tr
                    className={`transition-colors ${isSelected ? "bg-indigo-50/70 ring-1 ring-inset ring-indigo-200" : "hover:bg-app-hover"}`}
                  >
                    <td className="px-3 py-2.5">
                      <input
                        type="checkbox"
                        className="accent-indigo-500"
                        checked={isSelected}
                        onChange={() => onToggleSelect("doc", doc.id)}
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <div>
                        <p className="text-sm font-medium text-app-primary truncate" title={doc.title}>
                          {doc.title}
                        </p>
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                          <span className="text-xs text-app-muted">
                            {doc.source_meta?.label || doc.source_type}
                          </span>
                          {doc.char_count != null && (
                            <span className="text-xs text-app-muted">
                              {doc.char_count.toLocaleString()} 字符
                            </span>
                          )}
                          <span
                            className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${chip.className}`}
                          >
                            {chip.text}
                          </span>
                          {doc.status === "failed" && (
                            <button
                              className="app-button text-xs leading-none"
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onRetryDoc(doc.id);
                              }}
                            >
                              重试
                            </button>
                          )}
                        </div>
                        {doc.error_message && (
                          <p className="text-xs text-rose-600 mt-0.5 truncate" title={doc.error_message}>
                            {doc.error_message}
                          </p>
                        )}
                        {doc.status === "indexed" && Object.keys(doc.stage_timings ?? {}).length > 0 && (
                          <p className="text-[11px] text-app-muted mt-0.5">
                            {Object.entries(doc.stage_timings)
                              .map(([k, v]) => `${k}: ${v}ms`)
                              .join(" · ")}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-app-muted whitespace-nowrap align-top">
                      {new Date(doc.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5 align-top">
                      <div className="flex items-center gap-1.5">
                        {doc.status === "indexed" && (
                          <button
                            className="app-button-secondary text-xs"
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onViewChunks(doc.id);
                            }}
                          >
                            {isExpanded ? "收起分块" : "查看分块"}
                          </button>
                        )}
                        <button
                          className="app-button-danger text-xs"
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteDoc(doc);
                          }}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td colSpan={4} className="px-4 pb-3 pt-2 border-b border-app-border">
                        <div className="space-y-2 max-h-80 overflow-y-auto">
                          {chunksLoading && selectedDocId === doc.id && (
                            <p className="text-sm text-app-muted">加载中…</p>
                          )}
                          {!chunksLoading && chunks.length === 0 && (
                            <p className="text-sm text-app-muted">该文档暂无分块数据。</p>
                          )}
                          {chunks.map((c) => (
                            <div
                              key={c.id}
                              className="rounded-lg border border-app-border bg-white p-3"
                            >
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <span className="text-xs text-app-muted">
                                  块 #{c.chunk_index + 1}
                                </span>
                                {c.quality_score != null && (
                                  <span
                                    className={`text-[11px] font-medium ${
                                      c.quality_score >= 0.7
                                        ? "text-emerald-600"
                                        : c.quality_score >= 0.4
                                        ? "text-amber-600"
                                        : "text-rose-500"
                                    }`}
                                  >
                                    质量 {c.quality_score.toFixed(2)}
                                  </span>
                                )}
                              </div>
                              <pre className="whitespace-pre-wrap break-words text-xs text-app-secondary">
                                {c.content}
                              </pre>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            } else {
              const entry = item.data;
              const label = entry.source_meta?.label || entry.source_meta?.kind || "API";
              return (
                <tr
                  key={key}
                  id={key}
                  className={`transition-colors ${isSelected ? "bg-indigo-50/70 ring-1 ring-inset ring-indigo-200" : "hover:bg-app-hover"}`}
                >
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      className="accent-indigo-500"
                      checked={isSelected}
                      onChange={() => onToggleSelect("entry", entry.id)}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <div>
                      <p className="text-sm font-medium text-app-primary truncate" title={entry.title}>
                        {entry.title}
                      </p>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                        <span className="text-xs text-app-muted">{label}</span>
                        {entry.source_url && (
                          <a
                            className="app-link text-xs"
                            href={entry.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            源链接
                          </a>
                        )}
                      </div>
                      {entry.summary && (
                        <p className="text-xs text-app-muted mt-0.5 line-clamp-2" title={entry.summary}>
                          {entry.summary}
                        </p>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-app-muted whitespace-nowrap align-top">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <div className="flex items-center gap-1.5">
                      <button
                        className="app-button-secondary text-xs"
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onViewEntry(entry);
                        }}
                      >
                        查看
                      </button>
                      <button
                        className="app-button-danger text-xs"
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteEntry(entry);
                        }}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              );
            }
          })}
        </tbody>
      </table>
    </div>
  );
}
