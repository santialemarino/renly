import { defineConfig, devices } from '@playwright/test';

// `process.env.CI` arrives as a string — treat `"false"` and `"0"` as opt-outs so an explicit
// `CI=false` in a local shell doesn't force CI-mode behavior.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const ciEnv = process.env.CI;
const isCI = !!ciEnv && ciEnv !== 'false' && ciEnv !== '0';

// `||` (not `??`) so an empty `PLAYWRIGHT_BASE_URL=""` falls back to the default instead of
// producing an unusable empty baseURL.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

// Playwright configuration for the Renly web app.
// Tests live under tests/e2e/ and run against a local dev server on port 3000.
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  // Single worker by default so files run serially too — `fullyParallel: false` only disables
  // intra-file parallelism. Bump this once the suite is large and tests are proven independent.
  workers: 1,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  outputDir: 'test-results',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    testIdAttribute: 'data-testid',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
