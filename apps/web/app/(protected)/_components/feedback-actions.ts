'use server';

import { revalidatePath } from 'next/cache';

import type { FeedbackFormData } from '@/app/(protected)/_components/feedback-form-schema';
import { ROUTES } from '@/config/routes';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// Submits feedback to the API (the caller's account email is attached server-side). Returns true on
// success so the dialog can toast; the admin list is revalidated so a viewing admin sees it.
export async function submitFeedback(values: FeedbackFormData): Promise<boolean> {
  const res = await authenticatedFetch('/feedback', {
    method: 'POST',
    body: { category: values.category, message: values.message },
  });
  if (!res.ok) return false;
  revalidatePath(ROUTES.adminFeedback, 'page');
  return true;
}
