import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname } from 'node:path';
import { chromium, type Browser, type FullConfig } from '@playwright/test';

import { API_BASE } from './helpers/api';
import {
  ADMIN_AUTH_STATE_PATH,
  AUTH_STATE_PATH,
  e2eAdminCredentials,
  e2eCredentials,
  type E2ECredentials,
} from './helpers/auth';

// Route literals mirror apps/web/config/routes.ts. Kept local like the two logged-out specs' — the
// Playwright loader resolves no build-time path aliases.
const LOGIN = '/login';
const PROTECTED_PATH = '/dashboard';
// An admin-only page and what it ends in: its invite form for an admin, the not-found page for anyone
// without `users.is_admin` (or for everyone when the API is not in invite mode).
const ADMIN_PATH = '/admin';
const ADMIN_CONTENT = '[data-testid="admin-invite-email"]';
const NOT_FOUND = '[data-testid="not-found"]';

// Long enough for a cold dev server's first compile of /login, short enough that a wrong password
// fails the run in seconds rather than making it look hung.
const LOGIN_TIMEOUT_MS = 15_000;

// How long the preflight waits for a response before it stops waiting. Not a verdict: a server that
// accepted the connection is up however long it takes to answer.
const PREFLIGHT_TIMEOUT_MS = 10_000;

/*
 * Checks that the web app and the API are both running before any spec does. The suite never starts
 * them itself, and without this a forgotten server surfaces as every spec timing out on its first
 * navigation — a minute of failures that name the symptom and not the cause.
 *
 * Only a failure to CONNECT means "not running" (the port is closed, the host does not resolve), and
 * only that fails the run. A server that accepted the connection and has not answered within the
 * budget is up and busy — a cold `next dev` spends 20s and more compiling its first route — so a
 * timeout is reported and the run carries on: the specs' own budgets judge a slow page, and a
 * preflight that called it "down" would abort exactly the run that was about to work. ANY response
 * counts as up: this asks whether something is listening, not whether it is healthy. It runs for the
 * logged-out specs too, because the signup page they visit asks the API for its mode.
 */
async function preflight(baseURL: string) {
  const targets = [
    { name: 'web app', url: baseURL },
    { name: 'API', url: `${API_BASE}/health` },
  ];
  const down: string[] = [];
  for (const { name, url } of targets) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(PREFLIGHT_TIMEOUT_MS), redirect: 'manual' });
    } catch (error) {
      if (error instanceof Error && error.name === 'TimeoutError') {
        console.warn(
          `E2E preflight: the ${name} at ${url} accepted the connection but has not answered in ` +
            `${PREFLIGHT_TIMEOUT_MS / 1000}s (a cold compile?). Continuing.`,
        );
      } else {
        down.push(`the ${name} at ${url}`);
      }
    }
  }
  if (down.length > 0) {
    throw new Error(
      `E2E preflight: nothing is listening at ${down.join(' or ')}. Start the web and API servers ` +
        `(\`pnpm dev\` from the repo root), or point PLAYWRIGHT_BASE_URL / E2E_API_URL at them.`,
    );
  }
}

/*
 * Authenticates once for the whole run and saves the browser state to tests/e2e/.auth (gitignored),
 * which the `authenticated` project loads. Without this, every spec would log in through the UI and
 * the suite's runtime would be mostly login.
 *
 * It drives the real login form rather than posting to NextAuth's credentials callback directly, and
 * that is deliberate: the callback route needs a CSRF token paired with its own cookie, and the
 * session cookie's NAME depends on whether the origin is secure — so a protocol-level login is three
 * assumptions about a library's internals, each of which fails by producing a 200 and no session. One
 * scripted form submission per run costs a second and assumes nothing. It also means a login that
 * breaks fails HERE, with a message saying so, instead of every authenticated spec failing at once
 * for reasons that look unrelated.
 *
 * Credentials come from E2E_EMAIL / E2E_PASSWORD. When they are unset the whole authenticated project
 * is skipped by the config and this stops after the preflight — the same env-gating the API's
 * integration suites use, so a fresh clone's `pnpm test:e2e` still passes on the logged-out specs.
 * E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD add a second session, for the admin pages (see
 * `ADMIN_AUTH_STATE_PATH`); unset, only the admin scans skip.
 */
