"use client";

import type { ReactNode } from "react";
import type { TraceEntityLink } from "./chatSessions";
import { TraceCheckpointIcon, TrustLevelIcon } from "../components/icons";
import {
  traceCheckpointStatusLabel,
  traceCheckpointStripClass,
  type TraceCheckpointStatus
} from "./copilotTraceStatus";
import { renderTraceDetailWithLinks } from "./traceEntityLinks";
import { chipNeutral, reasoningBadge } from "./themeClasses";
import { tryParseReasoning3Line, type TrustUiCode } from "./traceReasoning3Parse";

export type { TrustUiCode } from "./traceReasoning3Parse";
export { tryParseReasoning3Line, stripReasoning3MachineMarkersForPlainText } from "./traceReasoning3Parse";

/** 与 reasoning_3 检查点推断一致（表级默认；单行会再叠加上下文关键词） */
function trustToCheckpointStatus(trust: TrustUiCode): TraceCheckpointStatus {
  switch (trust) {
    case "high":
      return "verified";
    case "medium-high":
      return "inferred_ok";
    case "medium":
      return "inferred_review";
    case "low":
      return "context_missing";
    case "review":
      return "inferred_review";
    default:
      return "inferred_ok";
  }
}

/**
 * 按依据分层（业务域 ‖ 数据库 ‖ 数据表）推断图标，同义缺口固定同一状态，
 * 避免「同为业务域缺失、仅表级 trust 不同」却出现 PackageX / Check 混用。
 */
function inferBasisLayerStatus(layer: string, trust: TrustUiCode): TraceCheckpointStatus {
  const t = layer.trim();

  if (/^业务域：/.test(t)) {
    if (/未选择业务域|未找到对应业务域|元数据中未找到对应业务域/.test(t)) return "context_missing";
    return "verified";
  }

  if (/^数据库：/.test(t)) {
    if (
      /未检索到数据源实体|缺少 datasource_id|无法下钻到连接配置|无法解析到具体数据源与库名|无表元数据锚点/.test(t)
    ) {
      return "context_missing";
    }
    return "inferred_ok";
  }

  if (/^数据表：/.test(t)) {
    return trustToCheckpointStatus(trust);
  }

  const missingLike =
    /缺失|未提供|暂无说明|暂无可|无法从|无法确定|未能|未找到|不存在对应|无有效|无生成|（空）|未解析出|未出现在|未携带|未命中|库中未找到|无生成\s*SQL|无表名/i;
  const reviewLike =
    /待核对|请确认|请对照|不一致|回退|容错|未稳定|候选|别名|请人工|不等价于|不等价|仅作|不等同|多表\s*JOIN|JOIN\s*之一|JOIN\/FROM|FROM\/JOIN/i;

  if (missingLike.test(t)) return "context_missing";
  if (reviewLike.test(t)) return "inferred_review";
  return trustToCheckpointStatus(trust);
}

function StatusGlyph({ status, className }: { status: TraceCheckpointStatus; className?: string }) {
  return <TraceCheckpointIcon status={status} className={className} />;
}

function TrustBadge({ code }: { code: TrustUiCode }) {
  const labelCls = "text-[12px] font-medium leading-none text-app-ink";
  const wrap = "inline-flex items-center gap-1";
  const a11y: Record<TrustUiCode, string> = {
    high: "可信度：高",
    "medium-high": "可信度：中高",
    medium: "可信度：中",
    low: "可信度：低",
    review: "可信度：待核对"
  };
  const labels: Record<TrustUiCode, string> = {
    high: "高",
    "medium-high": "中高",
    medium: "中",
    low: "低",
    review: "待核",
  };
  return (
    <span className={wrap} role="img" aria-label={a11y[code]} title={a11y[code]}>
      <TrustLevelIcon code={code} />
      <span className={labelCls}>{labels[code]}</span>
    </span>
  );
}

type RoleTone = "locked" | "primary" | "join" | "alert" | "context" | "missing" | "other";

