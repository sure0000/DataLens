"use client";

import { useEffect } from "react";
import { applyTheme, getSystemTheme } from "../lib/theme";
import { readUserPreferences, type ThemePreference } from "../lib/userPreferences";

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    applyTheme(readUserPreferences().theme);

    const onPrefsUpdated = () => {
      applyTheme(readUserPreferences().theme);
    };

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemChange = () => {
      if (readUserPreferences().theme === "system") {
        applyTheme("system");
      }
    };

    window.addEventListener("datalens-user-prefs-updated", onPrefsUpdated);
    media.addEventListener("change", onSystemChange);
    return () => {
      window.removeEventListener("datalens-user-prefs-updated", onPrefsUpdated);
      media.removeEventListener("change", onSystemChange);
    };
  }, []);

  return children;
}

export function themePreferenceLabel(theme: ThemePreference): string {
  if (theme === "light") return "明亮模式";
  if (theme === "dark") return "暗黑模式";
  return "跟随系统";
}

export function resolvedThemeLabel(theme: ThemePreference): string {
  if (theme === "system") {
    return getSystemTheme() === "dark" ? "暗黑（系统）" : "明亮（系统）";
  }
  return themePreferenceLabel(theme);
}
