'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface SaveAlertsParams {
  maxGroups: number | null;
  groupWarningPct: number | null;
  liquidityThresholdPct: number | null;
}

// Persists the alerts-page subset of settings (group limit + warning + liquidity threshold).
// Invalidates the layout so subsequent navigations re-read settings cleanly.
export async function saveAlerts(params: SaveAlertsParams): Promise<void> {
  const res = await authenticatedFetch('/settings', {
    method: 'PUT',
    body: {
      max_groups: params.maxGroups,
      group_warning_pct: params.groupWarningPct,
      liquidity_threshold_pct: params.liquidityThresholdPct,
    },
  });
  if (!res.ok) throw new Error('Failed to save alerts settings');
  revalidatePath('/', 'layout');
}
