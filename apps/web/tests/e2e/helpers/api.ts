import { expect, type APIRequestContext } from '@playwright/test';

import { e2eCredentials } from './auth';

// Where the API is, for what a spec cannot do or see through the DOM. A shell var like E2E_EMAIL and
// E2E_PASSWORD — Playwright reads no dotenv file, so it stays out of `.env.example` too — with the
// local default that makes it optional. `||` rather than `??` so an empty value falls back.
// eslint-disable-next-line turbo/no-undeclared-env-vars
export const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

// Logs into the API directly for its own bearer token. The browser's session is a NextAuth cookie on
// the WEB origin, which the API never sees — so a request context cannot borrow it, and the harness
// credentials are the only way in.
export async function apiToken(request: APIRequestContext): Promise<string> {
  const credentials = e2eCredentials();
  // The authenticated project only exists when both are set, so this cannot be null here — the check
  // is what makes that a type fact rather than a comment.
  if (credentials === null) throw new Error('E2E_EMAIL / E2E_PASSWORD are required for this spec');
  const response = await request.post(`${API_BASE}/auth/login`, { data: credentials });
  expect(response.ok(), `login to ${API_BASE} failed with ${response.status()}`).toBe(true);
  return (await response.json()).access_token;
}
