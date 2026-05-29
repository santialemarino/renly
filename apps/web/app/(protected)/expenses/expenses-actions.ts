'use server';

import type { ExpenseFormValues } from '@/app/(protected)/expenses/expenses-form-schema';
import type { Expense } from '@/lib/api/expenses';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface ExpenseRaw {
  id: number;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  source: string;
  payment_obligation_id: number | null;
  subscription_id: number | null;
  installment_id: number | null;
  created_at: string;
  updated_at: string;
}

// Cursor change emitted by a linked plan on create / update / delete (Phase 3,
// follow-up Item 7). The form composes a follow-up toast line — "Netflix's next
// billing date moved to Jun 27, 2026." — branching on planType. previousCursor /
// newCursor are stringified — ISO date for obligation/subscription, decimal index
// for installment; newCursor is empty when the plan archived, previousCursor is
// empty when the plan re-activated via reverse. totalCount is populated for
// installments only (the plan's `installments_count`) so the toast renders
// "N of M installments paid" without a client-side lookup against a stale
// active-plans list.
export interface PlanCursorChange {
  planType: 'obligation' | 'subscription' | 'installment';
  planId: number;
  planName: string;
  previousCursor: string;
  newCursor: string;
  totalCount: number | null;
}

// Bundle of cursor deltas returned by create / update mutations. Both fields can fire
// simultaneously on a FK swap — the OLD plan loses this expense (reverse) and the NEW
// plan gains it (advance). The form composes the toast with potentially both lines.
export interface ExpenseMutationOutcome {
  advance: PlanCursorChange | null;
  reverse: PlanCursorChange | null;
}

// Discriminated result so the form can branch without `instanceof` (Next.js Server Action
// boundary strips prototype chains — a thrown class instance arrives at the client as a
// plain Error, so an `instanceof` check silently returns false and the user sees the
// generic save-error toast instead of the backend's 409 detail). Returning the conflict
// as data keeps the type information across the boundary; only truly unexpected failures
// (network, 500) still throw.
export type ExpenseMutationResult =
  | { ok: true; outcome: ExpenseMutationOutcome }
  | { ok: false; conflictDetail: string };

interface PlanCursorChangeRaw {
  plan_type: 'obligation' | 'subscription' | 'installment';
  plan_id: number;
  plan_name: string;
  previous_cursor: string;
  new_cursor: string;
  total_count: number | null;
}

function mapCursorChange(raw: PlanCursorChangeRaw | null): PlanCursorChange | null {
  if (!raw) return null;
  return {
    planType: raw.plan_type,
    planId: raw.plan_id,
    planName: raw.plan_name,
    previousCursor: raw.previous_cursor,
    newCursor: raw.new_cursor,
    totalCount: raw.total_count,
  };
}

