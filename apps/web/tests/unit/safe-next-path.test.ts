import { describe, expect, it } from 'vitest';

import { ALL_ROUTE_PATHS, ROUTES } from '@/config/routes';
import { safeNextPath } from '@/lib/utils/safe-next-path';

/*
 * `?next=` is the one place this app takes a redirect target from the URL (a group-invite link opened
 * without a session bounces through /login and back). That makes it the classic open-redirect surface,
 * so the guard is an allowlist against the app's own routes rather than a blocklist of tricks — and
 * these tests are written to fail if it ever becomes the latter.
 */
describe('safeNextPath', () => {
  it('accepts an app route and keeps its query string', () => {
    // The token lives in the query, so dropping it would break the flow this exists for.
    const next = `${ROUTES.auth.joinGroup}?token=abc123`;
    expect(safeNextPath(next)).toBe('/join?token=abc123');
  });

  it('accepts every route the app declares', () => {
    for (const path of ALL_ROUTE_PATHS) {
      expect(safeNextPath(path)).toBe(path);
    }
  });

  it.each([
    ['undefined', undefined],
    ['empty', ''],
    ['an unknown path', '/not-a-route'],
    ['a path prefix that is not itself a route', '/shared/12'],
  ])('rejects %s', (_label, value) => {
    expect(safeNextPath(value)).toBeNull();
  });

  /*
   * Every one of these fails for the SAME reason — its pathname is not a Renly route — which is the
   * point of the allowlist. A sanitizer would need a rule per row here and would still miss the next
   * encoding someone invents.
   */
  it.each([
    ['an absolute off-site URL', 'https://evil.example/login'],
    ['a protocol-relative URL', '//evil.example'],
    ['a protocol-relative URL with a path', '//evil.example/login'],
    ['a backslash variant', '\\\\evil.example'],
    ['a javascript: URL', 'javascript:alert(1)'],
    ['a data: URL', 'data:text/html,<script>alert(1)</script>'],
    ['an encoded host', 'https:%2F%2Fevil.example'],
    ['an off-site URL whose path IS a route', 'https://evil.example/dashboard'],
    ['userinfo pointing at another host', 'https://renly.invalid@evil.example/dashboard'],
    // The parse base itself. An absolute URL is rejected even when it names the sentinel host and a
    // real route — nothing accepted may carry a scheme, so the base can never leak into a redirect.
    ['an absolute URL naming the parse base', 'https://renly.invalid/dashboard'],
    ['a backslash-escaped protocol-relative URL', '/\\evil.example'],
  ])('rejects %s', (_label, value) => {
    expect(safeNextPath(value)).toBeNull();
  });

  it('returns the normalised path, not the input string', () => {
    // Dot segments resolve BEFORE the allowlist check, so a non-route segment cannot ride along; and
    // the returned value is what was checked, rather than whatever the caller happened to write.
    expect(safeNextPath('/expenses/../dashboard')).toBe('/dashboard');
    expect(safeNextPath('/not-a-route/../dashboard')).toBe('/dashboard');
  });

  it('drops a fragment', () => {
    expect(safeNextPath('/dashboard#anything')).toBe('/dashboard');
    expect(safeNextPath(`${ROUTES.auth.joinGroup}?token=abc#frag`)).toBe('/join?token=abc');
  });

  it('never returns a value carrying an origin', () => {
    // The belt to the allowlist's braces: even for an accepted input, only pathname + search comes
    // back, so the result cannot address another host however it was written.
    for (const candidate of [ROUTES.dashboard, `${ROUTES.auth.joinGroup}?token=x`]) {
      const result = safeNextPath(candidate);
      expect(result).not.toBeNull();
      expect(result!.startsWith('/')).toBe(true);
      expect(result!.startsWith('//')).toBe(false);
      expect(result).not.toContain('://');
    }
  });
});
