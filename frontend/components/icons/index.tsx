"use client";

import {
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  Circle,
  CircleHelp,
  Loader2,
  MinusCircle,
  PackageX,
  Sparkles,
  XCircle,
} from "lucide-react";


/** 流水线 / 建模步骤状态（带默认语义色） */
export type PipelineStepIconStatus = "ok" | "fail" | "running" | "skip" | "pending" | "warning";

const PIPELINE_ICON_CLASS: Record<PipelineStepIconStatus, string> = {
  ok: "text-emerald-600 dark:text-emerald-400",
  fail: "text-red-500 dark:text-red-400",
  running: "text-indigo-500 dark:text-indigo-400 animate-spin",
  skip: "text-app-muted",
  pending: "text-app-muted",
  warning: "text-amber-500 dark:text-amber-400",
};

export function PipelineStepIcon({
  status,
  className = "h-4 w-4",
}: {
  status: PipelineStepIconStatus;
  className?: string;
}) {
  const cls = `${className} shrink-0 ${PIPELINE_ICON_CLASS[status]}`;
  switch (status) {
    case "ok":
      return <CheckCircle2 className={cls} aria-hidden />;
    case "fail":
      return <XCircle className={cls} aria-hidden />;
    case "running":
      return <Loader2 className={cls} aria-hidden />;
    case "skip":
      return <MinusCircle className={cls} aria-hidden />;
    case "warning":
      return <AlertTriangle className={cls} aria-hidden />;
    default:
      return <Circle className={cls} aria-hidden />;
  }
}

export type PipelineCardStatus = "done" | "progress" | "waiting" | "skipped" | "failed";

export function pipelineCardStatusToIcon(status: PipelineCardStatus): PipelineStepIconStatus {
  switch (status) {
    case "done":
      return "ok";
    case "progress":
      return "running";
    case "skipped":
      return "skip";
    case "failed":
      return "fail";
    default:
      return "pending";
  }
}

const PIPELINE_STATUS_LABEL: Record<PipelineCardStatus, string> = {
  done: "完成",
  progress: "进行中",
  waiting: "待开始",
  skipped: "跳过",
  failed: "失败",
};

/** 带彩色图标的状态标签（替代 ✓ / ○ / ◐ 文本符号） */
export function PipelineStatusBadge({
  status,
  suffix,
  className = "",
  iconClassName = "h-3.5 w-3.5",
}: {
  status: PipelineCardStatus;
  suffix?: string;
  className?: string;
  iconClassName?: string;
}) {
  const label = PIPELINE_STATUS_LABEL[status];
  const text = suffix ? `${label} ${suffix}` : label;
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <PipelineStepIcon status={pipelineCardStatusToIcon(status)} className={iconClassName} />
      <span>{text}</span>
    </span>
  );
}

/** 证据包 / 导入源连接器图标 */
export function ConnectorIcon({
  connector,
  className = "text-app-secondary",
}: {
  connector: string;
  className?: string;
}) {
  const props = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: `shrink-0 ${className}`,
    "aria-hidden": true,
  };

  switch (connector) {
    case "git":
      return (
        <svg {...props}>
          <path d="M6 3v12" />
          <circle cx="6" cy="18" r="3" />
          <path d="M18 6v9" />
          <circle cx="18" cy="18" r="3" />
          <path d="M6 15a9 9 0 009-9" />
        </svg>
      );
    case "database":
      return (
        <svg {...props}>
          <ellipse cx="12" cy="6" rx="8" ry="3" />
          <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
          <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
        </svg>
      );
    case "api":
      return (
        <svg {...props}>
          <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
        </svg>
      );
    case "manual":
      return (
        <svg {...props}>
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
      );
    case "ttl":
      return (
        <svg {...props}>
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
          <line x1="12" y1="22.08" x2="12" y2="12" />
        </svg>
      );
    case "file":
    default:
      return (
        <svg {...props}>
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      );
  }
}

/** SHACL / 质量摘要卡片用彩色图标 */
export function QualityStatIcon({
  tone,
  className = "h-5 w-5",
}: {
  tone: "success" | "danger" | "warning" | "muted";
  className?: string;
}) {
  const toneCls =
    tone === "success"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "danger"
        ? "text-red-600 dark:text-red-400"
        : tone === "warning"
          ? "text-amber-500 dark:text-amber-400"
          : "text-app-muted";
  const cls = `${className} shrink-0 ${toneCls}`;
  switch (tone) {
    case "success":
      return <CheckCircle2 className={cls} aria-hidden />;
    case "danger":
      return <XCircle className={cls} aria-hidden />;
    case "warning":
      return <AlertTriangle className={cls} aria-hidden />;
    default:
      return <Circle className={cls} aria-hidden />;
  }
}



