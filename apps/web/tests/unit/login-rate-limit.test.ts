import { CredentialsSignin } from 'next-auth';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { authConfig } from '@/auth.config';
import { decodeApiError } from '@/lib/i18n/api-errors';

/*
 * A rate-limited login must reach the form as "too many attempts, try again in N", not as wrong
 * credentials. The credentials provider's `authorize` is where the API's 429 is turned into what
 * Auth.js forwards to the browser — a `CredentialsSignin` whose `code` carries the parsed error — so
 * this drives it with the API's real 429 shape and decodes what the form would receive.
 */

type Authorize = (credentials: Record<string, unknown>) => Promise<unknown>;

const provider = authConfig.providers[0] as unknown as { options: { authorize: Authorize } };
const authorize = provider.options.authorize;
const CREDENTIALS = { email: 'me@example.com', password: 'secret-password', rememberMe: 'false' };

function stubLogin(response: Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => response),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('login authorize', () => {
  it('turns a 429 into a sign-in error carrying the rate-limit code and wait', async () => {
    stubLogin(
      new Response(
        JSON.stringify({
          detail: 'Too many requests. Please slow down and try again later.',
          code: 'rate_limited',
        }),
        { status: 429, headers: { 'Retry-After': '42' } },
      ),
    );
    const error = await authorize(CREDENTIALS).then(
      () => null,
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(CredentialsSignin);
    const decoded = decodeApiError((error as CredentialsSignin).code);
    expect(decoded?.code).toBe('rate_limited');
    expect(decoded?.params).toEqual({ retry_after_minutes: 1 });
  });

  it('still answers wrong credentials (401) with null, which the form reads as invalid', async () => {
    stubLogin(
      new Response(JSON.stringify({ detail: 'Invalid credentials', code: 'invalid_credentials' }), {
        status: 401,
      }),
    );
    expect(await authorize(CREDENTIALS)).toBeNull();
  });
});
