import { afterEach, describe, expect, it, vi } from 'vitest';

/*
 * The period control's default presets. A built image never receives NEXT_PUBLIC_PERIOD_PRESET_*
 * (inlined at build time, and the Docker build has no .env), so the code must offer 1M/3M/6M/YTD on
 * its own; the env vars stay an override. The module reads env at import, so each case re-imports it.
 */

const KEYS = [1, 2, 3, 4].map((n) => `NEXT_PUBLIC_PERIOD_PRESET_${n}`);

async function load(env: Record<string, string | undefined>) {
  vi.resetModules();
  for (const key of KEYS) vi.stubEnv(key, env[key] ?? '');
  return import('@/lib/constants/period-presets');
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('period presets', () => {
  it('fall back to 1M, 3M, 6M and YTD when no env var is set', async () => {
    const presets = await load({});
    expect(presets.PERIOD_PRESETS.map((p) => p.code)).toEqual(['1m', '3m', '6m', 'ytd', 'all']);
    expect(presets.DEFAULT_PERIOD_PRESETS).toBe('1M, 3M, 6M, YTD');
  });

  it('take the env vars as an override, in slot order', async () => {
    const presets = await load({
      NEXT_PUBLIC_PERIOD_PRESET_1: '1Y',
      NEXT_PUBLIC_PERIOD_PRESET_3: '2A',
    });
    expect(presets.PERIOD_PRESETS.map((p) => p.code)).toEqual(['1y', '2y', 'all']);
    expect(presets.DEFAULT_PERIOD_PRESETS).toBe('1Y, 2A');
  });
});
