/** 双主题语义化样式类名 — 配合 globals.css 中的 CSS 变量使用 */

export const chipSuccess = "app-chip app-chip-success";
export const chipError = "app-chip app-chip-error";
export const chipInfo = "app-chip app-chip-info";
export const chipWarning = "app-chip app-chip-warning";
export const chipNeutral = "app-chip app-chip-neutral";
export const chipProgress = "app-chip app-chip-progress";

export const alertError = "app-alert app-alert-error";
export const alertInfo = "app-alert app-alert-info";
export const alertWarning = "app-alert app-alert-warning";

export const textSuccess = "app-text-success";
export const textDanger = "app-text-danger";
export const textWarning = "app-text-warning";
export const textInfo = "app-text-info";
export const textAccent = "app-text-accent";

export const tabActive = "app-tab-active";
export const tabInactive = "app-tab-inactive";

export const userBubble = "app-user-bubble";
export const chatPanel = "app-chat-panel";
export const panelHeader = "app-panel-header";
export const panelSubtle = "app-panel-subtle";

export const linkAccent = "app-link-accent";

export const tagViolet = "app-tag-violet";
export const badgeExclusive = "app-badge-exclusive";

export const pipelineStepDone = "app-pipeline-step app-pipeline-step-done";
export const pipelineStepProgress = "app-pipeline-step app-pipeline-step-progress";
export const pipelineStepWaiting = "app-pipeline-step app-pipeline-step-waiting";
export const pipelineStepSkipped = "app-pipeline-step app-pipeline-step-skipped";

export const pipelineBadgeDone = "app-pipeline-badge app-pipeline-badge-done";
export const pipelineBadgeProgress = "app-pipeline-badge app-pipeline-badge-progress";
export const pipelineBadgeWaiting = "app-pipeline-badge app-pipeline-badge-waiting";

export const liveHighlight = "app-live-highlight";
export const traceCard = "app-trace-card";
export const traceCardHeader = "app-trace-card-header";
export const traceSqlWrap = "app-trace-sql-wrap";
export const traceCodeWrap = "app-trace-code-wrap";
export const traceIndigoPanel = "app-trace-indigo-panel";
export const traceIndigoHeader = "app-trace-indigo-header";

export const errorIconWrap = "app-error-icon-wrap";

export const reasoningBadge = {
  verified: "app-reasoning-badge app-reasoning-badge-verified",
  join: "app-reasoning-badge app-reasoning-badge-join",
  issue: "app-reasoning-badge app-reasoning-badge-issue",
  review: "app-reasoning-badge app-reasoning-badge-review",
  skipped: "app-reasoning-badge app-reasoning-badge-skipped",
} as const;

export const structuredBadge = {
  info: "app-structured-badge app-structured-badge-info",
  next: "app-structured-badge app-structured-badge-next",
  boundary: "app-structured-badge app-structured-badge-boundary",
  alt: "app-structured-badge app-structured-badge-alt",
  basis: "app-structured-badge app-structured-badge-basis",
} as const;

export function pipelineStepClass(status: "done" | "progress" | "waiting" | "skipped"): string {
  if (status === "done") return pipelineStepDone;
  if (status === "progress") return pipelineStepProgress;
  if (status === "skipped") return pipelineStepSkipped;
  return pipelineStepWaiting;
}

export function pipelineBadgeClass(status: "done" | "progress" | "waiting" | "skipped"): string {
  if (status === "done") return pipelineBadgeDone;
  if (status === "progress") return pipelineBadgeProgress;
  return pipelineBadgeWaiting;
}

export function confidenceClass(score: number): string {
  if (score >= 0.7) return textSuccess;
  if (score >= 0.4) return textWarning;
  return textDanger;
}

export function toastToneClass(tone: "success" | "error" | "info"): string {
  if (tone === "error") return alertError;
  if (tone === "info") return alertInfo;
  return "app-alert app-alert-success";
}
