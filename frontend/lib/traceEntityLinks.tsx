"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { TraceEntityLink, TraceEntityLinkKind } from "./chatSessions";

const KINDS: TraceEntityLinkKind[] = ["table", "datasource", "database", "business_domain", "knowledge_base"];

export function parseTraceEntityLinks(raw: unknown): TraceEntityLink[] {
  if (!Array.isArray(raw)) return [];
  const out: TraceEntityLink[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const kind = o.kind;
    if (typeof kind !== "string" || !KINDS.includes(kind as TraceEntityLinkKind)) continue;
    const matchesRaw = o.matches;
    if (!Array.isArray(matchesRaw)) continue;
    const matches = matchesRaw.filter((m): m is string => typeof m === "string" && m.trim().length > 0);
    if (!matches.length) continue;
    const id = typeof o.id === "number" ? o.id : undefined;
    const datasource_id = typeof o.datasource_id === "number" ? o.datasource_id : undefined;
    const database_name = typeof o.database_name === "string" ? o.database_name : undefined;
    out.push({
      kind: kind as TraceEntityLinkKind,
      id,
      datasource_id,
      database_name,
      matches
    });
  }
  return out;
}

export function traceEntityLinkHref(link: TraceEntityLink): string {
  switch (link.kind) {
    case "table":
      return link.id != null ? `/table/${link.id}` : "#";
    case "datasource":
      return link.id != null ? `/datasources/${link.id}` : "#";
    case "database":
      if (link.datasource_id == null || !link.database_name) return "#";
      return `/datasources/${link.datasource_id}/database/${encodeURIComponent(link.database_name)}`;
    case "business_domain":
      return link.id != null ? `/business-domains/${link.id}` : "#";
    case "knowledge_base":
      return link.id != null ? `/knowledge-bases/${link.id}` : "#";
    default:
      return "#";
  }
}

type Hit = { start: number; end: number; href: string };

function collectHits(text: string, links: TraceEntityLink[]): Hit[] {
  const hits: Hit[] = [];
  for (const link of links) {
    const href = traceEntityLinkHref(link);
    if (href === "#") continue;
    const rawMatches = Array.isArray(link.matches) ? link.matches : [];
    for (const raw of rawMatches) {
      const m = (raw || "").trim();
      if (m.length < 2) continue;
      let from = 0;
      while (from < text.length) {
        const i = text.indexOf(m, from);
        if (i === -1) break;
        hits.push({ start: i, end: i + m.length, href });
        from = i + m.length;
      }
    }
  }
  hits.sort((a, b) => b.end - b.start - (a.end - a.start));
  const picked: Hit[] = [];
  for (const h of hits) {
    if (picked.some((p) => h.start < p.end && h.end > p.start)) continue;
    picked.push(h);
  }
  picked.sort((a, b) => a.start - b.start);
  return picked;
}

/** 推理 trace 内实体链接：仅用下划线与字重区分，避免背景/描边块在多链相邻时叠压 */
const traceEntityLinkCls =
  "app-link cursor-pointer font-semibold decoration-2 underline-offset-[3px] transition-colors " +
  "text-blue-700 hover:text-blue-900 dark:text-indigo-300 dark:hover:text-indigo-100";

/** 将 detail 中的可识别片段替换为站内详情链接 */
export function renderTraceDetailWithLinks(text: string, links: TraceEntityLink[] | undefined): ReactNode {
  const t = (text || "").trim();
  if (!t) return null;
  if (!links?.length) return t;
  const hits = collectHits(t, links);
  if (!hits.length) return t;
  const out: ReactNode[] = [];
  let cursor = 0;
  hits.forEach((h, idx) => {
    if (cursor < h.start) {
      out.push(t.slice(cursor, h.start));
    }
    const slice = t.slice(h.start, h.end);
    out.push(
      <Link
        key={`${h.start}-${h.end}-${idx}`}
        href={h.href}
        className={traceEntityLinkCls}
        title="打开详情页"
      >
        {slice}
      </Link>
    );
    cursor = h.end;
  });
  if (cursor < t.length) out.push(t.slice(cursor));
  return <>{out}</>;
}
