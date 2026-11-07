import { afterEach, describe, expect, it, vi } from 'vitest';

import { startRead } from '@/lib/utils/start-read';

/*
 * `startRead` lets a page start a read now and await it later, after something else that must win (a
 * `notFound()` on the record the page is about). Its two promises: the read's own outcome reaches the
 * place it is awaited unchanged, and a rejection that lands before then is not reported as unhandled.
 */

const flush = () => new Promise((resolve) => setImmediate(resolve));

afterEach(() => {
  vi.restoreAllMocks();
});

describe('startRead', () => {
  it('hands back the read itself, value and all', async () => {
    const read = Promise.resolve(42);
    const started = startRead(read);
    expect(started).toBe(read);
    await expect(started).resolves.toBe(42);
  });

  it('still throws where it is awaited', async () => {
    const started = startRead(Promise.reject(new Error('read failed')));
    await flush();
    await expect(started).rejects.toThrow('read failed');
  });

  it('is not an unhandled rejection while the page awaits something else first', async () => {
    const unhandled = vi.fn();
    process.on('unhandledRejection', unhandled);
    try {
      const started = startRead(Promise.reject(new Error('read failed')));
      // The page is busy with its first await; several turns pass before it reaches this read.
      for (let i = 0; i < 5; i += 1) await flush();
      expect(unhandled).not.toHaveBeenCalled();
      await expect(started).rejects.toThrow('read failed');
    } finally {
      process.off('unhandledRejection', unhandled);
    }
  });
});
