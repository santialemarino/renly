'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { TIMEZONE_MODE_AUTO } from '@/lib/constants/timezones';

// Silent PUT of browser-detected timezone. Keeps mode = auto. Errors swallowed by caller.
export async function syncBrowserTimezone(timezone: string): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { timezone, timezone_mode: TIMEZONE_MODE_AUTO },
  });
  if (!res.ok) throw new Error('Failed to sync browser timezone');
  // Invalidate cached settings so other layouts see the new value next navigation.
  revalidatePath('/', 'layout');
}
