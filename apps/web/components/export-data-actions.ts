'use server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { rateLimitedMessage } from '@/lib/i18n/api-errors-server';

// The export as a JSON string, or a failure with a message worth showing (a rate limit) or null for
// the generic one. Returned rather than thrown: Next.js strips a thrown server-action error's message.
export type ExportDataResult = { ok: true; json: string } | { ok: false; message: string | null };

// Returns the user's full data export as a JSON string for client-side download (AUTH-6).
export async function exportData(): Promise<ExportDataResult> {
  const res = await authenticatedFetch('/me/export', { method: 'GET' });
  if (!res.ok) return { ok: false, message: await rateLimitedMessage(res) };
  return { ok: true, json: await res.text() };
}
