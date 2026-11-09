import { create } from 'zustand';

import { COOKIE_MAX_AGE_1_YEAR } from '@/config/constants';

export const ORIGINAL_CURRENCY = 'original';
export const ACTIVE_CURRENCY_COOKIE = 'active-currency';
export const CURRENCY_COLLAPSED_COOKIE = 'currency-collapsed';

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

// Resolves the page display currency from the active-currency cookie: a concrete currency code (the
// primary when nothing was chosen), or undefined when the user chose to view original currencies.
export function resolveActiveCurrency(
  cookieStore: { get: (name: string) => { value: string } | undefined },
  primaryCurrency: string,
): string | undefined {
  const active = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value || primaryCurrency;
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
