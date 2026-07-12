import { create } from 'zustand';

import { COOKIE_MAX_AGE_1_YEAR } from '@/config/constants';

export const ORIGINAL_CURRENCY = 'original';
export const ACTIVE_CURRENCY_COOKIE = 'active-currency';
export const CURRENCY_COLLAPSED_COOKIE = 'currency-collapsed';

// Resolves the page display currency from the active-currency cookie: a concrete
// currency code when one is active, or undefined when viewing original currencies.
export function resolveActiveCurrency(
  cookieStore: { get: (name: string) => { value: string } | undefined },
  primaryCurrency: string,
): string | undefined {
  const saved = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const active = saved || primaryCurrency;
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
