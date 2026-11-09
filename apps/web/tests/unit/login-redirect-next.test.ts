import { describe, expect, it, vi } from 'vitest';

import { authConfig } from '@/auth.config';
import { ROUTES } from '@/config/routes';
import { safeNextPath } from '@/lib/utils/safe-next-path';

/*
 * A logged-out visitor who opens a deep link is sent to /login, and must land back on that link once
 * signed in. The edge check once redirected to a bare /login, so every deep link (a notification email,
 * a bookmark) ended on the dashboard instead. The page rides along as `?next=`, and /login follows it
 * only through safeNextPath — which these tests also hold to the app's own origin.
 */

vi.mock('server-only', () => ({}));
vi.mock('next/headers', () => ({ headers: async () => new Headers() }));

type Authorized = (params: {
  auth: { user?: unknown } | null;
  request: { nextUrl: URL };
}) => Response | boolean;

const authorized = authConfig.callbacks!.authorized as unknown as Authorized;
const ORIGIN = 'https://renly.test';

function visit(path: string): Response | boolean {
  return authorized({ auth: null, request: { nextUrl: new URL(path, ORIGIN) } });
}

describe('the logged-out redirect to /login', () => {
  it('carries the requested page and its query as `next`', () => {
    const response = visit('/shared/12?tab=pots');
    expect(response).toBeInstanceOf(Response);
    const location = new URL((response as Response).headers.get('location')!);
    expect(location.origin).toBe(ORIGIN);
    expect(location.pathname).toBe(ROUTES.auth.login);
    expect(location.searchParams.get('next')).toBe('/shared/12?tab=pots');
    // What /login will then follow.
    expect(safeNextPath(location.searchParams.get('next')!)).toBe('/shared/12?tab=pots');
  });

  it('carries a top-level protected route too', () => {
    const location = new URL((visit(ROUTES.expenses) as Response).headers.get('location')!);
    expect(location.searchParams.get('next')).toBe(ROUTES.expenses);
  });

  it('never makes an off-site address out of a crafted path', () => {
    // A path that a naive concatenation would turn into a protocol-relative URL.
    const response = visit('/dashboard/..//evil.example');
    if (response instanceof Response) {
      const next = new URL(response.headers.get('location')!).searchParams.get('next');
      const followed = safeNextPath(next ?? undefined);
      expect(followed === null || followed.startsWith('/')).toBe(true);
      expect(followed ?? '').not.toMatch(/^\/\//);
    }
  });
});
