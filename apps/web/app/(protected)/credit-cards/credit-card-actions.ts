'use server';

import type { CreditCardFormValues } from '@/app/(protected)/credit-cards/credit-card-form-schema';
import type { SettlementFormValues } from '@/app/(protected)/credit-cards/settlement-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createCreditCard(values: CreditCardFormValues): Promise<void> {
  const { closingDay, dueDay, ...rest } = values;
  const res = await authenticatedFetch('/credit-cards', {
    method: 'POST',
    body: { ...rest, closing_day: Number(closingDay), due_day: Number(dueDay) },
  });
  if (!res.ok) throw new Error('Failed to create credit card');
}

export async function updateCreditCard(id: number, values: CreditCardFormValues): Promise<void> {
  const { closingDay, dueDay, ...rest } = values;
  const res = await authenticatedFetch(`/credit-cards/${id}`, {
    method: 'PUT',
    body: { ...rest, closing_day: Number(closingDay), due_day: Number(dueDay) },
  });
  if (!res.ok) throw new Error('Failed to update credit card');
}

export async function deleteCreditCard(id: number): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete credit card');
}

export async function archiveCreditCard(id: number): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${id}/archive`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to archive credit card');
}

export async function unarchiveCreditCard(id: number): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${id}/unarchive`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to unarchive credit card');
}

export async function createSettlement(
  cardId: number,
  values: SettlementFormValues & { currency: string },
): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements`, {
    method: 'POST',
    body: values,
  });
  if (!res.ok) throw new Error('Failed to create settlement');
}

export async function deleteSettlement(cardId: number, settlementId: number): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements/${settlementId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete settlement');
}

interface SettlementRaw {
  id: number;
  credit_card_id: number;
  date: string;
  amount: string;
  currency: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SettlementResult {
  id: number;
  creditCardId: number;
  date: string;
  amount: string;
  currency: string;
  notes: string | null;
}

// Fetches settlements for a card (callable from client components).
export async function fetchSettlements(cardId: number): Promise<SettlementResult[]> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch settlements');
  const raw: SettlementRaw[] = await res.json();
  return raw.map((s) => ({
    id: s.id,
    creditCardId: s.credit_card_id,
    date: s.date,
    amount: s.amount,
    currency: s.currency,
    notes: s.notes,
  }));
}
