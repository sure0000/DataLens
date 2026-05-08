const PREFS_KEY = "datalens_user_prefs_v1";

export type UserPreferences = {
  /** Copilot 对话模型：auto 或 catalog id，如 deepseek:deepseek-chat */
  chatModel: string;
};

const defaultPreferences = (): UserPreferences => ({
  chatModel: "auto"
});

export function readUserPreferences(): UserPreferences {
  if (typeof window === "undefined") return defaultPreferences();
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return defaultPreferences();
    const parsed = JSON.parse(raw) as Partial<UserPreferences>;
    return {
      chatModel: typeof parsed.chatModel === "string" && parsed.chatModel.trim() ? parsed.chatModel.trim() : "auto"
    };
  } catch {
    return defaultPreferences();
  }
}

export function writeUserPreferences(next: Partial<UserPreferences>) {
  if (typeof window === "undefined") return;
  const prev = readUserPreferences();
  const merged: UserPreferences = { ...prev, ...next };
  localStorage.setItem(PREFS_KEY, JSON.stringify(merged));
  window.dispatchEvent(new CustomEvent("datalens-user-prefs-updated"));
}
