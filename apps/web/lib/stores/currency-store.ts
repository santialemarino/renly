import { create } from 'zustand';

export const ORIGINAL_CURRENCY = 'original';
export const ACTIVE_CURRENCY_COOKIE = 'active-currency';

const COOKIE_MAX_AGE_1_YEAR = 60 * 60 * 24 * 365;

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
