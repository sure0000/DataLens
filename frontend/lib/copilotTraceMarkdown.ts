import type { PipelineTraceStep } from "./chatSessions";

/** 将 pipeline 步骤格式化为与回答一致的 Markdown 正文（段落 + 粗体标题） */
export function formatPipelineTraceForBodyMarkdown(
  steps: PipelineTraceStep[],
  sectionTitle: string = "推理过程"
): string {
  if (!steps.length) return "";
  const blocks: string[] = [`**${sectionTitle}**`];
  for (const s of steps) {
    const title = (s.label || "").trim() || "步骤";
    blocks.push(`**${title}**`);
    const d = (s.detail || "").trim();
    if (d) blocks.push(d);
  }
  return blocks.join("\n\n");
}
