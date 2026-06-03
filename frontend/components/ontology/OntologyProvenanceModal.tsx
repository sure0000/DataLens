"use client";

import { createPortal } from "react-dom";
import { Icon } from "../AppIcons";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import type { OntologyEntityOrigin, OntologyProvenance } from "../../lib/ontologyTypes";
import { shortenIri } from "../../lib/shortenIri";
import OntologyStatusBadge from "./OntologyStatusBadge";

export type ProvenanceColumnDef = {
  key: string;
  label: string;
  render?: (row: Record<string, string>) => string;
  wrap?: boolean;
};

export type ProvenanceRow = Record<string, string> & {
  origin?: OntologyEntityOrigin;
  status?: string;
  synonyms?: string[];
};

function cellValue(row: ProvenanceRow, col: ProvenanceColumnDef): string {
  if (col.render) return col.render(row);
  const v = row[col.key];
  return v?.trim() ? v : "—";
}

export function OriginBlock({ origin }: { origin: OntologyEntityOrigin }) {
  return (
    <div className="rounded-lg border border-app-border/60 px-3 py-2 text-xs">
      <p className="text-app-muted">来源知识库</p>
      <p className="font-medium text-app-primary">{origin.knowledge_base_name}</p>
      {origin.source_label ? (
        <>
          <p className="mt-2 text-app-muted">导入来源</p>
          <p className="text-app-secondary">{origin.source_label}</p>
        </>
      ) : null}
      {origin.source_type ? (
        <>
          <p className="mt-2 text-app-muted">来源类型</p>
          <p className="text-app-secondary">{origin.source_type}</p>
        </>
      ) : null}
      {origin.evidence_package_display_id ? (
        <>
          <p className="mt-2 text-app-muted">证据包</p>
          <p className="text-app-secondary">{origin.evidence_package_display_id}</p>
        </>
      ) : null}
    </div>
  );
}

export default function OntologyProvenanceModal({
  row,
  provenance,
  columns,
  onClose,
}: {
  row: ProvenanceRow;
  provenance: OntologyProvenance | null;
  columns: ProvenanceColumnDef[];
  onClose: () => void;
}) {
  useEscapeKey(onClose, true);

  const origin = row.origin;
  const title = row.label || shortenIri(row.s ?? "记录");
  const provenanceLoading = Boolean(row.s && origin?.knowledge_base_id && !provenance);

  const modal = (
    <div className="app-modal-backdrop app-modal-backdrop--front" role="presentation" onClick={onClose}>
      <div
        className="app-modal-surface flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden p-5 sm:p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="provenance-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-app-border pb-4">
          <div className="min-w-0">
            <p className="text-xs text-app-muted">语义资产详情</p>
            <h2 id="provenance-modal-title" className="mt-1 text-base font-semibold text-app-primary break-words">
              {title}
            </h2>
            {row.status ? (
              <div className="mt-2">
                <OntologyStatusBadge status={row.status} />
              </div>
            ) : null}
          </div>
          <button type="button" className="app-control-button shrink-0" onClick={onClose} aria-label="关闭">
            <Icon name="close" className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto text-sm">
          <section>
            <p className="text-xs font-medium text-app-muted">属性</p>
            <dl className="mt-2 divide-y divide-app-border rounded-lg border border-app-border">
              {columns.map((col) => {
                if (col.key === "status" && row.status) {
                  return (
                    <div key={col.key} className="flex gap-3 px-3 py-2 text-xs">
                      <dt className="w-24 shrink-0 text-app-muted">{col.label}</dt>
                      <dd className="min-w-0 flex-1 text-app-primary">
                        <OntologyStatusBadge status={row.status} />
                      </dd>
                    </div>
                  );
                }
                if (col.key === "synonyms") {
                  const syns: string[] = Array.isArray(row.synonyms)
                    ? (row.synonyms as unknown as string[]).filter((s) => typeof s === "string" && s.trim())
                    : [];
                  return (
                    <div key={col.key} className="flex gap-3 px-3 py-2 text-xs">
                      <dt className="w-24 shrink-0 text-app-muted">{col.label}</dt>
                      <dd className="min-w-0 flex-1 text-app-primary">
                        {syns.length > 0 ? (
                          <span className="flex flex-wrap gap-1">
                            {syns.map((s, i) => (
                              <span key={i} className="inline-flex items-center rounded border border-app-border bg-app-surfaceMuted px-1.5 py-0.5 text-xs text-app-secondary">
                                {s}
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="text-app-muted">—</span>
                        )}
                      </dd>
                    </div>
                  );
                }
                const value = cellValue(row, col);
                return (
                  <div key={col.key} className="flex gap-3 px-3 py-2 text-xs">
                    <dt className="w-24 shrink-0 text-app-muted">{col.label}</dt>
                    <dd className="min-w-0 flex-1 break-words text-app-primary">{value}</dd>
                  </div>
                );
              })}
            </dl>
          </section>

          <section>
            <p className="text-xs font-medium text-app-muted">来源</p>
            {origin ? (
              <div className="mt-2">
                <OriginBlock origin={origin} />
              </div>
            ) : (
              <p className="mt-2 text-xs text-app-muted">暂无来源信息</p>
            )}
          </section>

          {row.s ? (
            <section>
              <p className="text-xs font-medium text-app-muted">IRI</p>
              <p className="mt-2 break-all rounded-lg border border-app-border bg-app-surfaceMuted px-3 py-2 font-mono text-xs text-app-secondary">
                {shortenIri(row.s)}
              </p>
            </section>
          ) : null}

          <section>
            <p className="text-xs font-medium text-app-muted">溯源链</p>
            {provenance?.has_provenance ? (
              <ul className="mt-2 space-y-2">
                {provenance.documents?.map((d) => (
                  <li
                    key={d.id}
                    className="rounded-lg border border-app-border px-3 py-2 text-xs text-app-secondary"
                  >
                    <span className="text-app-muted">文档 · </span>
                    {d.title}
                  </li>
                ))}
                {provenance.evidence_packages?.map((p) => (
                  <li
                    key={p.display_id}
                    className="rounded-lg border border-app-border px-3 py-2 text-xs text-app-secondary"
                  >
                    <span className="text-app-muted">证据包 {p.display_id} · </span>
                    {p.title}
                  </li>
                ))}
                {provenance.chunks?.map((c) => (
                  <li
                    key={c.iri}
                    className="rounded-lg border border-app-border px-3 py-2 text-xs text-app-secondary"
                  >
                    <span className="font-mono text-app-muted">{shortenIri(c.iri)}</span>
                    {c.content_preview
                      ? `：${c.content_preview.slice(0, 160)}${c.content_preview.length > 160 ? "…" : ""}`
                      : ""}
                  </li>
                ))}
              </ul>
            ) : provenanceLoading ? (
              <p className="mt-2 text-xs text-app-muted">加载溯源链…</p>
            ) : (
              <p className="mt-2 text-xs text-app-muted">暂无溯源链记录</p>
            )}
          </section>
        </div>

        <div className="mt-4 shrink-0 border-t border-app-border pt-4">
          <button type="button" className="app-button-secondary w-full sm:ml-auto sm:w-auto" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(modal, document.body);
}
