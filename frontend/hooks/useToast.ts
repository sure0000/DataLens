"use client";

import { useCallback, useState } from "react";

export type ToastTone = "success" | "error" | "info";

export interface ToastState {
  message: string;
  tone: ToastTone;
  durationMs: number;
}

export function useToast() {
  const [toast, setToast] = useState<ToastState>({ message: "", tone: "success", durationMs: 4000 });

  const notify = useCallback((message: string, tone: ToastTone = "success", durationMs: number = 4000) => {
    setToast({ message, tone, durationMs });
  }, []);

  const dismiss = useCallback(() => {
    setToast((prev) => (prev.message ? { ...prev, message: "" } : prev));
  }, []);

  return { toast, notify, dismiss };
}
