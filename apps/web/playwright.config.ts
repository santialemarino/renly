import { defineConfig, devices } from '@playwright/test';

import { WEB_BASE } from './tests/e2e/helpers/api';
import { AUTH_STATE_PATH, e2eCredentials } from './tests/e2e/helpers/auth';

// `process.env.CI` arrives as a string — treat `"false"` and `"0"` as opt-outs so an explicit
// `CI=false` in a local shell doesn't force CI-mode behavior.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const ciEnv = process.env.CI;
const isCI = !!ciEnv && ciEnv !== 'false' && ciEnv !== '0';

// One definition, shared with the API helper so the browser and the specs' session reads agree.
const baseURL = WEB_BASE;

/*
 * The authenticated project runs only when E2E_EMAIL / E2E_PASSWORD name a real account — the same
 * env-gating the API's integration suites use, and for the same reason: a fresh clone has no seeded
 * user, and a suite that fails there teaches people to ignore it. With them unset the logged-out
 * specs still run and the suite exits 0.
 */
const authenticated = e2eCredentials() !== null;

// Playwright configuration for the Renly web app.
// Tests live under tests/e2e/ and run against an already-running web app (a local dev server on port
// 3000 by default, a production build in CI) — globalSetup fails fast when nothing answers there.
export default defineConfig({
  testDir: './tests/e2e',
  /*
   * Every test is its own unit of scheduling, so `--shard=i/n` splits the suite evenly by test rather
   * than by file (the three largest files are over half of it). It changes nothing about ORDER: with
   * one worker, a run or a shard still executes its tests one at a time, in file order, and a file's
   * `beforeAll` / `afterAll` still run once around the tests of that file the worker gets. What it
   * requires is that no test leans on an earlier test in its file having run — a file that ever does
   * opts out with `test.describe.configure({ mode: 'default' })`, which keeps it whole on one shard.
   */
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  /*
   * One worker: the authenticated specs share ONE harness account and change it as they go (display
   * currencies, digest cadence, notification state), so two tests at once would race on it. CI gets
   * its parallelism from shards instead, each with a database and harness account of its own.
   */
  workers: 1,
  /*
   * CI swaps the HTML report for two others: `github` turns each failure into an annotation on the
   * PR's diff, and `blob` writes the shard's raw results. The workflow merges every shard's blob into
   * one HTML report and one JSON file, and checks the JSON — that every spec file executed in its
   * project and that nothing skipped: the ways a run can go green on less than the whole suite.
   */
  reporter: isCI
    ? [['list'], ['github'], ['blob']]
    : [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  outputDir: 'test-results',
  // Logs in once and saves the state the authenticated project loads. A no-op when unconfigured.
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    baseURL,
    /*
     * The browser's clock and language, pinned rather than inherited from the machine. Every date the
     * suite writes is a UTC date — the specs build theirs with `toISOString()`, the CI seed with
     * `date -u` — and the harness account has no stored timezone, so the API reads its "today" in
     * UTC too. A browser in the runner's own zone (a laptop in Buenos Aires, say) disagreed with all
     * three for three hours every evening: the protected layout auto-syncs the account to the
     * browser's zone, and the app's "today" (date-picker defaults, the reconcile dialog, the current
     * statement) became a different day from the one a spec had just seeded. The language is the one
     * the harness account registers with; specs that need Spanish set the locale cookie themselves.
     * `global-setup.ts` signs in with the same two, so the saved session never carries another zone.
     */
    timezoneId: 'UTC',
    locale: 'en-US',
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
