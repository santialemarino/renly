import { join } from 'node:path';

/*
 * Where globalSetup writes the authenticated browser state and the `authenticated` project reads it.
 * One constant so the two cannot drift, and the directory is gitignored — the file holds a live
 * session cookie for a real account.
 */
export const AUTH_STATE_PATH = join(import.meta.dirname, '../.auth/storage-state.json');

export interface E2ECredentials {
  email: string;
  password: string;
}

/*
 * The account the authenticated specs run as, from E2E_EMAIL / E2E_PASSWORD, or null when either is
 * unset. Null means "skip the authenticated project" rather than "fail": the same posture the API's
 * env-gated integration suites take, so `pnpm test:e2e` on a fresh clone with no seeded account still
 * runs the logged-out specs and exits 0.
 *
 * Both are read here rather than at each call site so there is exactly one definition of "configured",
 * and so the config and the setup can never disagree about whether to run.
 */
export function e2eCredentials(): E2ECredentials | null {
  // eslint-disable-next-line turbo/no-undeclared-env-vars
  const email = process.env.E2E_EMAIL;
  // eslint-disable-next-line turbo/no-undeclared-env-vars
  const password = process.env.E2E_PASSWORD;
  if (!email || !password) return null;
  return { email, password };
}
