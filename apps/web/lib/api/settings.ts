import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

export interface SettingsData {
  primary_currency: string | null;
  secondary_currency: string | null;
}

export async function getSettings(): Promise<SettingsData> {
  const res = await authenticatedFetch('/settings', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch settings');
  return res.json();
}
