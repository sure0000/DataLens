export type TrustUiCode = "high" | "medium-high" | "medium" | "low" | "review";

const LINE_RE =
  /^(\「[^」]+\」|（[^）]+）)\s*\[\[trust:(high|medium-high|medium|low|review)\]\]\s*角色：(.+?)\s*判断依据：(.*)$/;

export function tryParseReasoning3Line(line: string): null | {
  tableToken: string;
  trust: TrustUiCode;
  role: string;
  basisRaw: string;
} {
  const t = line.trim();
  const m = t.match(LINE_RE);
  if (!m) return null;
  return {
    tableToken: m[1].trim(),
    trust: m[2] as TrustUiCode,
    role: m[3].trim(),
    basisRaw: (m[4] || "").trim()
  };
}

const TRUST_LABEL: Record<TrustUiCode, string> = {
  high: "高",
  "medium-high": "中高",
  medium: "中",
  low: "低",
  review: "待核对"
};

/** 导出 Markdown 等场景：去掉机器标记，‖ 换行，可信度恢复为可读文字 */
export function stripReasoning3MachineMarkersForPlainText(line: string): string {
  const p = tryParseReasoning3Line(line);
  if (!p) return line;
  const basis = p.basisRaw.split("‖").join("\n");
  return `${p.tableToken}　可信度：${TRUST_LABEL[p.trust]}　角色：${p.role}\n判断依据：\n${basis}`;
}
