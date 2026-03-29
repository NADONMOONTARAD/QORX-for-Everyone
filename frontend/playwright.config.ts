import path from "path";
import { defineConfig } from "@playwright/test";

const reportRoot = path.resolve(__dirname, "..", "backend", "data", "test-reports");
const externalBaseURL = process.env.E2E_BASE_URL?.trim();
const baseURL = externalBaseURL || "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  reporter: [
    ["list"],
    [
      "html",
      {
        outputFolder: path.join(reportRoot, "playwright-report"),
        open: "never",
      },
    ],
    [
      "junit",
      {
        outputFile: path.join(reportRoot, "playwright-junit.xml"),
      },
    ],
  ],
  outputDir: path.join(reportRoot, "playwright-output"),
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: externalBaseURL
    ? undefined
    : {
        command: "node ./scripts/start-e2e-server.mjs",
        port: 3100,
        reuseExistingServer: true,
        timeout: 300_000,
        stdout: "pipe",
        stderr: "pipe",
      },
});
