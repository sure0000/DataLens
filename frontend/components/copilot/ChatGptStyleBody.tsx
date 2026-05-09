"use client";

import { memo, useMemo } from "react";
import { highlightSqlKeywordsHtml } from "../SqlBlock";

/**
 * 轻量「类 ChatGPT」正文：段落、**粗体**、`行内代码`、无序列表、```sql … ``` 代码块；流式过程中也可安全渲染。
 */
function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatInline(raw: string) {
  let s = escapeHtml(raw);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(
    /`([^`]+)`/g,
    '<code style="background:rgba(0,0,0,.07);padding:1px 6px;border-radius:4px;font-size:.9em;font-family:ui-monospace,monospace">$1</code>'
  );
  return s;
}

function paragraphToHtml(block: string): string {
  const lines = block.replace(/\r/g, "").split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (/^[-*•]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
        items.push(`<li class="ml-4 list-disc pl-1">${formatInline(lines[i].trim().replace(/^[-*•]\s+/, ""))}</li>`);
        i += 1;
      }
      out.push(`<ul class="my-2 space-y-1">${items.join("")}</ul>`);
      continue;
    }
    if (trimmed) {
      out.push(`<p class="my-2 first:mt-0 last:mb-0 leading-7">${formatInline(trimmed)}</p>`);
    }
    i += 1;
  }
  return out.join("");
}

type FencedToken = { kind: "text"; body: string } | { kind: "code"; lang: string; body: string };

function splitFencedCodeBlocks(input: string): FencedToken[] {
  const out: FencedToken[] = [];
  let pos = 0;
  while (pos < input.length) {
    const start = input.indexOf("```", pos);
    if (start === -1) {
      if (pos < input.length) out.push({ kind: "text", body: input.slice(pos) });
      break;
    }
    if (start > pos) out.push({ kind: "text", body: input.slice(pos, start) });
    let i = start + 3;
    const nl = input.indexOf("\n", i);
    let lang = "";
    let codeStart = i;
    if (nl !== -1 && nl - i <= 24) {
      lang = input.slice(i, nl).trim().toLowerCase();
      codeStart = nl + 1;
    }
    const end = input.indexOf("```", codeStart);
    if (end === -1) {
      out.push({ kind: "text", body: input.slice(start) });
      break;
    }
    out.push({ kind: "code", lang: lang || "text", body: input.slice(codeStart, end) });
    pos = end + 3;
    if (input[pos] === "\n" || input[pos] === "\r") {
      if (input[pos] === "\r" && input[pos + 1] === "\n") pos += 2;
      else pos += 1;
    }
  }
  return out;
}

function textSegmentToHtml(segment: string): string {
  const t = segment.trim();
  if (!t) return "";
  return t
    .split(/\n\n+/)
    .map((b) => paragraphToHtml(b.trim()))
    .join("");
}

function codeBlockToHtml(lang: string, body: string): string {
  const raw = body.replace(/\r\n/g, "\n").trimEnd();
  if (!raw) return "";
  if (lang === "sql") {
    const inner = highlightSqlKeywordsHtml(raw);
    return `<pre class="sql-block my-3 overflow-x-auto rounded-lg p-3 text-xs leading-relaxed"><code>${inner}</code></pre>`;
  }
  return `<pre class="my-3 overflow-x-auto rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-xs leading-relaxed dark:border-neutral-700 dark:bg-neutral-900/80"><code>${escapeHtml(
    raw
  )}</code></pre>`;
}

function markdownDocumentToHtml(text: string): string {
  const t = (text || "").trim();
  if (!t) return "";
  const parts = splitFencedCodeBlocks(t);
  return parts
    .map((p) => {
      if (p.kind === "code") return codeBlockToHtml(p.lang, p.body);
      return textSegmentToHtml(p.body);
    })
    .join("");
}

type Props = {
  text: string;
  className?: string;
};

function ChatGptStyleBody({ text, className = "" }: Props) {
  const html = useMemo(() => markdownDocumentToHtml(text), [text]);

  if (!html) return null;

  return (
    <div
      className={`copilot-md max-w-none text-[15px] text-[#1e1e1e] dark:text-neutral-100 ${className}`}
      // eslint-disable-next-line react/no-danger -- 受控转义 + 代码块经 escape/highlightSql
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default memo(ChatGptStyleBody);
