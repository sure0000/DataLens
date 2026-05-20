import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "scenario-*.spec.ts",
  timeout: 600000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,

  use: {
    baseURL: process.env.FRONTEND_URL || "http://localhost:3000",
    headless: true,
    viewport: { width: 1440, height: 900 },
    actionTimeout: 15000,
    screenshot: "on",
    video: "off",
    trace: "off",
  },

  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium", channel: "chrome" },
    },
  ],

  outputDir: "test-results/artifacts",
  reporter: [
    ["html", { outputFolder: "test-results/report" }],
    ["list"],
  ],
});
