'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { TIMEZONE_MODE_AUTO } from '@/lib/constants/timezones';

// Silent PUT of browser-detected timezone. Called from the layout-level TimezoneAutoSync
// effect when mode is 'auto' and the browser tz differs from stored. Keeps mode = auto.
// Errors swallowed by caller (next page load retries). Colocated with the only caller
// (TimezoneAutoSync) since the action isn't tied to a specific page.
export async function syncBrowserTimezone(timezone: string): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { timezone, timezone_mode: TIMEZONE_MODE_AUTO },
  });
  if (!res.ok) throw new Error('Failed to sync browser timezone');
  revalidatePath('/', 'layout');
}
