// Server-only types + mappers for account reconciliations (Bucket 3 #1).
// Client components fetch via server actions in `account-actions.ts` instead.

import 'server-only';

// --- Raw types (API JSON shape, snake_case) ---

interface AccountReconciliationRaw {
  id: number;
  account_id: number;
  as_of_date: string;
  statement_balance: string;
  computed_balance: string;
  difference: string;
  adjustment_expense_id: number | null;
  adjustment_income_id: number | null;
  adjustment_shared_expense_id: number | null;
  adjustment_shared_income_id: number | null;
  reconciled_by: string | null;
  reconciled_at: string;
  created_at: string;
  updated_at: string;
}

interface ReconciliationBearerRaw {
  member_id: number;
  display_name: string;
  percentage: string;
}

interface AccountComputedBalanceRaw {
  account_id: number;
  as_of_date: string;
  balance: string;
  bearers: ReconciliationBearerRaw[];
}

// --- Frontend types (camelCase) ---

export interface AccountReconciliation {
  id: number;
  accountId: number;
  asOfDate: string;
  statementBalance: string;
  computedBalance: string;
  difference: string;
  adjustmentExpenseId: number | null;
  adjustmentIncomeId: number | null;
  adjustmentSharedExpenseId: number | null;
  adjustmentSharedIncomeId: number | null;
  /** Who ran it, as the pot's group names them; null on a private account and on a seat with no account. */
  reconciledBy: string | null;
  reconciledAt: string;
  createdAt: string;
  updatedAt: string;
}

/** One member who would bear part of a shared account's difference, and what proportion of it. */
export interface ReconciliationBearer {
  memberId: number;
  displayName: string;
  percentage: string;
}

export interface AccountComputedBalance {
  accountId: number;
  asOfDate: string;
  balance: string;
  /** Who the difference divides between on a pot's account, largest share first; empty on a private one. */
  bearers: ReconciliationBearer[];
}

// --- Mappers ---

export function mapAccountComputedBalance(raw: AccountComputedBalanceRaw): AccountComputedBalance {
  return {
    accountId: raw.account_id,
    asOfDate: raw.as_of_date,
    balance: raw.balance,
    bearers: raw.bearers.map((bearer) => ({
      memberId: bearer.member_id,
      displayName: bearer.display_name,
      percentage: bearer.percentage,
    })),
  };
}

export function mapAccountReconciliation(raw: AccountReconciliationRaw): AccountReconciliation {
  return {
    id: raw.id,
    accountId: raw.account_id,
    asOfDate: raw.as_of_date,
    statementBalance: raw.statement_balance,
    computedBalance: raw.computed_balance,
    difference: raw.difference,
    adjustmentExpenseId: raw.adjustment_expense_id,
    adjustmentIncomeId: raw.adjustment_income_id,
    adjustmentSharedExpenseId: raw.adjustment_shared_expense_id,
    adjustmentSharedIncomeId: raw.adjustment_shared_income_id,
    reconciledBy: raw.reconciled_by,
    reconciledAt: raw.reconciled_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}
