/**
 * 将 copilot pipeline_trace 步骤转为人类可读的"思考过程"叙述。
 *
 * 第一性原理：
 * - 用户需要知道"系统是怎么想的"，但不是调试级别的细节
 * - 思考过程 = 自然语言线性叙述，不是带状态图标的检查点列表
 * - 本体匹配按五层完整展示，有则列、无则告
 */

import type {
  OntologyMapping,
  OntologyMappingLink,
  PipelineTraceStep,
  TraceEntityLink,
} from "./chatSessions";

/* ── 类型 ────────────────────────────────────────────── */

export type NarrativeLine = {
  key: string;
  text: string;
  /** 可选的站内实体链接 */
  links?: TraceEntityLink[];
  /** 五层本体分解的子行（仅 ontology_match 步骤使用） */
  subLines?: NarrativeLine[];
};

/* ── 五层本体定义 ────────────────────────────────────── */

const ONTO_LAYERS = [
  { key: "vocabulary", label: "词汇层", kinds: ["term"] },
  { key: "rule", label: "规则层", kinds: ["metric", "rule"] },
  { key: "entity-concept", label: "实体概念层", kinds: ["concept", "entity_concept"] },
  { key: "dimension", label: "维度层", kinds: ["dimension"] },
  { key: "relation", label: "关系层", kinds: ["relation"] },
  { key: "attribute", label: "属性层", kinds: ["attribute"] },
] as const;

const KIND_TO_LAYER: Record<string, string> = {};
for (const layer of ONTO_LAYERS) {
  for (const kind of layer.kinds) {
    KIND_TO_LAYER[kind] = layer.key;
  }
}

/* ── 辅助函数 ────────────────────────────────────────── */

/** 剥离机器标记：[[trust:high]], [[trust:review]] 等 */
function stripMachineMarkers(text: string): string {
  return text
    .replace(/\[\[trust:[^\]]+\]\]/g, "")
    .replace(/【判定与取数逻辑】/g, "")
    .replace(/【SQL[^】]*】/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** 从 detail 文本取第一句有意义的内容 */
function extractSummary(detail: string | undefined, maxLen = 120): string {
  const t = stripMachineMarkers(detail || "").trim();
  if (!t) return "";
  // 按换行或句号取第一段
  const firstLine = t.split(/\n|。/)[0].trim();
  if (!firstLine) return "";
  return firstLine.length > maxLen
    ? firstLine.slice(0, maxLen) + "…"
    : firstLine;
}

/** 从 detail 文本取所有行（按换行分）并剥离机器标记 */
function extractLines(detail: string | undefined): string[] {
  return (detail || "")
    .split("\n")
    .map((l) => stripMachineMarkers(l))
    .filter((l) => l.length > 0);
}

/** 截断长文本 */
function truncate(text: string, maxLen = 120): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "…";
}

/* ── 单步骤叙述生成 ──────────────────────────────────── */

function reason1Narrative(step: PipelineTraceStep): NarrativeLine {
  const lines = extractLines(step.detail);
  // 找意图行
  const intentLine = lines.find(
    (l) => l.includes("判定意图") || l.includes("意图")
  );
  const text = intentLine
    ? `理解了你的问题：${intentLine.replace(/^判定意图[：:]\s*/, "").replace(/^意图[：:]\s*/, "")}`
    : `理解了你的问题：${truncate(step.detail || "数据分析查询")}`;
  return { key: step.id, text, links: step.links };
}

function ontologyNarrative(
  _step: PipelineTraceStep,
  ontologyMapping?: OntologyMapping
): NarrativeLine {
  const mappings = ontologyMapping?.mappings || [];

  // 按五层分组
  const layerGroups: Record<string, OntologyMappingLink[]> = {};
  for (const layer of ONTO_LAYERS) {
    layerGroups[layer.key] = [];
  }

  for (const m of mappings) {
    const kind = m.target_kind || "";
    const layerKey = KIND_TO_LAYER[kind];
    if (layerKey) {
      layerGroups[layerKey].push(m);
    }
    // "table" kind 不归入五层，在选定数据表步骤展示
  }

  const subLines: NarrativeLine[] = [];
  let totalMatched = 0;

  for (const layer of ONTO_LAYERS) {
    const items = layerGroups[layer.key] || [];
    if (items.length > 0) {
      const labels = items
        .slice(0, 5)
        .map((m) => m.target_label || "—")
        .join("、");
      const count = items.length > 5 ? `等${items.length}项` : `${items.length}项`;
      const matchType = items.some((m) => m.match_type === "semantic")
        ? "（含推断）"
        : "";
      subLines.push({
        key: `${layer.key}-matched`,
        text: `${layer.label}：${labels}（${count}）${matchType}`,
      });
      totalMatched += items.length;
    } else {
      // 关系层和属性层：尝试从 ontologyMapping.summary 找线索
      const summary = (ontologyMapping?.summary || "").toLowerCase();
      const layerLabel = layer.label.toLowerCase();
      if (summary.includes(layerLabel)) {
        subLines.push({
          key: `${layer.key}-hint`,
          text: `${layer.label}：知识库中有相关数据`,
        });
        totalMatched++;
      } else {
        subLines.push({
          key: `${layer.key}-none`,
          text: `${layer.label}：未匹配到相关知识`,
        });
      }
    }
  }

  const text =
    totalMatched > 0
      ? `匹配本体知识：共命中 ${totalMatched} 项`
      : "匹配本体知识：未命中相关知识，将依赖 Schema 推断";

  return { key: "ontology_match", text, subLines };
}

