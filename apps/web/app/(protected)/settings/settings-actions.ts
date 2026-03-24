'use server';

import type { SettingsData } from '@/lib/api/settings';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function saveSettings(
  primaryCurrency: string,
  secondaryCurrency: string | null,
  periodPresets?: string[] | null,
): Promise<SettingsData> {
  const body: Record<string, unknown> = {
    primary_currency: primaryCurrency,
    secondary_currency: secondaryCurrency,
  };
  if (periodPresets !== undefined) {
    body.period_presets = periodPresets;
  }
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body,
  });
  if (!res.ok) throw new Error('Failed to save settings');
  const raw = await res.json();
  return {
    primaryCurrency: raw.primary_currency,
    secondaryCurrency: raw.secondary_currency,
    periodPresets: raw.period_presets ?? null,
  };
}
