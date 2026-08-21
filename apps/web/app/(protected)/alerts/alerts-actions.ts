'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface SaveAlertsParams {
  maxCollections: number | null;
  collectionWarningPct: number | null;
  liquidityThresholdPct: number | null;
  savingsRateHealthyPct: number | null;
  savingsRateModeratePct: number | null;
  incomeExpenseRatioHealthy: number | null;
}

// Persists the alerts-page subset of settings (collection limit + warning + 4 health thresholds).
// Invalidates the layout so subsequent navigations re-read settings cleanly.
export async function saveAlerts(params: SaveAlertsParams): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: {
      max_collections: params.maxCollections,
      collection_warning_pct: params.collectionWarningPct,
      liquidity_threshold_pct: params.liquidityThresholdPct,
      savings_rate_healthy_pct: params.savingsRateHealthyPct,
      savings_rate_moderate_pct: params.savingsRateModeratePct,
      // Decimal field stored as string on the backend; sent as a JSON number here and
      // Pydantic parses to Decimal. Null clears the user's value (backend falls back).
      income_expense_ratio_healthy: params.incomeExpenseRatioHealthy,
    },
  });
  if (!res.ok) throw new Error('Failed to save alerts settings');
  revalidatePath('/', 'layout');
}
