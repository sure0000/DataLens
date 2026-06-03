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
