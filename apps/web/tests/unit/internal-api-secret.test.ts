import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  internalApiSecretWarning,
  MIN_INTERNAL_API_SECRET_LENGTH,
} from '@/lib/internal-api-secret';
import { register } from '../../instrumentation';

/*
 * A web INTERNAL_API_SECRET shorter than the API accepts can never match it, and the only symptom is
 * that every server-side call shares one rate-limit bucket again. The server warns once at startup.
 */

vi.mock('@sentry/nextjs', () => ({ captureRequestError: vi.fn() }));
vi.mock('../../sentry.server.config', () => ({}));

describe('internalApiSecretWarning', () => {
  it('is silent when the secret is unset or empty (forwarding off)', () => {
    expect(internalApiSecretWarning(undefined)).toBeNull();
    expect(internalApiSecretWarning('')).toBeNull();
  });

  it('warns one character below the minimum and not at it', () => {
    expect(internalApiSecretWarning('x'.repeat(MIN_INTERNAL_API_SECRET_LENGTH - 1))).toContain(
      `at least ${MIN_INTERNAL_API_SECRET_LENGTH}`,
    );
    expect(internalApiSecretWarning('x'.repeat(MIN_INTERNAL_API_SECRET_LENGTH))).toBeNull();
  });

  it('never prints the secret', () => {
    const secret = 'short-secret-value';
    expect(internalApiSecretWarning(secret)).not.toContain(secret);
  });
});

describe('server startup', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('logs the warning on the node runtime when the secret is too short', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubEnv('NEXT_RUNTIME', 'nodejs');
    vi.stubEnv('INTERNAL_API_SECRET', 'too-short');
    await register();
    expect(warn).toHaveBeenCalledOnce();
    expect(warn.mock.calls[0]?.[0]).toContain('INTERNAL_API_SECRET');
  });

  it('logs nothing when the secret is long enough', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubEnv('NEXT_RUNTIME', 'nodejs');
    vi.stubEnv('INTERNAL_API_SECRET', 'x'.repeat(MIN_INTERNAL_API_SECRET_LENGTH));
    await register();
    expect(warn).not.toHaveBeenCalled();
  });
});
