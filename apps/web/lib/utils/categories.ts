import {
  EXPENSE_CATEGORIES,
  INCOME_CATEGORIES,
  INVESTMENT_CATEGORIES,
  type ExpenseCategory,
  type IncomeCategory,
  type InvestmentCategory,
} from '@/lib/constants/categories';
import { getLocaleTag } from '@/lib/i18n/locales';

// Sorts categories alphabetically by translated label, with "other" always last.
function sortWithOtherLast<T extends string>(
  categories: readonly T[],
  getLabel: (cat: T) => string,
  locale?: string,
): T[] {
  const tag = getLocaleTag(locale);
  return [...categories].sort((a, b) => {
    if (a === 'other') return 1;
    if (b === 'other') return -1;
    return getLabel(a).localeCompare(getLabel(b), tag);
  });
}

// Returns investment categories sorted by translated label, "other" last.
export function sortCategoriesByLabel(
  t: (key: string) => string,
  locale?: string,
): InvestmentCategory[] {
  return sortWithOtherLast(INVESTMENT_CATEGORIES, (cat) => t(`categories.${cat}`), locale);
}

// Returns expense categories sorted by translated label, "other" last.
export function sortExpenseCategoriesByLabel(
  t: (key: string) => string,
  locale?: string,
): ExpenseCategory[] {
  return sortWithOtherLast(EXPENSE_CATEGORIES, (cat) => t(`categories.${cat}`), locale);
}

// Returns income categories sorted by translated label, "other" last.
export function sortIncomeCategoriesByLabel(
  t: (key: string) => string,
  locale?: string,
): IncomeCategory[] {
  return sortWithOtherLast(INCOME_CATEGORIES, (cat) => t(`categories.${cat}`), locale);
}

/*
 * True for a stored category value that is not in the given user-pickable set. Derived from the set
 * the picker itself renders, so the two can never drift: the backend enums also carry
 * system-generated values a reconciliation writes (`card_fees_and_taxes`,
 * `card_credits_and_refunds`, `account_adjustment`) which are deliberately absent here.
 */
function isOutsidePickableSet(categories: readonly string[], category: string | null): boolean {
  return category !== null && !categories.includes(category);
}

/*
 * True when an expense's category is system-generated, so the entry form cannot round-trip the row:
 * the combobox has no matching option and renders blank, and the form schema's
 * `z.enum(EXPENSE_CATEGORIES)` rejects the stored value on save. Such a row is un-editable regardless
 * of whether a reconciliation still owns it — a restored adjustment keeps its system category after
 * restore nulls the reconciliation links, and a card credit additionally carries a NEGATIVE amount
 * the shared amount input strips. Distinct from isReconciliationOwned (lib/reconciliation): that gates
 * BOTH actions because the API refuses both, whereas a row nothing owns may still legitimately be
 * deleted, so this gates Edit only.
 */
export function isSystemExpenseCategory(category: string | null): boolean {
  return isOutsidePickableSet(EXPENSE_CATEGORIES, category);
}

// True when an income entry's category is system-generated — the income-side counterpart of
// isSystemExpenseCategory (`account_adjustment`, and the legacy `card_credits_and_refunds`).
export function isSystemIncomeCategory(category: string | null): boolean {
  return isOutsidePickableSet(INCOME_CATEGORIES, category);
}
