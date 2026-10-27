'use server';

import { revalidatePath } from 'next/cache';

import type { FeedbackFormData } from '@/app/(protected)/_components/feedback-form-schema';
import { ROUTES } from '@/config/routes';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { rateLimitedMessage } from '@/lib/i18n/api-errors-server';

// The outcome of a feedback submission: ok, or failed with a message worth showing (a rate limit) or
// null for the dialog's generic error.
export type SubmitFeedbackResult = { ok: true } | { ok: false; message: string | null };

// Submits feedback to the API (the caller's account email is attached server-side). Reports success so
// the dialog can toast; the admin list is revalidated so a viewing admin sees it.
export async function submitFeedback(values: FeedbackFormData): Promise<SubmitFeedbackResult> {
  const res = await authenticatedFetch('/feedback', {
    method: 'POST',
    body: { category: values.category, message: values.message },
  });
  if (!res.ok) return { ok: false, message: await rateLimitedMessage(res) };
  revalidatePath(ROUTES.adminFeedback, 'page');
  return { ok: true };
}
