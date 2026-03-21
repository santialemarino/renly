'use server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function upsertSnapshot(
  investmentId: number,
  data: { date: string; value: string; currency: string },
): Promise<void> {
  const res = await authenticatedFetch(`/investments/${investmentId}/snapshots`, {
    method: 'POST',
    body: {
      date: data.date,
      value: data.value,
      currency: data.currency,
    },
  });
  if (!res.ok) throw new Error('Failed to save snapshot');
}

export async function createTransaction(
  investmentId: number,
  data: { date: string; amount: string; currency: string; type: string },
): Promise<void> {
  const res = await authenticatedFetch(`/investments/${investmentId}/transactions`, {
    method: 'POST',
    body: {
      date: data.date,
      amount: data.amount,
      currency: data.currency,
      type: data.type,
    },
  });
  if (!res.ok) throw new Error('Failed to create transaction');
}

export async function updateTransaction(
  investmentId: number,
  transactionId: number,
  data: { amount: string; type: string },
): Promise<void> {
  const res = await authenticatedFetch(
    `/investments/${investmentId}/transactions/${transactionId}`,
    {
      method: 'PUT',
      body: {
        amount: data.amount,
        type: data.type,
      },
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
