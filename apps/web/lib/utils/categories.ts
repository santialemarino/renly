import { INVESTMENT_CATEGORIES, type InvestmentCategory } from '@/lib/constants/categories';

// Returns categories sorted alphabetically by their translated label.
export function sortCategoriesByLabel(t: (key: string) => string): InvestmentCategory[] {
  return [...INVESTMENT_CATEGORIES].sort((a, b) =>
    t(`categories.${a}`).localeCompare(t(`categories.${b}`)),
  );
}
