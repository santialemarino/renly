export const INVESTMENT_CATEGORIES = [
  'cedears',
  'corporate_bonds',
  'crypto',
  'dollars',
  'fci',
  'government_bonds',
  'other',
  'real_estate',
  'stocks',
  'term_deposit',
] as const;

export type InvestmentCategory = (typeof INVESTMENT_CATEGORIES)[number];

// Describes what each category supports.
interface CategoryCapability {
  hasTicker: boolean;
}

// Per-category capabilities. The investment form shows the ticker field from `hasTicker`, and the
// API auto-prices exactly the categories that have one (pinned by the API's enum-parity test).
export const CATEGORY_CAPABILITIES: Record<InvestmentCategory, CategoryCapability> = {
  cedears: { hasTicker: true },
  corporate_bonds: { hasTicker: false },
  crypto: { hasTicker: true },
  dollars: { hasTicker: false },
  fci: { hasTicker: true },
  government_bonds: { hasTicker: true },
  other: { hasTicker: false },
  real_estate: { hasTicker: false },
  stocks: { hasTicker: true },
  term_deposit: { hasTicker: false },
};

export const INCOME_CATEGORIES = [
  'bonus',
  'dividends',
  'freelance',
  'gifts',
  'investment_returns',
  'other',
  'refunds',
  'rental_income',
  'salary',
  'sales',
] as const;

export type IncomeCategory = (typeof INCOME_CATEGORIES)[number];

export const EXPENSE_CATEGORIES = [
  'clothing',
  'dining',
  'education',
  'entertainment',
  'food',
  'gifts',
  'health',
  'home_maintenance',
  'insurance',
  'kids',
  'other',
  'personal_care',
  'pets',
  'rent',
  'sports',
  'subscriptions',
  'taxes',
  'transport',
  'travel',
  'utilities',
] as const;

export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number];

export const PAYMENT_METHODS = ['cash', 'debit', 'transfer', 'credit_card'] as const;

export type PaymentMethod = (typeof PAYMENT_METHODS)[number];
