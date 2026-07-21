'use server';

import type { AccountFormValues } from '@/app/(protected)/accounts/account-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

function toBody(values: AccountFormValues) {
  const { openingBalance, openingDate, notes, ...rest } = values;
  return {
    ...rest,
    opening_balance: Number(openingBalance || 0),
    opening_date: openingDate,
    notes: notes || null,
  };
}

export async function createAccount(values: AccountFormValues): Promise<void> {
  const res = await authenticatedFetch('/accounts', { method: 'POST', body: toBody(values) });
  if (!res.ok) throw new Error('Failed to create account');
}

export async function updateAccount(id: number, values: AccountFormValues): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}`, { method: 'PUT', body: toBody(values) });
  if (!res.ok) throw new Error('Failed to update account');
}

export async function deleteAccount(id: number): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete account');
}

export async function archiveAccount(id: number): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}/archive`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to archive account');
}

export async function unarchiveAccount(id: number): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}/unarchive`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to unarchive account');
}
