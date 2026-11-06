import { defineConfig } from "@playwright/test";

// Deterministic UI regression server: no inference, hardware, or production analytics.
export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:4186",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    { command: "node tests/fixtures/api-server.mjs", url: "http://127.0.0.1:8766/status" },
    {
      command: "npm run dev -- --webpack --hostname 127.0.0.1 --port 4186",
      url: "http://127.0.0.1:4186",
      timeout: 120_000,
      env: { API_INTERNAL_URL: "http://127.0.0.1:8766", NEXT_PUBLIC_API_URL: "http://127.0.0.1:8766", NEXT_PUBLIC_GA_ENABLED: "0" },
    },
  ],
});
