import { defineConfig, devices } from '@playwright/test';

import { AUTH_STATE_PATH, e2eCredentials } from './tests/e2e/helpers/auth';

// `process.env.CI` arrives as a string — treat `"false"` and `"0"` as opt-outs so an explicit
// `CI=false` in a local shell doesn't force CI-mode behavior.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const ciEnv = process.env.CI;
const isCI = !!ciEnv && ciEnv !== 'false' && ciEnv !== '0';

// `||` (not `??`) so an empty `PLAYWRIGHT_BASE_URL=""` falls back to the default instead of
// producing an unusable empty baseURL.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

/*
 * The authenticated project runs only when E2E_EMAIL / E2E_PASSWORD name a real account — the same
 * env-gating the API's integration suites use, and for the same reason: a fresh clone has no seeded
 * user, and a suite that fails there teaches people to ignore it. With them unset the logged-out
 * specs still run and the suite exits 0.
 */
const authenticated = e2eCredentials() !== null;

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
  // Logs in once and saves the state the authenticated project loads. A no-op when unconfigured.
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    testIdAttribute: 'data-testid',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  /*
   * Two projects over one directory, split by whether a spec needs a session, with the file naming
   * carrying the split: `*.auth.spec.ts` runs signed in, everything else signed OUT.
   *
   * The logged-out project has to EXCLUDE the authenticated specs rather than simply not include
   * them, because a project with no `testMatch` matches every file in `testDir` — so the auth specs
   * would otherwise also run with no session, where each asserts something about a page it would
   * never reach.
   */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testIgnore: /\.auth\.spec\.ts$/,
    },
    ...(authenticated
      ? [
          {
            name: 'chromium-authenticated',
            use: { ...devices['Desktop Chrome'], storageState: AUTH_STATE_PATH },
            testMatch: /\.auth\.spec\.ts$/,
          },
        ]
      : []),
  ],
});
