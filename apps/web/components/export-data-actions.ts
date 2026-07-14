'use server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// Returns the user's full data export as a JSON string for client-side download (AUTH-6).
export async function exportData(): Promise<string> {
  const res = await authenticatedFetch('/me/export', { method: 'GET' });
  if (!res.ok) throw new Error('export_failed');
  return res.text();
}
