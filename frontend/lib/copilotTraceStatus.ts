import type { TraceSubCheckpoint } from "./copilotTraceMarkdown";

/**
 * 检查点状态（仅用于配色/图标推断；界面以颜色+图形表达，中文标签仅作无障碍备用）
 */
export type TraceCheckpointStatus = "verified" | "context_missing" | "inferred_ok" | "inferred_review" | "skipped" | "issue";

/** 屏幕阅读器用短标签（不在主界面展示） */
const LABEL: Record<TraceCheckpointStatus, string> = {
  verified: "已确认",
  context_missing: "缺上下文",
  inferred_ok: "推断",
  inferred_review: "推断待核",
  skipped: "已跳过",
  issue: "异常"
};

/** 左侧色条（高饱和，便于扫读） */
const STRIP: Record<TraceCheckpointStatus, string> = {
  verified: "bg-emerald-500 shadow-[0_0_0_1px_rgba(16,185,129,0.35)] dark:bg-emerald-400",
  context_missing: "bg-rose-500 shadow-[0_0_0_1px_rgba(244,63,94,0.35)] dark:bg-rose-400",
  inferred_ok: "bg-indigo-500 shadow-[0_0_0_1px_rgba(99,102,241,0.35)] dark:bg-indigo-400",
  inferred_review: "bg-amber-500 shadow-[0_0_0_1px_rgba(245,158,11,0.4)] dark:bg-amber-400",
  skipped: "bg-neutral-400 shadow-[0_0_0_1px_rgba(163,163,163,0.45)] dark:bg-neutral-500",
  issue: "bg-red-600 shadow-[0_0_0_1px_rgba(220,38,38,0.35)] dark:bg-red-500"
};

/** Lucide 图标描边/填充色，与色条同系 */
const ICON: Record<TraceCheckpointStatus, string> = {
  verified: "text-emerald-600 dark:text-emerald-400",
  context_missing: "text-rose-600 dark:text-rose-400",
  inferred_ok: "text-indigo-600 dark:text-indigo-400",
  inferred_review: "text-amber-600 dark:text-amber-400",
  skipped: "text-neutral-500 dark:text-neutral-400",
  issue: "text-red-600 dark:text-red-400"
};

export function traceCheckpointStatusLabel(s: TraceCheckpointStatus): string {
  return LABEL[s];
}

export function traceCheckpointStripClass(s: TraceCheckpointStatus): string {
  return STRIP[s];
}

export function traceCheckpointIconClass(s: TraceCheckpointStatus): string {
  return ICON[s];
}

export function inferTraceCheckpointStatus(
  stepId: string,
  sub: Pick<TraceSubCheckpoint, "body" | "sql" | "sqlCaption">
): TraceCheckpointStatus {
  const t = [sub.body, sub.sqlCaption, sub.sql || ""].join("\n").trim();
  const sqlTrim = (sub.sql || "").trim();

  if (stepId === "reasoning_gq") {
    if (/不进行单表/.test(t)) return "verified";
    return "inferred_ok";
  }

  if (stepId === "reasoning_1" && /用户问题摘要|判定为|意图说明/.test(t)) return "verified";

  if (stepId === "reasoning_3") {
    if (/\[\[trust:review\]\]/.test(t)) return "inferred_review";
    if (/\[\[trust:high\]\]/.test(t)) return "verified";
    if (/\[\[trust:low\]\]/.test(t)) return "context_missing";
    if (/\[\[trust:medium-high\]\]|\[\[trust:medium\]\]/.test(t)) return "inferred_ok";
  }

  if (
    stepId === "reasoning_7" &&
    (/结果集：\s*0\s*行|返回\s*0\s*行|执行状态：失败/.test(t))
  ) {
    return "issue";
  }

  if (stepId === "reasoning_2" && /约\s*0\s*(字|条)/.test(t)) return "context_missing";

  if (sqlTrim && /（清洗后暂无可执行 SQL）|暂无可执行 SQL/i.test(sqlTrim)) return "context_missing";

  const hardIssue =
    /失败|错误|AST\s*未通过|安全校验未通过|未找到可用数据源|SQL\s*安全校验未通过|执行失败|校验未通过/i;
  if (hardIssue.test(t)) return "issue";

  const skipped =
    /跳过数据源|未进行\s*AST|跳过\s*AST|无可执行语句|未配置数据源，跳过|跳过与下发/i.test(t) ||
    (/跳过/.test(t) && !/已通过|准备向数据源下发|成功[:：]/i.test(t));
  if (skipped) return "skipped";

  const missing =
    /库中未找到该\s*table_id|库中未找到|未找到该\s*table_id|未找到对应|无法解析为有效表|无有效\s*SQL|未生成\s*SQL|（空）|（模型未给出说明）|元数据结论：库中未找到/i;
  if (missing.test(t)) return "context_missing";

  const reviewRe =
    /未稳定对齐|候选表|在候选表之间|回退|最近表|容错说明|与上文|不一致|多为「|推理策略：|执行绑定：|将绑定到已配置的数据源|请求参数：未(在请求中)?携带/i;
  if (reviewRe.test(t)) return "inferred_review";

  const verifiedStrong =
    /请求参数：携带\s*table_id|元数据命中：|已成功|成功[:：]|已通过|准备向数据源下发|返回\s*[1-9]\d*\s*行|返回\s*\d+\s*行、\s*[1-9]|主上下文策略：|模型约束：|已加载：|^业务\/知识库约|^相似历史问法|^表与数据源说明|^列语义 Schema|^数据源：|^连接类型：|^解析出的 SQL 方言|^库\/命名空间：/i;
  if (verifiedStrong.test(t) && !reviewRe.test(t)) return "verified";

  if (stepId === "reasoning_4") {
    if (sqlTrim.length > 12 && !/（清洗后暂无可执行/i.test(sqlTrim)) return "inferred_ok";
    if (sub.body?.trim()) return "inferred_ok";
  }

  const inferredSoft =
    /自动对齐|对齐依据|对齐结果|示例写入绑定|绑定物理表|Schema\s*策略|【判定与取数逻辑】|【SQL/i;
  if (inferredSoft.test(t)) return "inferred_ok";

  if (/命中|已通过|准备向|成功|返回\s*\d+\s*行/.test(t)) return "verified";

  return "inferred_ok";
}

export function annotateSubCheckpointsWithStatus(
  stepId: string,
  subs: TraceSubCheckpoint[]
): Array<TraceSubCheckpoint & { status: TraceCheckpointStatus }> {
  return subs.map((sub) => ({
    ...sub,
    status: inferTraceCheckpointStatus(stepId, sub)
  }));
}