// Fetches a single expense by id. Used by the Payments Calendar to open the linked
// expense's edit dialog when the user clicks a Paid badge.
export async function getExpenseById(id: number): Promise<Expense> {
  const res = await authenticatedFetch(`/expenses/${id}`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch expense');
  const raw: ExpenseRaw = await res.json();
  return {
    id: raw.id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    category: raw.category,
    notes: raw.notes,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    source: raw.source,
    paymentObligationId: raw.payment_obligation_id,
    subscriptionId: raw.subscription_id,
    installmentId: raw.installment_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

type ExpenseMutationRaw = ExpenseRaw & {
  advance_change: PlanCursorChangeRaw | null;
  reverse_change: PlanCursorChangeRaw | null;
};

function mapMutationOutcome(raw: ExpenseMutationRaw): ExpenseMutationOutcome {
  return {
    advance: mapCursorChange(raw.advance_change),
    reverse: mapCursorChange(raw.reverse_change),
  };
}

async function readErrorDetail(res: Response): Promise<string | null> {
  try {
    const body: { detail?: unknown } = await res.json();
    return typeof body.detail === 'string' ? body.detail : null;
  } catch {
    return null;
  }
}

export async function createExpense(values: ExpenseFormValues): Promise<ExpenseMutationResult> {
  const {
    paymentMethod,
    creditCardId,
    paymentObligationId,
    subscriptionId,
    installmentId,
    cyclesToAdvance,
    ...rest
  } = values;
  // cyclesToAdvance is a digit-only string from IntegerInput; empty / undefined means
  // "default to 1" (single-cycle path). The backend enforces 1..12 in the schema; the
  // form schema mirrors that range and the Mark Paid dialog hides the field for
  // one-off obligations + non-Mark-Paid flows.
  const cycles = cyclesToAdvance ? Number(cyclesToAdvance) : 1;
  const res = await authenticatedFetch('/expenses', {
    method: 'POST',
    body: {
      ...rest,
      payment_method: paymentMethod,
      credit_card_id: creditCardId,
      payment_obligation_id: paymentObligationId ?? null,
      subscription_id: subscriptionId ?? null,
      installment_id: installmentId ?? null,
      cycles_to_advance: cycles,
    },
  });
  if (!res.ok) {
    if (res.status === 409) {
      const detail = await readErrorDetail(res);
      if (detail) return { ok: false, conflictDetail: detail };
    }
    throw new Error('Failed to create expense');
  }
  return { ok: true, outcome: mapMutationOutcome(await res.json()) };
}

export async function updateExpense(
  id: number,
  values: ExpenseFormValues,
): Promise<ExpenseMutationResult> {
  // Commitment FKs follow JSON Merge Patch semantics: pass `null` to clear an existing
  // link, pass an id to swap to a different plan. The server fires the symmetric advance /
  // reverse model — clear / swap reverses the OLD plan; add / swap advances the NEW plan.
  // A swap can populate both `advance` and `reverse` in the outcome (Phase 3, follow-up
  // Items 10 + audit round 2).
  const res = await authenticatedFetch(`/expenses/${id}`, {
    method: 'PUT',
    body: {
      date: values.date,
      amount: values.amount,
      currency: values.currency,
      category: values.category,
      notes: values.notes,
      payment_method: values.paymentMethod,
      credit_card_id: values.creditCardId,
      payment_obligation_id: values.paymentObligationId ?? null,
      subscription_id: values.subscriptionId ?? null,
      installment_id: values.installmentId ?? null,
    },
  });
  if (!res.ok) {
    if (res.status === 409) {
      const detail = await readErrorDetail(res);
      if (detail) return { ok: false, conflictDetail: detail };
    }
    throw new Error('Failed to update expense');
  }
  return { ok: true, outcome: mapMutationOutcome(await res.json()) };
}

export async function deleteExpense(id: number): Promise<PlanCursorChange | null> {
  const res = await authenticatedFetch(`/expenses/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete expense');
  const raw: { reverse_change: PlanCursorChangeRaw | null } = await res.json();
  return mapCursorChange(raw.reverse_change);
}

// Result of a manual-dupe expense lookup (Phase 3, Step D).
export interface AutoChargeMatch {
  expenseId: number;
  date: string;
  source: 'subscription' | 'installment';
  sourcePlan: { id: number; name: string };
}

interface AutoChargeMatchRaw {
  expense_id: number;
  date: string;
  source: 'subscription' | 'installment';
  source_plan: { id: number; name: string };
}

export async function getAutoChargeMatch(params: {
  creditCardId: number;
  currency: string;
  amount: string;
  date: string;
  excludeExpenseId?: number;
}): Promise<AutoChargeMatch | null> {
  const qs = new URLSearchParams({
    credit_card_id: String(params.creditCardId),
    currency: params.currency,
    amount: params.amount,
    date: params.date,
  });
  if (params.excludeExpenseId !== undefined) {
    qs.set('exclude_expense_id', String(params.excludeExpenseId));
  }
  const res = await authenticatedFetch(`/expenses/auto-charge-match?${qs.toString()}`, {
    method: 'GET',
  });
  if (!res.ok) throw new Error('Failed to look up auto-charge match');
  const raw: { match: AutoChargeMatchRaw | null } = await res.json();
  if (!raw.match) return null;
  return {
    expenseId: raw.match.expense_id,
    date: raw.match.date,
    source: raw.match.source,
    sourcePlan: raw.match.source_plan,
  };
}

// Preview decision returned by GET /expenses/cycle-advance-preview (Phase 3, follow-up 3b,
// revised by Item 9). The expense form calls this before save when the user has linked
// a subscription or installment; would_advance=false drives a soft-confirm dialog before
// continuing. multi_jump=true means the matched cycle is ahead of the current cursor
// (pre-pay / mis-click) — link saved, scheduler back-fills intermediate cycles.
export interface CycleAdvancePreview {
  wouldAdvance: boolean;
  distanceDays: number;
  nextExpectedDate: string;
  multiJump: boolean;
}

interface CycleAdvancePreviewRaw {
  would_advance: boolean;
  distance_days: number;
  next_expected_date: string;
  multi_jump: boolean;
}

export async function getCycleAdvancePreview(params: {
  entryDate: string;
  subscriptionId?: number;
  installmentId?: number;
}): Promise<CycleAdvancePreview> {
  const qs = new URLSearchParams({ entry_date: params.entryDate });
  if (params.subscriptionId !== undefined) qs.set('subscription_id', String(params.subscriptionId));
  if (params.installmentId !== undefined) qs.set('installment_id', String(params.installmentId));
  const res = await authenticatedFetch(`/expenses/cycle-advance-preview?${qs.toString()}`, {
    method: 'GET',
  });
  if (!res.ok) throw new Error('Failed to look up cycle advance preview');
  const raw: CycleAdvancePreviewRaw = await res.json();
  return {
    wouldAdvance: raw.would_advance,
    distanceDays: raw.distance_days,
    nextExpectedDate: raw.next_expected_date,
    multiJump: raw.multi_jump,
  };
}
