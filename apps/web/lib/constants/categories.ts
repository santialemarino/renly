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
