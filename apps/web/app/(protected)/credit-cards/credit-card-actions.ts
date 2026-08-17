'use server';

import type { CreditCardFormValues } from '@/app/(protected)/credit-cards/credit-card-form-schema';
import type { ReconciliationFormValues } from '@/app/(protected)/credit-cards/reconciliation-form-schema';
import type { SettlementFormValues } from '@/app/(protected)/credit-cards/settlement-form-schema';
import {
  mapReconciliation,
  mapStatement,
  type CardReconciliation,
  type StatementPeriod,
} from '@/lib/api/card-reconciliations';
import {
  mapCreditCard,
  mapSettlement,
  type CardSettlement,
  type CardSettlementRaw,
  type CreditCard,
} from '@/lib/api/credit-cards';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { isRefusal, localizedApiError } from '@/lib/i18n/api-errors-server';

function buildCardBody(values: CreditCardFormValues): Record<string, unknown> {
  const { closingDay, dueDay, monthlyPayment, defaultAccountId, ...rest } = values;
  return {
    ...rest,
    closing_day: Number(closingDay),
    due_day: Number(dueDay),
    monthly_payment: monthlyPayment && monthlyPayment.trim() !== '' ? Number(monthlyPayment) : null,
    default_account_id: defaultAccountId ?? null,
  };
}

// Discriminated results so the form dialog surfaces the backend's coded 400 instead of a generic
// save-failed toast — a thrown error's message does not survive the Server Action boundary.
export type CreateCreditCardResult =
  | { ok: true; card: CreditCard }
  | { ok: false; conflictDetail: string };
export type UpdateCreditCardResult = { ok: true } | { ok: false; conflictDetail: string };

export async function createCreditCard(
  values: CreditCardFormValues,
): Promise<CreateCreditCardResult> {
  const res = await authenticatedFetch('/credit-cards', {
    method: 'POST',
    body: buildCardBody(values),
  });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to create credit card');
  }
  return { ok: true, card: mapCreditCard(await res.json()) };
}

export async function updateCreditCard(
  id: number,
  values: CreditCardFormValues,
): Promise<UpdateCreditCardResult> {
  const res = await authenticatedFetch(`/credit-cards/${id}`, {
    method: 'PUT',
    body: buildCardBody(values),
  });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to update credit card');
  }
  return { ok: true };
}

// Discriminated result so the delete dialog can surface the backend's 409 detail (which
// names the entity kinds still referencing the card) — a thrown error's message does not
// survive the Server Action boundary.
export type DeleteCreditCardResult = { ok: true } | { ok: false; conflictDetail: string };

export async function deleteCreditCard(id: number): Promise<DeleteCreditCardResult> {
  const res = await authenticatedFetch(`/credit-cards/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
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

export type CreateSettlementResult = { ok: true } | { ok: false; conflictDetail: string };

export async function createSettlement(
  cardId: number,
  values: SettlementFormValues,
): Promise<CreateSettlementResult> {
  const { accountId, accountAmount, ...rest } = values;
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements`, {
    method: 'POST',
    body: {
      ...rest,
      account_id: accountId ?? null,
      // Omitted rather than sent empty when no conversion happened: the API reads a null account_amount
      // as "this settlement did not cross currencies", and an empty string would be a 422.
      account_amount: accountAmount || null,
    },
  });
  if (!res.ok) {
    // Reachable: the funding account may be in any currency, so the API refuses a settlement that
    // crosses currencies without recording what left the account, or one that claims a different amount
    // within a single currency. The refusal has to say which.
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to create settlement');
  }
  return { ok: true };
}

export async function deleteSettlement(cardId: number, settlementId: number): Promise<void> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements/${settlementId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete settlement');
}

// Fetches settlements for a card (callable from client components). The wire shape and its mapper are
// imported from lib/api/credit-cards rather than re-declared here — two copies of a wire shape means
// the next API field reaches one call site and silently misses the other.
export async function fetchSettlements(cardId: number): Promise<CardSettlement[]> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch settlements');
  const raw: CardSettlementRaw[] = await res.json();
  return raw.map(mapSettlement);
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

// Discriminated result so the reconcile dialog can surface the backend's coded 400 (an unclosed
// period, a window that is not one of this card's statements) instead of a generic save-failed
// toast — a thrown error's message does not survive the Server Action boundary.
export type ReconciliationResult = { ok: true } | { ok: false; conflictDetail: string };

// Create-or-replace a reconciliation for (card, currency, period). Replaces in-place when one exists.
export async function createOrReplaceReconciliation(
  cardId: number,
  values: ReconciliationFormValues,
): Promise<ReconciliationResult> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/reconciliations`, {
    method: 'POST',
    body: {
      currency: values.currency,
      period_start: values.periodStart,
      period_end: values.periodEnd,
      statement_balance: values.statementBalance,
    },
  });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to save reconciliation');
  }
  return { ok: true };
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
