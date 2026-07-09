import 'server-only';

import { cache } from 'react';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface OnboardingStatusRaw {
  has_investments: boolean;
  has_finances: boolean;
  primary_currency_set: boolean;
  sample_investments: boolean;
  sample_expenses: boolean;
  sample_income: boolean;
}

// --- Frontend types (camelCase) ---

export interface OnboardingStatus {
  hasInvestments: boolean;
  hasFinances: boolean;
  primaryCurrencySet: boolean;
  sampleInvestments: boolean;
  sampleExpenses: boolean;
  sampleIncome: boolean;
}

// --- Mappers ---

function mapOnboardingStatus(raw: OnboardingStatusRaw): OnboardingStatus {
  return {
    hasInvestments: raw.has_investments,
    hasFinances: raw.has_finances,
    primaryCurrencySet: raw.primary_currency_set,
    sampleInvestments: raw.sample_investments,
    sampleExpenses: raw.sample_expenses,
    sampleIncome: raw.sample_income,
  };
}

// --- API functions ---

// Server-side, request-memoized onboarding status so the protected layout and the first-run pages
// (dashboard, sample-data list pages) that read it in the same render share a single API call.
export const getOnboardingStatus = cache(async (): Promise<OnboardingStatus> => {
  const res = await authenticatedFetch('/onboarding/status', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch onboarding status');
  return mapOnboardingStatus(await res.json());
});