function sqlDecisionNarrative(step: PipelineTraceStep): NarrativeLine {
  const detail = (step.detail || "").trim();
  const needsSql = !detail.includes("无需") && !detail.includes("不执行");
  return {
    key: step.id,
    text: needsSql
      ? "判定需要执行 SQL 查询"
      : "判定为通用问答，无需执行 SQL",
  };
}

function reason2Narrative(step: PipelineTraceStep): NarrativeLine {
  const lines = extractLines(step.detail);
  // 简化上下文摘要
  const summary = lines.length > 0
    ? lines
        .map((l) =>
          l
            .replace(/^已加载[：:]\s*/, "")
            .replace(/^业务\/知识库约\s*/, "")
            .replace(/^相似历史问法\s*/, "")
        )
        .filter((l) => l.length > 5)
        .slice(0, 3)
        .join("；")
    : extractSummary(step.detail);
  return {
    key: step.id,
    text: `加载上下文：${truncate(summary || "已加载相关 Schema 与知识库")}`,
    links: step.links,
  };
}

function reason3Narrative(step: PipelineTraceStep): NarrativeLine {
  const lines = extractLines(step.detail);
  // 提取表名 - 从中括号或引号中抓取
  const tableNames: string[] = [];
  for (const line of lines) {
    const matches = line.match(/[「「]([^」」]+)[」」]/g);
    if (matches) {
      for (const m of matches) {
        const name = m.replace(/[「「」」]/g, "").trim();
        if (name && !tableNames.includes(name)) {
          tableNames.push(name);
        }
      }
    }
  }
  const text =
    tableNames.length > 0
      ? `选定数据表：${tableNames.join("、")}`
      : `选定数据表：${extractSummary(step.detail, 100)}`;
  return { key: step.id, text, links: step.links };
}

function routingReviewNarrative(step: PipelineTraceStep): NarrativeLine {
  const detail = stripMachineMarkers(step.detail || "");
  const isOk =
    detail.includes("通过") ||
    detail.includes("信任") ||
    detail.includes("trust") ||
    detail.includes("high");
  return {
    key: step.id,
    text: isOk
      ? "路由校验通过"
      : `路由校验：${extractSummary(detail, 80) || "需关注"}`,
  };
}

function reason4Narrative(step: PipelineTraceStep): NarrativeLine {
  const detail = step.detail || "";
  // 只取逻辑描述，不要 SQL 代码块
  const logicPart = detail
    .replace(/【SQL[^】]*】[\s\S]*$/, "")
    .replace(/```sql[\s\S]*```/g, "")
    .trim();
  const summary = extractSummary(logicPart, 100);
  return {
    key: step.id,
    text: `查询逻辑：${summary || "已生成 SQL 查询"}`,
  };
}

function reason5Narrative(step: PipelineTraceStep): NarrativeLine {
  const detail = stripMachineMarkers(step.detail || "");
  return {
    key: step.id,
    text: `执行环境校验：${extractSummary(detail, 80) || "已通过 AST 安全校验"}`,
  };
}

function reason7Narrative(step: PipelineTraceStep): NarrativeLine {
  const detail = stripMachineMarkers(step.detail || "");
  // 提取行数
  const rowMatch = detail.match(/返回\s*(\d+)\s*行|(\d+)\s*行/);
  const rows = rowMatch ? (rowMatch[1] || rowMatch[2]) : null;
  const datasourceMatch = detail.match(/数据源[：:]\s*(\S+)/);
  const ds = datasourceMatch ? datasourceMatch[1] : null;

  let text: string;
  if (rows !== null) {
    text = `执行结果：${ds ? ds + " " : ""}返回 ${rows} 行`;
  } else if (detail.includes("失败") || detail.includes("错误")) {
    text = `执行结果：${extractSummary(detail, 80)}`;
  } else if (detail.includes("未执行")) {
    text = "执行结果：等待审核确认后执行";
  } else {
    text = `执行结果：${extractSummary(detail, 80) || "已完成"}`;
  }
  return { key: step.id, text };
}

