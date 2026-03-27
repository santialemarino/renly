'use server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function upsertSnapshot(
  investmentId: number,
  data: { date: string; value: string; quantity?: string; currency: string },
): Promise<void> {
  const body: Record<string, unknown> = {
    date: data.date,
    value: data.value,
    currency: data.currency,
  };
  if (data.quantity) {
    body.quantity = data.quantity;
  }
  const res = await authenticatedFetch(`/investments/${investmentId}/snapshots`, {
    method: 'POST',
    body,
  });
  if (!res.ok) throw new Error('Failed to save snapshot');
}

export async function createTransaction(
  investmentId: number,
  data: { date: string; amount: string; quantity?: string; currency: string; type: string },
): Promise<void> {
  const body: Record<string, unknown> = {
    date: data.date,
    amount: data.amount,
    currency: data.currency,
    type: data.type,
  };
  if (data.quantity) {
    body.quantity = data.quantity;
  }
  const res = await authenticatedFetch(`/investments/${investmentId}/transactions`, {
    method: 'POST',
    body,
  });
  if (!res.ok) throw new Error('Failed to create transaction');
}

export async function updateTransaction(
  investmentId: number,
  transactionId: number,
  data: { amount: string; quantity?: string; type: string },
): Promise<void> {
  const body: Record<string, unknown> = {
    amount: data.amount,
    type: data.type,
  };
  if (data.quantity) {
    body.quantity = data.quantity;
  }
  const res = await authenticatedFetch(
    `/investments/${investmentId}/transactions/${transactionId}`,
    {
      method: 'PUT',
      body,
    },
  );
  if (!res.ok) throw new Error('Failed to update transaction');
}

export async function deleteTransaction(
  investmentId: number,
  transactionId: number,
): Promise<void> {
  const res = await authenticatedFetch(
    `/investments/${investmentId}/transactions/${transactionId}`,
    {
      method: 'DELETE',
    },
  );
  if (!res.ok) throw new Error('Failed to delete transaction');
}

// Fetches the price for a ticker on a specific date (get from DB or fetch from provider).
// When convertTo is provided, the backend converts the price to the target currency.
export async function fetchPriceForDate(
  ticker: string,
  date: string,
  category: string,
  convertTo?: string,
): Promise<{
  price: number;
  currency: string;
  convertedPrice: number | null;
  convertedCurrency: string | null;
} | null> {
  const qs = new URLSearchParams({ date, category });
  if (convertTo) qs.append('convert_to', convertTo);
  const res = await authenticatedFetch(`/asset-prices/${ticker}/lookup?${qs}`, { method: 'GET' });
  if (!res.ok) return null;
  const raw = await res.json();
  if (!raw) return null;
  return {
    price: Number(raw.price),
    currency: raw.currency,
    convertedPrice: raw.converted_price !== null ? Number(raw.converted_price) : null,
    convertedCurrency: raw.converted_currency,
  };
}

// Triggers on-demand price refresh for all ticker-linked investments.
export async function refreshPrices(): Promise<{ pricesStored: number }> {
  const res = await authenticatedFetch('/asset-prices/refresh', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to refresh prices');
  const raw = await res.json();
  return { pricesStored: raw.prices_stored };
}
