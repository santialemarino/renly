'use server';

import { revalidatePath } from 'next/cache';

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

  // Invalidate the client-side router cache so all pages (dashboard, layout, etc.)
  // re-fetch settings on next navigation instead of serving stale data.
  // Route groups like (protected) are not real URL paths, so revalidate from root.
  revalidatePath('/', 'layout');

  return {
    primaryCurrency: raw.primary_currency,
    secondaryCurrency: raw.secondary_currency,
    periodPresets: raw.period_presets ?? null,
  };
}
