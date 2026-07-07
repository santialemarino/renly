'use server';

import { revalidatePath } from 'next/cache';

import { ROUTES } from '@/config/routes';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// The sections that render a first-run sample. Matches the backend SampleEntity enum + routing.
export type SampleEntity = 'investments' | 'expenses' | 'income';

const SAMPLE_ENTITY_ROUTES: Record<SampleEntity, string> = {
  investments: ROUTES.investments,
  expenses: ROUTES.expenses,
  income: ROUTES.income,
};

// Retires one section's first-run sample (the section's "Clear"). Per-section: revalidates only
// that section's route, so clearing one leaves the other sections' samples in place.
export async function dismissSample(entity: SampleEntity): Promise<void> {
  const res = await authenticatedFetch(`/onboarding/samples/${entity}/dismiss`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to dismiss sample');
  revalidatePath(SAMPLE_ENTITY_ROUTES[entity]);
}
