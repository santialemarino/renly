'use server';

import { revalidatePath } from 'next/cache';

import { mapSettings, type SettingsData } from '@/lib/api/settings';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface SaveSettingsParams {
  primaryCurrency: string;
  secondaryCurrency: string | null;
  preferredCurrencies?: string[] | null;
  periodPresets?: string[] | null;
  dollarRatePreference?: string | null;
}

export async function saveSettings(params: SaveSettingsParams): Promise<SettingsData> {
  const body: Record<string, unknown> = {
    primary_currency: params.primaryCurrency,
    secondary_currency: params.secondaryCurrency,
  };
  if (params.preferredCurrencies !== undefined) {
    body.preferred_currencies = params.preferredCurrencies;
  }
  if (params.periodPresets !== undefined) {
    body.period_presets = params.periodPresets;
  }
  if (params.dollarRatePreference !== undefined) {
    body.dollar_rate_preference = params.dollarRatePreference;
  }
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body,
  });
  if (!res.ok) throw new Error('Failed to save settings');

  // Invalidate the client-side router cache so all pages (dashboard, layout, etc.)
  // re-fetch settings on next navigation instead of serving stale data.
  revalidatePath('/', 'layout');

  // Reuse the shared mapper so the snake→camel mapping lives in exactly one place.
  return mapSettings(await res.json());
}
