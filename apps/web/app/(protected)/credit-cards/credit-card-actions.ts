'use server';

import { getTranslations } from 'next-intl/server';

import type { CreditCardFormValues } from '@/app/(protected)/credit-cards/credit-card-form-schema';
import type { ReconciliationFormValues } from '@/app/(protected)/credit-cards/reconciliation-form-schema';
import type { SettlementFormValues } from '@/app/(protected)/credit-cards/settlement-form-schema';
import {
  mapReconciliation,
  mapStatement,
  type CardReconciliation,
  type StatementPeriod,
} from '@/lib/api/card-reconciliations';
import { mapCreditCard, type CreditCard } from '@/lib/api/credit-cards';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError } from '@/lib/i18n/api-errors';

function buildCardBody(values: CreditCardFormValues): Record<string, unknown> {
  const { closingDay, dueDay, monthlyPayment, ...rest } = values;
  return {
    ...rest,
    closing_day: Number(closingDay),
    due_day: Number(dueDay),
    monthly_payment: monthlyPayment && monthlyPayment.trim() !== '' ? Number(monthlyPayment) : null,
  };
}

export async function createCreditCard(values: CreditCardFormValues): Promise<CreditCard> {
  const res = await authenticatedFetch('/credit-cards', {
    method: 'POST',
    body: buildCardBody(values),
  });
  if (!res.ok) throw new Error('Failed to create credit card');
  return mapCreditCard(await res.json());
}

export async function updateCreditCard(id: number, values: CreditCardFormValues): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${id}`, {
    method: 'PUT',
    body: buildCardBody(values),
  });
  if (!res.ok) throw new Error('Failed to update credit card');
}

// Discriminated result so the delete dialog can surface the backend's 409 detail (which
// names the entity kinds still referencing the card) — a thrown error's message does not
// survive the Server Action boundary.
export type DeleteCreditCardResult = { ok: true } | { ok: false; conflictDetail: string };

export async function deleteCreditCard(id: number): Promise<DeleteCreditCardResult> {
  const res = await authenticatedFetch(`/credit-cards/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    if (res.status === 409) {
      const parsed = await parseApiError(res);
      if (parsed.code || parsed.detail) {
        const t = await getTranslations('apiErrors');
        return { ok: false, conflictDetail: resolveApiError(t, parsed, '') };
      }
    }
    throw new Error('Failed to delete credit card');
  }
  return { ok: true };
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
  values: SettlementFormValues,
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

// Fetches recent statement periods per bucket with reconciliation status (Phase 3, Step 5).
// Drives the Reconciliations sub-section in the expandable card row.
export async function fetchStatements(
  cardId: number,
  currency: string,
): Promise<StatementPeriod[]> {
  const res = await authenticatedFetch(
    `/credit-cards/${cardId}/statements?currency=${encodeURIComponent(currency)}`,
    { method: 'GET' },
  );
  if (!res.ok) throw new Error('Failed to fetch statements');
  const raw = await res.json();
  return raw.map(mapStatement);
}

// Fetches existing reconciliations for a card+bucket. Used to render history under the statement list.
export async function fetchReconciliations(
  cardId: number,
  currency: string,
): Promise<CardReconciliation[]> {
  const res = await authenticatedFetch(
    `/credit-cards/${cardId}/reconciliations?currency=${encodeURIComponent(currency)}`,
    { method: 'GET' },
  );
  if (!res.ok) throw new Error('Failed to fetch reconciliations');
  const raw = await res.json();
  return raw.map(mapReconciliation);
}

// Create-or-replace a reconciliation for (card, currency, period). Replaces in-place when one exists.
export async function createOrReplaceReconciliation(
  cardId: number,
  values: ReconciliationFormValues,
): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/reconciliations`, {
    method: 'POST',
    body: {
      currency: values.currency,
      period_start: values.periodStart,
      period_end: values.periodEnd,
      statement_balance: values.statementBalance,
    },
  });
  if (!res.ok) throw new Error('Failed to save reconciliation');
}

// Delete a reconciliation (cascades to its adjustment expense or income).
export async function deleteReconciliation(
  cardId: number,
  reconciliationId: number,
): Promise<void> {
  const res = await authenticatedFetch(
    `/credit-cards/${cardId}/reconciliations/${reconciliationId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error('Failed to delete reconciliation');
}
