'use server';

import type { SettingsData } from '@/lib/api/settings';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function saveSettings(
  primaryCurrency: string,
  secondaryCurrency: string | null,
): Promise<SettingsData> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { primary_currency: primaryCurrency, secondary_currency: secondaryCurrency },
  });
  if (!res.ok) throw new Error('Failed to save settings');
  return res.json();
}
