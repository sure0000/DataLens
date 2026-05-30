import { useEffect, useMemo, useRef } from "react";

/**
 * 仅在 tasksActive 从 false→true 时启动 interval；依赖 tasksActive 布尔值，避免因 setState 引用变化反复重启轮询。
 */
export function useBackgroundTaskPolling({
  tasksActive,
  intervalMs = 3000,
  onTick,
  onTasksCompleted,
}: {
  tasksActive: boolean;
  intervalMs?: number;
  onTick: () => void | Promise<void>;
  onTasksCompleted?: () => void;
}): void {
  const onTickRef = useRef(onTick);
  const onCompletedRef = useRef(onTasksCompleted);
  onTickRef.current = onTick;
  onCompletedRef.current = onTasksCompleted;

  const prevActiveRef = useRef(false);

  useEffect(() => {
    const wasActive = prevActiveRef.current;
    if (wasActive && !tasksActive) {
      onCompletedRef.current?.();
    }
    prevActiveRef.current = tasksActive;

    if (!tasksActive) return;

    let cancelled = false;
    const run = () => {
      if (!cancelled) void onTickRef.current();
    };
    run();
    const timer = setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [tasksActive, intervalMs]);
}

/** 从任务指纹推导是否活跃（指纹仅含 running 源与 worker 中文档） */
export function useTaskActivityFlag(
  cleaningRunningFp: string,
  docsWorkerFp: string,
): boolean {
  return useMemo(
    () => cleaningRunningFp.length > 0 || docsWorkerFp.length > 0,
    [cleaningRunningFp, docsWorkerFp],
  );
}
