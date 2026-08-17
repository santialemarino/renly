import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SupportedCurrenciesRaw {
  currencies: string[];
}

interface ExchangeRateRaw {
  id: number;
  date: string;
  pair: string;
  rate: string;
  source: string;
}

interface LatestRatesRaw {
  rates: ExchangeRateRaw[];
  last_update: string | null;
}

// --- Frontend types (camelCase) ---

export interface ExchangeRate {
  date: string;
  pair: string;
  rate: string;
}

export interface LatestRates {
  rates: ExchangeRate[];
  lastUpdate: string | null;
}

// --- Mappers ---

function mapExchangeRate(raw: ExchangeRateRaw): ExchangeRate {
  return { date: raw.date, pair: raw.pair, rate: raw.rate };
}

function mapLatestRates(raw: LatestRatesRaw): LatestRates {
  return { rates: raw.rates.map(mapExchangeRate), lastUpdate: raw.last_update };
}

// --- API functions ---

export async function getSupportedCurrencies(): Promise<string[]> {
  const res = await authenticatedFetch('/exchange-rates/currencies', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch supported currencies');
  const raw: SupportedCurrenciesRaw = await res.json();
  return raw.currencies;
}

export async function getLatestRates(): Promise<LatestRates> {
  const res = await authenticatedFetch('/exchange-rates/latest', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch latest exchange rates');
  const raw: LatestRatesRaw = await res.json();
  return mapLatestRates(raw);
}