async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://localhost:3000';
  await preflight(baseURL);

  const credentials = e2eCredentials();
  // A stale state file from a previous run must never survive a failed setup: a spec would load it
  // and fail against whatever session it happens to hold. Both go, whichever accounts are set now.
  for (const path of [AUTH_STATE_PATH, ADMIN_AUTH_STATE_PATH]) {
    if (existsSync(path)) rmSync(path);
  }
  if (!credentials) return;
  mkdirSync(dirname(AUTH_STATE_PATH), { recursive: true });

  const browser = await chromium.launch();
  try {
    await signIn(browser, baseURL, credentials, AUTH_STATE_PATH, 'E2E_EMAIL / E2E_PASSWORD');
    const admin = e2eAdminCredentials();
    if (admin) {
      await signIn(
        browser,
        baseURL,
        admin,
        ADMIN_AUTH_STATE_PATH,
        'E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD',
        {
          mustBeAdmin: true,
        },
      );
    }
  } finally {
    await browser.close();
  }
}

// Signs one account in through the form, verifies the session, and saves it to `statePath`. An admin
// session is also checked to BE one: an account without `is_admin` gets the not-found page on every
// admin route, and each admin scan would fail on that instead of on this one stated cause.
async function signIn(
  browser: Browser,
  baseURL: string,
  credentials: E2ECredentials,
  statePath: string,
  envNames: string,
  { mustBeAdmin = false }: { mustBeAdmin?: boolean } = {},
) {
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();

  try {
    await page.goto(LOGIN);
    await page.getByTestId('login-email-input').fill(credentials.email);
    await page.getByTestId('login-password-input').fill(credentials.password);
    await page.getByTestId('login-submit').click();

    /*
     * The verification is the point of the whole function, and it has to SAY what went wrong. A login
     * that fails leaves the page on /login showing an inline error, and saving that state would hand
     * every authenticated spec a logged-out browser — which fails as a redirect to /login in each of
     * them, N confusing failures away from the one real cause.
     *
     * Two distinct failures, hence two checks. Rejected credentials never leave /login at all, so the
     * wait times out — caught here and re-thrown with the reason, because a bare
     * `waitForURL exceeded 15000ms` names the symptom and not one of its causes. A session that is
     * accepted and then unusable (a stale epoch, an unverified account) does leave /login and gets
     * bounced back from the protected route, which the second check catches.
     */
    try {
      await page.waitForURL((url) => url.pathname !== LOGIN, { timeout: LOGIN_TIMEOUT_MS });
    } catch {
      throw new Error(
        `E2E login was rejected for ${credentials.email}: the form stayed on ${LOGIN}. ` +
          `Check ${envNames}, and that the app at ${baseURL} can reach the API.`,
      );
    }

    await page.goto(PROTECTED_PATH);
    await page.waitForLoadState('domcontentloaded');
    if (new URL(page.url()).pathname === LOGIN) {
      throw new Error(
        `E2E login succeeded for ${credentials.email} but the session is not usable: ` +
          `${PROTECTED_PATH} bounced back to ${LOGIN}. The account may be unverified.`,
      );
    }

    if (mustBeAdmin) {
      await page.goto(ADMIN_PATH);
      /*
       * Wait for the page to END in one of its two outcomes, not for `load`: the route streams behind
       * a skeleton, and a `notFound()` there is swapped in after hydration — at `load` neither the
       * not-found page nor the form is on screen yet, and a count taken then passes for anyone.
       */
      await page.locator(`${NOT_FOUND}, ${ADMIN_CONTENT}`).first().waitFor({
        timeout: LOGIN_TIMEOUT_MS,
      });
      if ((await page.locator(NOT_FOUND).count()) > 0) {
        throw new Error(
          `E2E admin account ${credentials.email} is not an admin: ${ADMIN_PATH} rendered the ` +
            `not-found page. Set users.is_admin for it in the database the API uses (and run the ` +
            `API with SIGNUP_MODE=invite, the only mode with an invite admin).`,
        );
      }
    }

    await context.storageState({ path: statePath });
  } finally {
    await context.close();
  }
}

export default globalSetup;