function roleTone(role: string): RoleTone {
  const r = role.trim();
  const bare = r.replace(/\s/g, "");
  if (!bare || /^[—－\-–]+$/.test(bare)) return "missing";
  if (r.includes("主分析") && r.includes("锁定一致")) return "locked";
  if (r.includes("用户锁定主表") || r.includes("未解析到该物理名")) return "alert";
  if (r.includes("上下文参考")) return "context";
  if (r.includes("查询涉及") || r.includes("FROM/JOIN")) return "join";
  if (r.includes("主分析")) return "primary";
  return "other";
}

/** 角色：圆角 tag，与消息内意图 chip 同系 */
function RoleTag({ role }: { role: string }) {
  const tone = roleTone(role);
  const base =
    "inline-flex max-w-full min-w-0 items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-tight";
  const toneCls: Record<RoleTone, string> = {
    locked: reasoningBadge.verified,
    primary: "border-[var(--app-active-border)] bg-[var(--app-active-bg)] text-app-chipText",
    join: reasoningBadge.join,
    alert: reasoningBadge.issue,
    context: reasoningBadge.review,
    missing: reasoningBadge.skipped,
    other: `${chipNeutral} text-app-chipText`,
  };
  const isMissing = tone === "missing";
  return (
    <span
      className={`${base} ${toneCls[tone]}`}
      title={isMissing ? "角色信息缺失或未标注" : undefined}
      {...(isMissing ? { "aria-label": "角色信息缺失" } : {})}
    >
      <span className="min-w-0 break-words">{isMissing ? "未标注" : role}</span>
    </span>
  );
}

/** 与「2. 确认拿到的上下文信息」子检查点同一套布局（条带 + 状态图标 + 序号 + 正文） */
function BasisCheckpointRow({
  status,
  indexLabel,
  children
}: {
  status: TraceCheckpointStatus;
  indexLabel: string;
  children: ReactNode;
}) {
  const a11y = traceCheckpointStatusLabel(status);
  const iconBox = "h-4 w-4";
  const idxCls = "w-4 shrink-0 self-start pt-px text-right text-[10px] font-medium tabular-nums text-app-muted";
  return (
    <li className="flex items-stretch gap-1.5 py-1.5">
      <div className={`w-1 shrink-0 self-stretch rounded-full ${traceCheckpointStripClass(status)}`} aria-hidden />
      <div className="flex shrink-0 self-start pt-0.5" role="img" aria-label={a11y}>
        <StatusGlyph status={status} className={iconBox} />
      </div>
      <span className={idxCls} aria-hidden>
        {indexLabel}
      </span>
      <div className="min-w-0 flex-1 self-start">
        <div className="whitespace-pre-wrap break-words text-[12px] leading-snug text-app-secondary">{children}</div>
      </div>
    </li>
  );
}

/** 第 3 步：表名链接 + 可信度（图标+文字）+ 角色 tag + 判断依据（上下文检查点样式） */
export function renderReasoning3Row(line: string, links: TraceEntityLink[]): ReactNode {
  const parsed = tryParseReasoning3Line(line);
  if (!parsed) return renderTraceDetailWithLinks(line, links);
  const layers = parsed.basisRaw
    .split("‖")
    .map((x) => x.trim())
    .filter(Boolean);
  const basisMissing = layers.length === 0;

  return (
    <span className="block w-full min-w-0">
      <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="min-w-0 font-medium text-app-primary">{renderTraceDetailWithLinks(parsed.tableToken, links)}</span>
        <TrustBadge code={parsed.trust} />
        <RoleTag role={parsed.role} />
      </span>

      <div className="mt-2 min-w-0">
        <ol className="app-trace-divide m-0 list-none p-0">
          {basisMissing ? (
            <BasisCheckpointRow status="context_missing" indexLabel="—">
              <span className="italic text-app-muted">未提供说明，请结合上文或人工核对。</span>
            </BasisCheckpointRow>
          ) : (
            layers.map((layer, i) => (
              <BasisCheckpointRow key={i} status={inferBasisLayerStatus(layer, parsed.trust)} indexLabel={String(i + 1)}>
                {renderTraceDetailWithLinks(layer, links)}
              </BasisCheckpointRow>
            ))
          )}
        </ol>
      </div>
    </span>
  );
}
