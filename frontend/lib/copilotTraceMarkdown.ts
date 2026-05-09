import type { PipelineTraceStep } from "./chatSessions";
import { stripReasoning3MachineMarkersForPlainText, tryParseReasoning3Line } from "./traceReasoning3Parse";

/** 去掉「【判定与取数逻辑】」小节标题（及紧随换行），避免子检查点首条只显示该标题 */
export function stripReasoning4LogicBanner(text: string): string {
  let t = (text || "").trimStart();
  const re = /^\s*【判定与取数逻辑】\s*(?:\n+|$)/;
  while (re.test(t)) t = t.replace(re, "").trimStart();
  return t;
}

/** 去掉模型回答里追加的「自动修复说明」段落（历史消息兼容） */
export function stripAutoRepairExplanationNote(text: string): string {
  const t = (text || "").trimEnd();
  if (!t) return t;
  const markers = ["\n\n自动修复说明", "\n自动修复说明"];
  for (const m of markers) {
    const i = t.indexOf(m);
    if (i !== -1) return t.slice(0, i).trimEnd();
  }
  return t;
}

/** 单行或紧凑 SQL 的简单换行，便于阅读 */
export function layoutSqlSimple(sql: string): string {
  const t = sql.trim().replace(/\r\n/g, "\n");
  if (!t) return sql;
  const newlineCount = (t.match(/\n/g) || []).length;
  if (newlineCount >= 2) return t;
  return t
    .replace(/\s+(UNION ALL|UNION)\b/gi, "\n$1 ")
    .replace(/\s+(LEFT JOIN|RIGHT JOIN|INNER JOIN|CROSS JOIN|JOIN)\b/gi, "\n$1 ")
    .replace(/\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET)\b/gi, "\n$1 ")
    .trim();
}

/** UI 用：拆出正文与 SQL，便于检查点卡片内单独渲染代码块 */
export type TraceStepDisplayParts = {
  bodyText: string;
  sql: string | null;
  /** 与 detail 中一致的 SQL 小标题，导出 Markdown 时复用 */
  sqlMarker: string | null;
};

/** 单个大步骤（reasoning_n）内部的细粒度检查点 */
export type TraceSubCheckpoint = {
  /** 说明正文（多行可） */
  body: string;
  sql: string | null;
  /** 仅有 SQL 时的小标题（如【SQL（清洗后用于执行）】） */
  sqlCaption?: string | null;
};

/** 将「判定与取数逻辑」长段拆成多条，便于逐项标注状态 */
function splitReasoning4LogicChunks(body: string): string[] {
  const t = body.trim();
  if (!t) return [];
  const paras = t.split(/\n\n+/).map((x) => x.trim()).filter(Boolean);
  if (paras.length > 1) return paras;
  const single = paras[0] || t;
  const sents = single.split(/(?<=[。！？])\s+/).map((x) => x.trim()).filter(Boolean);
  if (sents.length > 1 && sents.every((s) => s.length < 900)) return sents;
  return [single];
}

function splitReasoning1Detail(d: string): TraceSubCheckpoint[] {
  const t = d.trim();
  const lines = t.split(/\n/).map((x) => x.trim()).filter(Boolean);
  if (lines.length > 1) return lines.map((body) => ({ body, sql: null }));
  const idx = t.indexOf("说明：");
  if (idx > 0) {
    const head = t.slice(0, idx).trim();
    const tail = t.slice(idx).trim();
    if (head && tail) return [{ body: head, sql: null }, { body: tail, sql: null }];
  }
  return [{ body: t, sql: null }];
}

/** 选表：一行多项时用分号再拆；兼容旧版超长单行 */
function splitReasoning3Detail(d: string): TraceSubCheckpoint[] {
  const lines = d.split(/\n/).map((x) => x.trim()).filter(Boolean);
  const out: TraceSubCheckpoint[] = [];
  for (const line of lines) {
    if (/；/.test(line) && line.length > 40) {
      const parts = line.split(/；\s*/).map((x) => x.trim()).filter(Boolean);
      if (parts.length > 1) {
        for (const p of parts) out.push({ body: p, sql: null });
        continue;
      }
    }
    out.push({ body: line, sql: null });
  }
  return out.length ? out : [{ body: d.trim(), sql: null }];
}

function splitReasoningGqDetail(d: string): TraceSubCheckpoint[] {
  const t = d.trim();
  if (t.includes("；")) {
    const parts = t.split(/；\s*/).map((x) => x.trim()).filter(Boolean);
    if (parts.length > 1) return parts.map((body) => ({ body, sql: null }));
  }
  const lines = t.split(/\n/).map((x) => x.trim()).filter(Boolean);
  if (lines.length > 1) return lines.map((body) => ({ body, sql: null }));
  return [{ body: t, sql: null }];
}

