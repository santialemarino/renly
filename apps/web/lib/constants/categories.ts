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

// Describes what each category supports for pricing and display.
interface CategoryCapability {
  hasTicker: boolean;
  hasAutoPrice: boolean;
  supportsHistory: boolean;
}

// Per-category capabilities. Used by the investment form to show/hide ticker field
// and by the snapshot form to determine price lookup behavior.
export const CATEGORY_CAPABILITIES: Record<InvestmentCategory, CategoryCapability> = {
  cedears: { hasTicker: true, hasAutoPrice: true, supportsHistory: true },
  corporate_bonds: { hasTicker: false, hasAutoPrice: false, supportsHistory: false },
  crypto: { hasTicker: true, hasAutoPrice: true, supportsHistory: false },
  dollars: { hasTicker: false, hasAutoPrice: false, supportsHistory: false },
  fci: { hasTicker: true, hasAutoPrice: false, supportsHistory: false },
  government_bonds: { hasTicker: true, hasAutoPrice: true, supportsHistory: true },
  other: { hasTicker: false, hasAutoPrice: false, supportsHistory: false },
  real_estate: { hasTicker: false, hasAutoPrice: false, supportsHistory: false },
  stocks: { hasTicker: true, hasAutoPrice: true, supportsHistory: true },
  term_deposit: { hasTicker: false, hasAutoPrice: false, supportsHistory: false },
};
