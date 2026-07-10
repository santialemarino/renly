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

// Marks the first-run welcome tour finished/dismissed so it never auto-starts again. A dedicated
// onboarding flag, kept separate from onboarding_completed so the tour and the checklist don't
// suppress each other. Revalidates only the dashboard — the flag affects nothing else.
export async function completeTour(): Promise<void> {
  const res = await authenticatedFetch('/onboarding/tour/complete', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to complete tour');
  revalidatePath(ROUTES.dashboard);
}
