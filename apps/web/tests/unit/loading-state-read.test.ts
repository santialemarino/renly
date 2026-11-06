import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LOADING_STATE_READ_TIMEOUT_MS, PAGE_SKELETON_DELAY_MS } from '@/lib/constants/animations';
import { readForLoadingState } from '@/lib/utils/loading-state-read';

/*
 * A settings-type loading state draws from the page's own reads, and a slow or hanging API must not
 * keep it from showing: past the timeout, or on an error, it draws with the defaults.
 */

describe('readForLoadingState', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("returns the read's value when it arrives in time", async () => {
    await expect(readForLoadingState(Promise.resolve('real'), 'fallback')).resolves.toBe('real');
  });

  it('falls back when the read fails', async () => {
    await expect(readForLoadingState(Promise.reject(new Error('down')), 'fallback')).resolves.toBe(
      'fallback',
    );
  });

  it('falls back when the read hangs past the timeout, and not before', async () => {
    const hanging = new Promise<string>(() => undefined);
    let settled: string | undefined;
    void readForLoadingState(hanging, 'fallback').then((value) => (settled = value));

    await vi.advanceTimersByTimeAsync(LOADING_STATE_READ_TIMEOUT_MS - 1);
    expect(settled).toBeUndefined();
    await vi.advanceTimersByTimeAsync(1);
    expect(settled).toBe('fallback');
  });

  it('keeps the timeout under the loading state delay, so it never adds more than that', () => {
    expect(LOADING_STATE_READ_TIMEOUT_MS).toBeLessThan(PAGE_SKELETON_DELAY_MS);
  });
});
