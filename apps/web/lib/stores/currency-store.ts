import { create } from 'zustand';

import { COOKIE_MAX_AGE_1_YEAR } from '@/config/constants';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';

export const ORIGINAL_CURRENCY = 'original';
export const ACTIVE_CURRENCY_COOKIE = 'active-currency';
export const CURRENCY_COLLAPSED_COOKIE = 'currency-collapsed';

// The two settings the display currency depends on.
interface CurrencySettings {
  primaryCurrency: string | null;
  secondaryCurrency: string | null;
}

/*
 * Which of the switcher's choices is selected: the saved one while it is still among them, the primary
 * currency otherwise. "Otherwise" includes having NO cookie at all (a first visit, cleared cookies,
 * another device), so the sidebar and every page read a missing choice the same way. "Original" is only
 * ever an explicit choice.
 */
export function resolveCurrencySelection(
  saved: string | undefined,
  displayCurrencies: string[],
  primaryCurrency: string,
): string {
  return saved && displayCurrencies.includes(saved) ? saved : primaryCurrency;
}

// The switcher's choices for these settings: the primary, the secondary when there is one, "original".
export function displayCurrenciesFor(settings: CurrencySettings | null): string[] {
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const secondary = settings?.secondaryCurrency ?? null;
  return secondary ? [primary, secondary, ORIGINAL_CURRENCY] : [primary, ORIGINAL_CURRENCY];
}

/*
 * Resolves the page display currency from the active-currency cookie: a concrete currency code, or
 * undefined when the user chose to view original currencies. Through resolveCurrencySelection, so a
 * missing cookie AND one naming a currency that is no longer among the user's (a changed secondary)
 * both read as the primary — as the switcher and the dashboards read them.
 */
export function resolveActiveCurrency(
  cookieStore: { get: (name: string) => { value: string } | undefined },
  settings: CurrencySettings | null,
): string | undefined {
  const choices = displayCurrenciesFor(settings);
  const active = resolveCurrencySelection(
    cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value,
    choices,
    choices[0]!,
  );
  return active !== ORIGINAL_CURRENCY ? active : undefined;
}

interface CurrencyState {
  activeCurrency: string;
  setActiveCurrency: (currency: string) => void;
}

export const useCurrencyStore = create<CurrencyState>((set) => ({
  activeCurrency: ORIGINAL_CURRENCY,

  setActiveCurrency: (currency) => {
    document.cookie = `${ACTIVE_CURRENCY_COOKIE}=${currency}; path=/; max-age=${COOKIE_MAX_AGE_1_YEAR}`;
    set({ activeCurrency: currency });
  },
}));
