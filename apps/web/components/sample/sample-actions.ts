'use server';

import { revalidatePath } from 'next/cache';

import { ROUTES } from '@/config/routes';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// Dismisses first-run sample data account-wide (persists the settings flag). Revalidates every list
// surface that can show samples so they clear consistently wherever the user navigates next.
export async function dismissSamples(): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { samples_dismissed: true },
  });
  if (!res.ok) throw new Error('Failed to dismiss samples');
  [ROUTES.investments, ROUTES.expenses, ROUTES.income].forEach((path) => revalidatePath(path));
}
