import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SettingsRaw {
  primary_currency: string | null;
  secondary_currency: string | null;
  preferred_currencies: string[] | null;
  period_presets: string[] | null;
  max_groups: number | null;
  group_warning_pct: number | null;
  dollar_rate_preference: string | null;
}

// --- Frontend types (camelCase) ---

export interface SettingsData {
  primaryCurrency: string | null;
  secondaryCurrency: string | null;
  preferredCurrencies: string[] | null;
  periodPresets: string[] | null;
  maxGroups: number | null;
  groupWarningPct: number | null;
  dollarRatePreference: string | null;
}

// --- Mappers ---

function mapSettings(raw: SettingsRaw): SettingsData {
  return {
    primaryCurrency: raw.primary_currency,
    secondaryCurrency: raw.secondary_currency,
    preferredCurrencies: raw.preferred_currencies,
    periodPresets: raw.period_presets,
    maxGroups: raw.max_groups,
    groupWarningPct: raw.group_warning_pct,
    dollarRatePreference: raw.dollar_rate_preference,
  };
}

// --- API functions ---

export async function getSettings(): Promise<SettingsData> {
  const res = await authenticatedFetch('/settings', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch settings');
  return mapSettings(await res.json());
}
