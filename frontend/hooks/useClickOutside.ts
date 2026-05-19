"use client";

import { type RefObject, useEffect } from "react";

export function useClickOutside(ref: RefObject<HTMLElement | null>, handler: () => void, enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return;

    const listener = (evt: MouseEvent) => {
      const el = ref.current;
      if (!el || el.contains(evt.target as Node)) return;
      handler();
    };

    document.addEventListener("mousedown", listener);
    return () => document.removeEventListener("mousedown", listener);
  }, [ref, handler, enabled]);
}
