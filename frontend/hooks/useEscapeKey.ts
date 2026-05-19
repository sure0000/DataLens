"use client";

import { useEffect } from "react";

export function useEscapeKey(handler: () => void, enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return;

    const listener = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") handler();
    };

    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, [handler, enabled]);
}
