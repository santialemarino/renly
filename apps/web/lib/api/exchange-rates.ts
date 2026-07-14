import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SupportedCurrenciesRaw {
  currencies: string[];
}

// --- API functions ---

export async function getSupportedCurrencies(): Promise<string[]> {
  const res = await authenticatedFetch('/exchange-rates/currencies', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch supported currencies');
  const raw: SupportedCurrenciesRaw = await res.json();
  return raw.currencies;
}
