import { describe, expect, it } from 'vitest';

import {
  ACTIVE_CURRENCY_COOKIE,
  ORIGINAL_CURRENCY,
  resolveActiveCurrency,
  resolveCurrencySelection,
} from '@/lib/stores/currency-store';

/*
 * The display currency is read in two places: the protected layout (which pill the sidebar's switcher
 * shows selected) and every page (what the figures are converted to). Both must read a MISSING cookie
 * the same way — as the primary currency. They once disagreed: the switcher showed the primary selected
 * while the pages showed original amounts, and clicking the selected pill could not fix it.
 */

const PRIMARY = 'ARS';
const CHOICES = [PRIMARY, 'USD', ORIGINAL_CURRENCY];
const SETTINGS = { primaryCurrency: PRIMARY, secondaryCurrency: 'USD' };

function cookies(value?: string) {
  return {
    get: (name: string) =>
      name === ACTIVE_CURRENCY_COOKIE && value !== undefined ? { value } : undefined,
  };
}

describe('resolveCurrencySelection (the switcher)', () => {
  it('selects the primary currency when nothing was chosen', () => {
    expect(resolveCurrencySelection(undefined, CHOICES, PRIMARY)).toBe(PRIMARY);
    expect(resolveCurrencySelection('', CHOICES, PRIMARY)).toBe(PRIMARY);
  });

  it('keeps an explicit choice, original included', () => {
    expect(resolveCurrencySelection('USD', CHOICES, PRIMARY)).toBe('USD');
    expect(resolveCurrencySelection(ORIGINAL_CURRENCY, CHOICES, PRIMARY)).toBe(ORIGINAL_CURRENCY);
  });

  it('falls back to the primary for a choice that is no longer offered', () => {
    expect(resolveCurrencySelection('EUR', CHOICES, PRIMARY)).toBe(PRIMARY);
  });
});

describe('resolveActiveCurrency (the pages)', () => {
  it('converts to the primary currency when nothing was chosen', () => {
    expect(resolveActiveCurrency(cookies(), SETTINGS)).toBe(PRIMARY);
    expect(resolveActiveCurrency(cookies(''), SETTINGS)).toBe(PRIMARY);
  });

  it('converts to an explicitly chosen currency', () => {
    expect(resolveActiveCurrency(cookies('USD'), SETTINGS)).toBe('USD');
  });

  it('shows original amounts only when "original" was chosen', () => {
    expect(resolveActiveCurrency(cookies(ORIGINAL_CURRENCY), SETTINGS)).toBeUndefined();
  });

  it('converts to the primary once the chosen currency is no longer one of the user’s', () => {
    // The secondary was USD when it was chosen, and is EUR now: the sidebar and the dashboards fall
    // back to the primary, and so must every list page.
    const changed = { primaryCurrency: PRIMARY, secondaryCurrency: 'EUR' };
    expect(resolveActiveCurrency(cookies('USD'), changed)).toBe(PRIMARY);
    expect(resolveActiveCurrency(cookies('USD'), { ...changed, secondaryCurrency: null })).toBe(
      PRIMARY,
    );
  });

  it('agrees with the switcher for a missing cookie', () => {
    expect(resolveActiveCurrency(cookies(), SETTINGS)).toBe(
      resolveCurrencySelection(undefined, CHOICES, PRIMARY),
    );
  });
});
