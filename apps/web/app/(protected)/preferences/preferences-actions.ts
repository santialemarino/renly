'use server';

import { revalidatePath } from 'next/cache';

import type { SettingsData } from '@/lib/api/settings';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface SaveSettingsParams {
  primaryCurrency: string;
  secondaryCurrency: string | null;
  preferredCurrencies?: string[] | null;
  periodPresets?: string[] | null;
  dollarRatePreference?: string | null;
}

export async function saveSettings(params: SaveSettingsParams): Promise<SettingsData> {
  const body: Record<string, unknown> = {
    primary_currency: params.primaryCurrency,
    secondary_currency: params.secondaryCurrency,
  };
  if (params.preferredCurrencies !== undefined) {
    body.preferred_currencies = params.preferredCurrencies;
  }
  if (params.periodPresets !== undefined) {
    body.period_presets = params.periodPresets;
  }
  if (params.dollarRatePreference !== undefined) {
    body.dollar_rate_preference = params.dollarRatePreference;
  }
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body,
  });
  if (!res.ok) throw new Error('Failed to save settings');
  const raw = await res.json();

  // Invalidate the client-side router cache so all pages (dashboard, layout, etc.)
  // re-fetch settings on next navigation instead of serving stale data.
  revalidatePath('/', 'layout');

  return {
    primaryCurrency: raw.primary_currency,
    secondaryCurrency: raw.secondary_currency,
    preferredCurrencies: raw.preferred_currencies ?? null,
    periodPresets: raw.period_presets ?? null,
    maxGroups: raw.max_groups ?? null,
    groupWarningPct: raw.group_warning_pct ?? null,
    dollarRatePreference: raw.dollar_rate_preference ?? null,
    shortcutCurrencies: raw.shortcut_currencies ?? null,
    timezone: raw.timezone ?? null,
    timezoneMode: raw.timezone_mode ?? null,
    language: raw.language ?? null,
    languageMode: raw.language_mode ?? null,
    liquidityThresholdPct: raw.liquidity_threshold_pct ?? null,
    savingsRateHealthyPct: raw.savings_rate_healthy_pct ?? null,
    savingsRateModeratePct: raw.savings_rate_moderate_pct ?? null,
    incomeExpenseRatioHealthy:
      raw.income_expense_ratio_healthy != null ? Number(raw.income_expense_ratio_healthy) : null,
    onboardingCompleted: raw.onboarding_completed ?? null,
  };
}
