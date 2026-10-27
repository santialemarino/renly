import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CLIENT_IP_HEADER, INTERNAL_SECRET_HEADER, serverApiFetch } from '@/lib/server-api-fetch';

/*
 * Every call this server makes to the API names the visitor it is made for, so the API rate-limits
 * the visitor and not this server. The IP comes from this server's own request under
 * WEB_TRUSTED_PROXY_COUNT, and the shared secret goes with it; without the secret, or without an IP
 * the rule can trust, the call carries neither and the API keys it by this server, as before.
 */

const state = vi.hoisted(() => ({ requestHeaders: new Headers() }));

vi.mock('server-only', () => ({}));
vi.mock('next/headers', () => ({ headers: async () => state.requestHeaders }));

const SECRET = 's'.repeat(40);
const calls: { url: string; headers: Headers }[] = [];

beforeEach(() => {
  calls.length = 0;
  state.requestHeaders = new Headers({ 'x-forwarded-for': '9.9.9.9, 203.0.113.7' });
  vi.stubEnv('INTERNAL_API_SECRET', SECRET);
  vi.stubEnv('WEB_TRUSTED_PROXY_COUNT', '1');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, headers: new Headers(init.headers) });
      return new Response(null, { status: 204 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('serverApiFetch', () => {
  it('names the client and proves it with the secret', async () => {
    await serverApiFetch('/auth/login', { method: 'POST' });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.url.endsWith('/auth/login')).toBe(true);
    expect(calls[0]?.headers.get(CLIENT_IP_HEADER)).toBe('203.0.113.7');
    expect(calls[0]?.headers.get(INTERNAL_SECRET_HEADER)).toBe(SECRET);
  });

  it("keeps the caller's own headers", async () => {
    await serverApiFetch('/auth/me', {
      headers: { Authorization: 'Bearer token', 'Content-Type': 'application/json' },
    });
    expect(calls[0]?.headers.get('Authorization')).toBe('Bearer token');
    expect(calls[0]?.headers.get('Content-Type')).toBe('application/json');
    expect(calls[0]?.headers.get(CLIENT_IP_HEADER)).toBe('203.0.113.7');
  });

  it('a caller cannot set the forwarding headers itself', async () => {
    await serverApiFetch('/auth/login', {
      headers: { [CLIENT_IP_HEADER]: '198.51.100.1', [INTERNAL_SECRET_HEADER]: 'forged' },
    });
    expect(calls[0]?.headers.get(CLIENT_IP_HEADER)).toBe('203.0.113.7');
    expect(calls[0]?.headers.get(INTERNAL_SECRET_HEADER)).toBe(SECRET);
  });

  it('sends neither header without the secret', async () => {
    vi.stubEnv('INTERNAL_API_SECRET', '');
    await serverApiFetch('/auth/login', { method: 'POST' });
    expect(calls[0]?.headers.get(CLIENT_IP_HEADER)).toBeNull();
    expect(calls[0]?.headers.get(INTERNAL_SECRET_HEADER)).toBeNull();
  });

  it('sends neither header without a trusted proxy', async () => {
    vi.stubEnv('WEB_TRUSTED_PROXY_COUNT', '0');
    await serverApiFetch('/auth/login', { method: 'POST' });
    expect(calls[0]?.headers.get(CLIENT_IP_HEADER)).toBeNull();
    expect(calls[0]?.headers.get(INTERNAL_SECRET_HEADER)).toBeNull();
  });

  it('sends neither header when the request has no forwarded chain', async () => {
    state.requestHeaders = new Headers();
    await serverApiFetch('/auth/login', { method: 'POST' });
    expect(calls[0]?.headers.get(CLIENT_IP_HEADER)).toBeNull();
    expect(calls[0]?.headers.get(INTERNAL_SECRET_HEADER)).toBeNull();
  });
});
