// Server-only types + helpers for card reconciliations (Phase 3, Step 5).
// Client components fetch via server actions in `credit-card-actions.ts` instead.

import 'server-only';

// --- Raw types (API JSON shape, snake_case) ---

interface CardReconciliationRaw {
  id: number;
  card_id: number;
  currency: string;
  period_start: string;
  period_end: string;
  statement_balance: string;
  computed_balance: string;
  difference: string;
  adjustment_expense_id: number | null;
  adjustment_income_id: number | null;
  is_stale: boolean;
  reconciled_at: string;
  created_at: string;
  updated_at: string;
}

interface StatementPeriodRaw {
  currency: string;
  period_start: string;
  period_end: string;
  computed_balance: string;
  reconciliation: CardReconciliationRaw | null;
}

// --- Frontend types (camelCase) ---

export interface CardReconciliation {
  id: number;
  cardId: number;
  currency: string;
  periodStart: string;
  periodEnd: string;
  statementBalance: string;
  computedBalance: string;
  difference: string;
  adjustmentExpenseId: number | null;
  adjustmentIncomeId: number | null;
  isStale: boolean;
  reconciledAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface StatementPeriod {
  currency: string;
  periodStart: string;
  periodEnd: string;
  computedBalance: string;
  reconciliation: CardReconciliation | null;
}

// --- Mappers ---

export function mapReconciliation(raw: CardReconciliationRaw): CardReconciliation {
  return {
    id: raw.id,
    cardId: raw.card_id,
    currency: raw.currency,
    periodStart: raw.period_start,
    periodEnd: raw.period_end,
    statementBalance: raw.statement_balance,
    computedBalance: raw.computed_balance,
    difference: raw.difference,
    adjustmentExpenseId: raw.adjustment_expense_id,
    adjustmentIncomeId: raw.adjustment_income_id,
    isStale: raw.is_stale,
    reconciledAt: raw.reconciled_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

export function mapStatement(raw: StatementPeriodRaw): StatementPeriod {
  return {
    currency: raw.currency,
    periodStart: raw.period_start,
    periodEnd: raw.period_end,
    computedBalance: raw.computed_balance,
    reconciliation: raw.reconciliation ? mapReconciliation(raw.reconciliation) : null,
  };
}
