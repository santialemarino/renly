import {
  EXPENSE_CATEGORIES,
  INCOME_CATEGORIES,
  INVESTMENT_CATEGORIES,
  type ExpenseCategory,
  type IncomeCategory,
  type InvestmentCategory,
} from '@/lib/constants/categories';

// Sorts categories alphabetically by translated label, with "other" always last.
function sortWithOtherLast<T extends string>(
  categories: readonly T[],
  getLabel: (cat: T) => string,
): T[] {
  return [...categories].sort((a, b) => {
    if (a === 'other') return 1;
    if (b === 'other') return -1;
    return getLabel(a).localeCompare(getLabel(b));
  });
}

// Returns investment categories sorted by translated label, "other" last.
export function sortCategoriesByLabel(t: (key: string) => string): InvestmentCategory[] {
  return sortWithOtherLast(INVESTMENT_CATEGORIES, (cat) => t(`categories.${cat}`));
}

// Returns expense categories sorted by translated label, "other" last.
export function sortExpenseCategoriesByLabel(t: (key: string) => string): ExpenseCategory[] {
  return sortWithOtherLast(EXPENSE_CATEGORIES, (cat) => t(`categories.${cat}`));
}

// Returns income categories sorted by translated label, "other" last.
export function sortIncomeCategoriesByLabel(t: (key: string) => string): IncomeCategory[] {
  return sortWithOtherLast(INCOME_CATEGORIES, (cat) => t(`categories.${cat}`));
}
