import { expect, request } from '@playwright/test';

import { AUTH_STATE_PATH } from './auth';

/*
 * Direct API access for the authenticated specs: seeding the data a spec is not testing, or reading a
 * figure the DOM cannot show.
 */

// Where the web app runs. `||` rather than `??` so an empty `PLAYWRIGHT_BASE_URL=""` falls back
// instead of producing an unusable empty base URL. The Playwright config reads it from here too, so
// the browser and this helper cannot point at different servers.
// eslint-disable-next-line turbo/no-undeclared-env-vars
export const WEB_BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

// Where the API is. A shell var like E2E_EMAIL and E2E_PASSWORD, since Playwright reads no dotenv
// file, so it stays out of `.env.example` too. The local default makes it optional.
// eslint-disable-next-line turbo/no-undeclared-env-vars
export const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

/*
 * The API bearer token of the session globalSetup already signed in, read from NextAuth's
 * `/api/auth/session` with the saved storage state (the session callback exposes it as
 * `user.accessToken`).
 *
 * Deliberately NOT a fresh `POST /auth/login`. The API allows five logins a minute, and Playwright
 * restarts the worker after every failed test, which re-runs each `beforeAll`. A spec that logged in
 * there spent one login per failure, so after a few real failures every later test reported
 * `login … failed with 429` instead of the regression it exists to catch. globalSetup's form login is
 * now the only login in a run.
 */
export async function apiToken(): Promise<string> {
  const context = await request.newContext({ baseURL: WEB_BASE, storageState: AUTH_STATE_PATH });
  try {
    const response = await context.get('/api/auth/session');
    expect(
      response.ok(),
      `reading the session from ${WEB_BASE} failed with ${response.status()}`,
    ).toBe(true);
    const token: unknown = (await response.json())?.user?.accessToken;
    expect(
      typeof token === 'string' && token.length > 0,
      'the saved session carries no API access token; did globalSetup sign in?',
    ).toBe(true);
    return token as string;
  } finally {
    await context.dispose();
  }
}
