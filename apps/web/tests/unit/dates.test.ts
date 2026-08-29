import { describe, expect, it } from 'vitest';

import { isIsoDate } from '@/lib/utils/dates';

/*
 * The date a guided flow is priced at arrives from a URL, which means it arrives from anywhere. It is
 * passed straight to the API as `as_of_date`, so a value that merely LOOKS like a date reaches the
 * backend and comes back a 422 with nothing on screen to act on.
 */
describe('isIsoDate', () => {
  it('accepts a real calendar date', () => {
    expect(isIsoDate('2026-08-28')).toBe(true);
    expect(isIsoDate('2024-02-29')).toBe(true);
  });

  it('rejects a date-shaped string that is not a date', () => {
    // The case a shape check alone lets through: February has no 31st, and JS rolls it forward to
    // 2026-03-03 rather than failing — so the round-trip is what catches it.
    expect(isIsoDate('2026-02-31')).toBe(false);
    expect(isIsoDate('2026-13-01')).toBe(false);
    expect(isIsoDate('2025-02-29')).toBe(false);
  });

  it('rejects anything not in YYYY-MM-DD form', () => {
    expect(isIsoDate('2026-8-28')).toBe(false);
    expect(isIsoDate('28/08/2026')).toBe(false);
    expect(isIsoDate('2026-08-28T00:00:00Z')).toBe(false);
    expect(isIsoDate('')).toBe(false);
    expect(isIsoDate('nonsense')).toBe(false);
  });
});
