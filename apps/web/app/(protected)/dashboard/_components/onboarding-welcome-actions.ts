'use server';

import { revalidatePath } from 'next/cache';

import { ROUTES } from '@/config/routes';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// Marks first-run onboarding complete so the dashboard welcome stops showing (persisted in settings,
// so it stays dismissed across devices and even if the user later empties their account). Colocated
// with its only caller, OnboardingWelcome. Revalidates only the dashboard — the flag affects nothing
// else — so dismissing doesn't re-fetch every other route's layout data.
export async function completeOnboarding(): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { onboarding_completed: true },
  });
  if (!res.ok) throw new Error('Failed to complete onboarding');
  revalidatePath(ROUTES.dashboard);
}
