"use client";

import { useEffect, useState } from "react";
import { resolvedThemeLabel, themePreferenceLabel } from "../ThemeProvider";
import { setThemePreference } from "../../lib/theme";
import { readUserPreferences, type ThemePreference } from "../../lib/userPreferences";

const THEME_OPTIONS: { id: ThemePreference; description: string }[] = [
  { id: "light", description: "始终使用浅色界面" },
  { id: "dark", description: "始终使用 ChatGPT 风格深色界面" },
  { id: "system", description: "自动匹配操作系统的外观设置" },
];

function IconSun({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

export default function AppearanceTab() {
  const [theme, setTheme] = useState<ThemePreference>("dark");

  useEffect(() => {
    setTheme(readUserPreferences().theme);

    const onPrefsUpdated = () => {
      setTheme(readUserPreferences().theme);
    };
    window.addEventListener("datalens-user-prefs-updated", onPrefsUpdated);
    return () => window.removeEventListener("datalens-user-prefs-updated", onPrefsUpdated);
  }, []);

  function selectTheme(next: ThemePreference) {
    setTheme(next);
    setThemePreference(next);
  }

  return (
    <section className="app-card rounded-2xl p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-hover text-app-primary">
          <IconSun />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="app-card-title text-base">外观</h2>
          <p className="mt-1 text-sm text-app-secondary">
            选择界面主题。当前生效：
            <span className="font-medium text-app-primary">{resolvedThemeLabel(theme)}</span>
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-2" role="radiogroup" aria-label="主题选择">
        {THEME_OPTIONS.map((option) => {
          const selected = theme === option.id;
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => selectTheme(option.id)}
              className={`app-select-card flex w-full items-start gap-3 px-4 py-3 text-left ${
                selected ? "border-app-activeBorder bg-app-activeBg ring-1 ring-app-activeBorder" : ""
              }`}
            >
              <span
                className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                  selected ? "border-app-primary bg-app-primary" : "border-app-border"
                }`}
                aria-hidden
              >
                {selected && <span className="h-1.5 w-1.5 rounded-full bg-[var(--app-primary-text)]" />}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-app-primary">{themePreferenceLabel(option.id)}</span>
                <span className="mt-0.5 block text-xs text-app-secondary">{option.description}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
