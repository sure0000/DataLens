"use client";

import { memo, useMemo } from "react";

/**
 * 轻量「类 ChatGPT」正文：段落、**粗体**、`行内代码`、无序列表；流式过程中也可安全渲染（不完整语法时降级为纯文本）。
 */
function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatInline(raw: string): string {
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

type Props = {
  text: string;
  className?: string;
};

function ChatGptStyleBody({ text, className = "" }: Props) {
  const html = useMemo(() => {
    const t = (text || "").trim();
    if (!t) return "";
    const blocks = t.split(/\n\n+/);
    return blocks.map((b) => paragraphToHtml(b.trim())).join("");
  }, [text]);

  if (!html) return null;

  return (
    <div
      className={`copilot-md max-w-none text-[15px] text-[#1e1e1e] dark:text-neutral-100 ${className}`}
      // eslint-disable-next-line react/no-danger -- 受控转义 + 无用户 HTML 输入
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default memo(ChatGptStyleBody);