/** 按 `【…】` 小节、空行分段、单行拆行等规则，把一步 detail 拆成多条子检查点 */
export function splitTraceStepDetailIntoSubCheckpoints(s: PipelineTraceStep): TraceSubCheckpoint[] {
  const d = (s.detail || "").trim();
  if (!d) return [];

  if (s.id === "reasoning_4") {
    const p = parseTraceStepDetailForUi(s);
    const rows: TraceSubCheckpoint[] = [];
    const logicCore = stripReasoning4LogicBanner(p.bodyText.trim());
    if (logicCore.trim()) {
      for (const chunk of splitReasoning4LogicChunks(logicCore)) {
        const c = stripReasoning4LogicBanner(chunk.trim());
        if (c.trim()) rows.push({ body: c, sql: null });
      }
    }
    if (p.sql) rows.push({ body: "", sql: p.sql, sqlCaption: p.sqlMarker });
    return rows.length ? rows : [{ body: d, sql: null }];
  }

  if (s.id === "reasoning_2") {
    return splitReasoning2ContextDetail(d);
  }

  if (s.id === "reasoning_1") {
    return splitReasoning1Detail(d);
  }

  if (s.id === "reasoning_3") {
    return splitReasoning3Detail(d);
  }

  if (s.id === "reasoning_gq") {
    return splitReasoningGqDetail(d);
  }

  const byBook = splitDetailByChineseBookends(d);
  if (byBook !== null && byBook.length > 0) return byBook;

  const paras = d.split(/\n\n+/).map((x) => x.trim()).filter(Boolean);
  if (paras.length > 1) return paras.map((body) => ({ body, sql: null }));

  const single = paras[0] || d;
  const lines = single.split("\n").map((x) => x.trim()).filter(Boolean);
  if (lines.length > 1) {
    const maxLen = Math.max(...lines.map((l) => l.length));
    if (maxLen <= 800) return lines.map((body) => ({ body, sql: null }));
  }

  return [{ body: single.trim(), sql: null }];
}

/** 「确认上下文」：新数据一行一项；旧版单行「已加载：…；…」按分号拆成多条检查点 */
function splitReasoning2ContextDetail(d: string): TraceSubCheckpoint[] {
  const t = d.trim();
  const lines = t.split(/\n/).map((x) => x.trim()).filter(Boolean);
  if (lines.length > 1) {
    return lines.map((body) => ({ body, sql: null }));
  }

  if (t.startsWith("已加载：")) {
    const tail = t.slice("已加载：".length).trim();
    const parts = tail.split(/；\s*/).map((x) => x.trim()).filter(Boolean);
    if (parts.length > 1) {
      return parts.map((body) => ({ body: body.replace(/\s+/g, " ").trim(), sql: null }));
    }
  }

  return [{ body: t, sql: null }];
}

function splitDetailByChineseBookends(d: string): TraceSubCheckpoint[] | null {
  const re = /【[^】]+】/g;
  const hits: { idx: number; len: number; raw: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(d)) !== null) {
    hits.push({ idx: m.index, len: m[0].length, raw: m[0] });
  }
  if (hits.length === 0) return null;

  const out: TraceSubCheckpoint[] = [];
  const firstIdx = hits[0].idx;
  if (firstIdx > 0) {
    const prefix = d.slice(0, firstIdx).trim();
    if (prefix) out.push({ body: prefix, sql: null });
  }
  for (let i = 0; i < hits.length; i++) {
    const start = hits[i].idx + hits[i].len;
    const end = i + 1 < hits.length ? hits[i + 1].idx : d.length;
    const inner = d.slice(start, end).trim();
    const header = hits[i].raw;
    const body = inner ? `${header}\n${inner}` : header;
    out.push({ body, sql: null });
  }
  return out.length > 0 ? out : null;
}

export function parseTraceStepDetailForUi(s: PipelineTraceStep): TraceStepDisplayParts {
  const d = (s.detail || "").trim();
  if (!d) return { bodyText: "", sql: null, sqlMarker: null };
  if (s.id === "reasoning_4") {
    const markers = ["【SQL（清洗后用于执行）】", "【SQL】"];
    for (const marker of markers) {
      const idx = d.indexOf(marker);
      if (idx === -1) continue;
      const logic = stripAutoRepairExplanationNote(d.slice(0, idx).trimEnd());
      let sqlPart = d.slice(idx + marker.length).trim();
      sqlPart = layoutSqlSimple(sqlPart);
      if (!sqlPart) return { bodyText: d, sql: null, sqlMarker: null };
      return { bodyText: logic, sql: sqlPart, sqlMarker: marker };
    }
  }
  return { bodyText: d, sql: null, sqlMarker: null };
}

function formatStepDetailForBody(s: PipelineTraceStep): string {
  const d = (s.detail || "").trim();
  if (!d) return "";
  if (s.id === "reasoning_3") {
    return d
      .split("\n")
      .map((line) => {
        const t = line.trim();
        if (!t) return "";
        return tryParseReasoning3Line(t) ? stripReasoning3MachineMarkersForPlainText(t) : t;
      })
      .filter(Boolean)
      .join("\n\n");
  }
  const p = parseTraceStepDetailForUi(s);
  if (s.id === "reasoning_4" && p.sql && p.sqlMarker) {
    return `${stripReasoning4LogicBanner(p.bodyText)}\n\n${p.sqlMarker}\n\n\`\`\`sql\n${p.sql}\n\`\`\``;
  }
  if (s.id === "reasoning_4") return stripReasoning4LogicBanner(p.bodyText);
  return p.bodyText;
}

/** 将 pipeline 步骤格式化为与回答一致的 Markdown 正文（段落 + 粗体标题；第 4 步 SQL 用 ```sql 代码块） */
export function formatPipelineTraceForBodyMarkdown(
  steps: PipelineTraceStep[],
  sectionTitle: string = "推理过程"
): string {
  if (!steps.length) return "";
  const blocks: string[] = [`**${sectionTitle}**`];
  for (const s of steps) {
    const title = (s.label || "").trim() || "步骤";
    blocks.push(`**${title}**`);
    const formatted = formatStepDetailForBody(s);
    if (formatted) blocks.push(formatted);
  }
  return blocks.join("\n\n");
}
