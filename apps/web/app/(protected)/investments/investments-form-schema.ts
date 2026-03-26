import { z } from 'zod';

import { INVESTMENT_BROKER_MAX, INVESTMENT_NAME_MAX } from '@/lib/constants/api-constants';

export const INVESTMENT_CATEGORIES = [
  'cedears',
  'fci',
  'dollars',
  'bonds',
  'stocks',
  'crypto',
  'real_estate',
  'term_deposit',
  'other',
] as const;

export type InvestmentCategory = (typeof INVESTMENT_CATEGORIES)[number];

export function buildInvestmentFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(INVESTMENT_NAME_MAX),
    category: z.enum(INVESTMENT_CATEGORIES, { message: requiredMsg }),
    baseCurrency: z.string().min(1, { message: requiredMsg }),
    ticker: z.string().max(20).optional(),
    broker: z.string().max(INVESTMENT_BROKER_MAX).optional(),
    notes: z.string().optional(),
    groupIds: z.array(z.number()).optional(),
  });
}

export type InvestmentFormValues = z.infer<ReturnType<typeof buildInvestmentFormSchema>>;
