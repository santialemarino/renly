import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname } from 'node:path';
import { chromium, type FullConfig } from '@playwright/test';

import { AUTH_STATE_PATH, e2eCredentials } from './helpers/auth';

// Route literals mirror apps/web/config/routes.ts. Kept local like the two logged-out specs' — the
// Playwright loader resolves no build-time path aliases.
const LOGIN = '/login';
const PROTECTED_PATH = '/dashboard';

// Long enough for a cold dev server's first compile of /login, short enough that a wrong password
// fails the run in seconds rather than making it look hung.
const LOGIN_TIMEOUT_MS = 15_000;

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
 * is skipped by the config, so this never runs — the same env-gating the API's integration suites use,
 * so a fresh clone's `pnpm test:e2e` still passes on the logged-out specs alone.
 */
async function globalSetup(config: FullConfig) {
  const credentials = e2eCredentials();
  if (!credentials) return;

  // A stale state file from a previous run must never survive a failed setup: the authenticated
  // project would load it and fail against whatever session it happens to hold.
  if (existsSync(AUTH_STATE_PATH)) rmSync(AUTH_STATE_PATH);
  mkdirSync(dirname(AUTH_STATE_PATH), { recursive: true });

  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://localhost:3000';
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });

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
          `Check E2E_EMAIL / E2E_PASSWORD, and that the app at ${baseURL} can reach the API.`,
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

    await page.context().storageState({ path: AUTH_STATE_PATH });
  } finally {
    await browser.close();
  }
}

export default globalSetup;
