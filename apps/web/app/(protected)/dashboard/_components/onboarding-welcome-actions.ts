'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// Marks first-run onboarding complete so the dashboard welcome stops showing (persisted in settings,
// so it stays dismissed across devices and even if the user later empties their account). Colocated
// with its only caller, OnboardingWelcome.
export async function completeOnboarding(): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: { onboarding_completed: true },
  });
  if (!res.ok) throw new Error('Failed to complete onboarding');
  revalidatePath('/', 'layout');
}
