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

/*
 * The ADMIN session, a second saved state beside the harness one. The admin pages (`/admin`,
 * `/admin/feedback`) render only for a user with `users.is_admin` and show anyone else the not-found
 * page, so the harness account cannot reach them — and making IT an admin would change what every
 * other authenticated spec sees. A second account, flagged in SQL, signs in once in globalSetup like
 * the first, and the specs that need it load this file with `test.use({ storageState: … })`.
 */
export const ADMIN_AUTH_STATE_PATH = join(import.meta.dirname, '../.auth/admin-storage-state.json');

/*
 * The admin account, from E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD, or null when either is unset — the
 * same gating as `e2eCredentials`: unset, the admin scans skip (a local run) and globalSetup signs in
 * only the harness account. CI sets both, and refuses a run in which anything skipped.
 */
export function e2eAdminCredentials(): E2ECredentials | null {
  // eslint-disable-next-line turbo/no-undeclared-env-vars
  const email = process.env.E2E_ADMIN_EMAIL;
  // eslint-disable-next-line turbo/no-undeclared-env-vars
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) return null;
  return { email, password };
}

/*
 * The RENAME session, a third saved state. The account-name spec renames its account, and PATCH /me
 * allows five renames an hour, counted in the API's memory per account: on the harness account a CI
 * retry could run past that, and a refused restore would leave the account every other spec reads
 * renamed. Its own account takes both risks off the harness. It signs in once in globalSetup like the
 * other two, so no spec spends a login on it.
 */
export const RENAME_AUTH_STATE_PATH = join(
  import.meta.dirname,
  '../.auth/rename-storage-state.json',
);

/*
 * The rename account, from E2E_RENAME_EMAIL / E2E_RENAME_PASSWORD, or null when either is unset — the
 * same gating as the admin one: unset, the account-name spec skips (a local run); CI sets both.
 */
export function e2eRenameCredentials(): E2ECredentials | null {
  // eslint-disable-next-line turbo/no-undeclared-env-vars
  const email = process.env.E2E_RENAME_EMAIL;
  // eslint-disable-next-line turbo/no-undeclared-env-vars
  const password = process.env.E2E_RENAME_PASSWORD;
  if (!email || !password) return null;
  return { email, password };
}
