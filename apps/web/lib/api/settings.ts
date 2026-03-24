import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SettingsRaw {
  primary_currency: string | null;
  secondary_currency: string | null;
  period_presets: string[] | null;
}

// --- Frontend types (camelCase) ---

export interface SettingsData {
  primaryCurrency: string | null;
  secondaryCurrency: string | null;
  periodPresets: string[] | null;
}

// --- Mappers ---

function mapSettings(raw: SettingsRaw): SettingsData {
  return {
    primaryCurrency: raw.primary_currency,
    secondaryCurrency: raw.secondary_currency,
    periodPresets: raw.period_presets,
  };
}

// --- API functions ---

export async function getSettings(): Promise<SettingsData> {
  const res = await authenticatedFetch('/settings', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch settings');
  return mapSettings(await res.json());
}
