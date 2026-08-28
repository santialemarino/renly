import { describe, expect, it } from 'vitest';

import { createFormatters } from '@/lib/i18n/create-formatters';

// The pure factory both useFormatters (client) and getFormatters (server) reuse. These assert the
// locale + timezone are actually bound across the set — a regression here is silent (wrong number
// format or wrong calendar day) since every consumer goes through the bound `fmt`.
describe('createFormatters', () => {
  it('binds the locale across the formatter set', () => {
    const es = createFormatters('es');
    expect(es.locale).toBe('es');
    expect(es.value(1000)).toBe('1.000');
    expect(es.ratio(1.5)).toBe('1,50');
    expect(es.sharePct(13.91)).toBe('13,91');
    expect(es.list(['A', 'B'])).toBe('A y B');
    expect(es.amount('1234.5', 'USD')).toBe('1.234,5');
  });

  it('binds the timezone into timestampDate (and only there)', () => {
    // 02:00 UTC Jul 16 is still Jul 15 in Los Angeles but Jul 16 in Sydney.
    expect(
      createFormatters('en', 'America/Los_Angeles').timestampDate('2026-07-16T02:00:00Z'),
    ).toBe('Jul 15, 2026');
    expect(createFormatters('en', 'Australia/Sydney').timestampDate('2026-07-16T02:00:00Z')).toBe(
      'Jul 16, 2026',
    );
    // A date-only value stays on the local-midnight anchor regardless of the bound timezone.
    expect(createFormatters('en', 'America/Los_Angeles').date('2026-07-16')).toBe('Jul 16, 2026');
  });

  it('exposes the date-only label helpers', () => {
    const en = createFormatters('en');
    expect(en.monthLong(2025, 5)).toBe('May');
    expect(en.monthYear('2025-01-31')).toBe('Jan 2025');
    const wd = en.weekdayDay('2025-01-06');
    expect(wd).toContain('Monday');
    expect(wd).toContain('6');
  });
});
