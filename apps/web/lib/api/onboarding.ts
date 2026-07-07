import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface OnboardingStatusRaw {
  has_investments: boolean;
  has_finances: boolean;
  primary_currency_set: boolean;
  sample_mode: boolean;
}

// --- Frontend types (camelCase) ---

export interface OnboardingStatus {
  hasInvestments: boolean;
  hasFinances: boolean;
  primaryCurrencySet: boolean;
  sampleMode: boolean;
}

// --- Mappers ---

function mapOnboardingStatus(raw: OnboardingStatusRaw): OnboardingStatus {
  return {
    hasInvestments: raw.has_investments,
    hasFinances: raw.has_finances,
    primaryCurrencySet: raw.primary_currency_set,
    sampleMode: raw.sample_mode,
  };
}

// --- API functions ---

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await authenticatedFetch('/onboarding/status', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch onboarding status');
  return mapOnboardingStatus(await res.json());
}
