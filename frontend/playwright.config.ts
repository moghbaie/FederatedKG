import { defineConfig, devices } from "@playwright/test";

// Runs against the Docker Compose stack (`docker compose up -d --build --wait`), test mode on.
export default defineConfig({
  testDir: "./tests/e2e",
  // Screenshot capture is opt-in (FKG_SCREENSHOTS=1); the normal run executes the *.spec.ts suites.
  testMatch: process.env.FKG_SCREENSHOTS ? "**/*.capture.ts" : "**/*.spec.ts",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.FKG_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