function reasonGqNarrative(step: PipelineTraceStep): NarrativeLine {
  return {
    key: step.id,
    text: `回答方式：${extractSummary(step.detail, 100) || "基于知识库检索回答"}`,
  };
}

function genericNarrative(step: PipelineTraceStep): NarrativeLine {
  return {
    key: step.id,
    text: `${step.label}：${extractSummary(step.detail, 100) || "已完成"}`,
    links: step.links,
  };
}

/* ── 步骤级调度 ──────────────────────────────────────── */

const STEP_HANDLERS: Record<
  string,
  (
    step: PipelineTraceStep,
    extra?: { ontologyMapping?: OntologyMapping }
  ) => NarrativeLine
> = {
  reasoning_1: reason1Narrative,
  reasoning_2: reason2Narrative,
  reasoning_3: reason3Narrative,
  reasoning_4: reason4Narrative,
  reasoning_5: reason5Narrative,
  reasoning_7: reason7Narrative,
  reasoning_gq: reasonGqNarrative,
  sql_decision: sqlDecisionNarrative,
  routing_review: routingReviewNarrative,
  routing_meta: (s) => genericNarrative(s),
};

/** 需要展示的核心步骤（按显示顺序） */
const DISPLAY_STEP_ORDER = [
  "reasoning_1",
  "ontology_match",
  "sql_decision",
  "reasoning_2",
  "routing_review",
  "reasoning_3",
  "reasoning_4",
  "reasoning_5",
  "reasoning_7",
  "reasoning_gq",
];

/* ── 主入口 ───────────────────────────────────────────── */

export function transformStepsToNarrative(
  steps: PipelineTraceStep[],
  options?: {
    ontologyMapping?: OntologyMapping;
    sqlDerivation?: unknown;
    intent?: "sql_query" | "general_qa";
  }
): NarrativeLine[] {
  const ontologyMapping = options?.ontologyMapping;
  const intent = options?.intent;

  // 构建步骤索引
  const stepMap = new Map<string, PipelineTraceStep>();
  for (const s of steps) {
    // 过滤掉仅流式用的 ephemeral step 和内部修复步骤
    if (s.id.startsWith("live_")) continue;
    if (s.id === "sql_repair" || s.id === "sql_repair_result") continue;
    if (s.id === "nlp_preprocess") continue;
    // 失败的 sql_execute 不展示
    if (s.id === "sql_execute") {
      const d = (s.detail || "").trim();
      if (!/成功[：:]/.test(d)) continue;
    }
    stepMap.set(s.id, s);
  }

  const result: NarrativeLine[] = [];

  for (const stepId of DISPLAY_STEP_ORDER) {
    // ontology_match 特殊处理：融合 ontologyMapping 数据
    if (stepId === "ontology_match") {
      const step = stepMap.get(stepId);
      const mapping = ontologyMapping;
      // 只有当有 mapping 数据或 trace 步骤存在时才展示
      if (
        (mapping && mapping.matched !== false && mapping.mappings?.length) ||
        step
      ) {
        result.push(
          ontologyNarrative(step || { id: stepId, label: "", detail: "" }, mapping)
        );
      }
      continue;
    }

    // general_qa 路径只展示 reasoning_1 和 reasoning_gq
    if (intent === "general_qa") {
      if (stepId !== "reasoning_1" && stepId !== "reasoning_gq") continue;
    }

    const step = stepMap.get(stepId);
    if (!step) continue;

    const handler = STEP_HANDLERS[stepId];
    if (handler) {
      result.push(handler(step, { ontologyMapping }));
    }
  }

  // 如果 pipeline_trace 为空但有 ontologyMapping（历史数据兼容）
  if (result.length === 0 && ontologyMapping && ontologyMapping.matched !== false) {
    result.push(
      ontologyNarrative(
        { id: "ontology_match", label: "", detail: "" },
        ontologyMapping
      )
    );
    if (options?.sqlDerivation) {
      const sd = options.sqlDerivation as Record<string, unknown>;
      if (sd.pattern && typeof sd.pattern === "string") {
        result.push({
          key: "sql_derivation",
          text: `查询模式：${sd.pattern}`,
        });
      }
    }
  }

  return result;
}

/** 从叙述行生成折叠时的一行摘要 */
export function narrativeToSummary(lines: NarrativeLine[]): string {
  if (!lines.length) return "";
  const first = lines[0].text.replace(/^理解了你的问题[：:]\s*/, "");
  const last =
    lines.length > 1
      ? lines[lines.length - 1].text.replace(/^执行结果[：:]\s*/, "")
      : "";
  if (!last || last === first) return first;
  return `${first} → ${last}`;
}
