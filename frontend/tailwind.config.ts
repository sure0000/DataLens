import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          main: "var(--app-main-bg)",
          card: "var(--app-card-bg)",
          border: "var(--app-card-border)",
          subtle: "var(--app-border-subtle)",
          soft: "var(--app-border-soft)",
          surface: "var(--app-surface-subtle)",
          hover: "var(--app-surface-hover)",
          primary: "var(--app-text-primary)",
          secondary: "var(--app-text-secondary)",
          ink: "var(--app-text-ink)",
          muted: "var(--app-text-placeholder)",
          link: "var(--app-link)",
          activeBorder: "var(--app-active-border)",
          activeBg: "var(--app-active-bg)",
          chip: "var(--app-chip-bg)",
          chipText: "var(--app-chip-text)",
          overlay: "var(--app-overlay-backdrop)"
        }
      }
    }
  },
  plugins: []
};

export default config;
