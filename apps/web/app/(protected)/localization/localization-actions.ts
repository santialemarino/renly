'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface SaveLocalizationParams {
  timezone: string;
  timezoneMode: string;
}

// Persists the user's IANA timezone + mode (explicit save from the Localization form).
// Invalidates the layout so the next navigation re-reads settings (the auto-sync effect
// needs the fresh stored value to skip its no-op path).
export async function saveLocalization(params: SaveLocalizationParams): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: {
      timezone: params.timezone,
      timezone_mode: params.timezoneMode,
    },
  });
  if (!res.ok) throw new Error('Failed to save localization settings');
  revalidatePath('/', 'layout');
}
