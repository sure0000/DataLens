import { readUserPreferences, writeUserPreferences, type ThemePreference } from "./userPreferences";

export type ResolvedTheme = "light" | "dark";

export function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") return getSystemTheme();
  return preference;
}

export function applyTheme(preference: ThemePreference) {
  if (typeof document === "undefined") return resolveTheme(preference);
  const resolved = resolveTheme(preference);
  const root = document.documentElement;
  root.setAttribute("data-theme", resolved);
  root.classList.toggle("dark", resolved === "dark");
  return resolved;
}

export function initThemeFromStorage() {
  const preference = readUserPreferences().theme;
  return applyTheme(preference);
}

export function setThemePreference(preference: ThemePreference) {
  writeUserPreferences({ theme: preference });
  return applyTheme(preference);
}

/** 供 layout 内联脚本使用，避免首屏主题闪烁 */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var k="datalens_user_prefs_v1";var raw=localStorage.getItem(k);var pref="dark";if(raw){var p=JSON.parse(raw);if(p.theme==="light"||p.theme==="dark"||p.theme==="system")pref=p.theme;}var resolved=pref==="system"?(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):pref;document.documentElement.setAttribute("data-theme",resolved);document.documentElement.classList.toggle("dark",resolved==="dark");}catch(e){document.documentElement.setAttribute("data-theme","dark");document.documentElement.classList.add("dark");}})();`;
