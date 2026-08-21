import type { Expense } from '@/lib/api/expenses';
import type { IncomeEntry } from '@/lib/api/income';
import type { Investment } from '@/lib/api/investments';

/*
 * Client-rendered first-run sample data. Shown in place of empty sections for a brand-new account
 * so newcomers see what populated tables look like before entering anything of their own. This is
 * a pure frontend fixture — never persisted, never sent to the API. Negative ids keep the rows
 * unmistakably distinct from real ones. Categories/currencies use real enum values so they render
 * through the same translations and formatters as real rows.
 */

const SAMPLE_TIMESTAMP = '2026-01-15T12:00:00Z';

export const sampleInvestments: Investment[] = [
  {
    id: -1,
    name: 'Apple',
    category: 'stocks',
    baseCurrency: 'USD',
    ticker: 'AAPL',
    broker: 'Interactive Brokers',
    notes: 'Long-term hold.',
    isActive: true,
    hasSnapshots: true,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
    collections: [],
  },
  {
    id: -2,
    name: 'Bitcoin',
    category: 'crypto',
    baseCurrency: 'USD',
    ticker: 'BTC',
    broker: null,
    notes: null,
    isActive: true,
    hasSnapshots: true,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
    collections: [],
  },
  {
    id: -3,
    name: 'Plazo Fijo',
    category: 'term_deposit',
    baseCurrency: 'ARS',
    ticker: null,
    broker: 'Banco Nación',
    notes: null,
    isActive: true,
    hasSnapshots: false,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
    collections: [],
  },
];

export const sampleExpenses: Expense[] = [
  {
    id: -1,
    date: '2026-01-05',
    amount: '45000.00',
    currency: 'ARS',
    convertedAmount: null,
    category: 'food',
    notes: 'Weekly groceries.',
    paymentMethod: 'debit',
    creditCardId: null,
    accountId: null,
    source: 'manual',
    paymentObligationId: null,
    subscriptionId: null,
    installmentId: null,
    reconciliationId: null,
    accountReconciliationId: null,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
  },
  {
    id: -2,
    date: '2026-01-03',
    amount: '12.99',
    currency: 'USD',
    convertedAmount: null,
    category: 'subscriptions',
    notes: 'Streaming.',
    paymentMethod: 'credit_card',
    creditCardId: null,
    accountId: null,
    source: 'manual',
    paymentObligationId: null,
    subscriptionId: null,
    installmentId: null,
    reconciliationId: null,
    accountReconciliationId: null,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
  },
  {
    id: -3,
    date: '2026-01-01',
    amount: '320000.00',
    currency: 'ARS',
    convertedAmount: null,
    category: 'rent',
    notes: null,
    paymentMethod: 'transfer',
    creditCardId: null,
    accountId: null,
    source: 'manual',
    paymentObligationId: null,
    subscriptionId: null,
    installmentId: null,
    reconciliationId: null,
    accountReconciliationId: null,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
  },
];

export const sampleIncome: IncomeEntry[] = [
  {
    id: -1,
    date: '2026-01-01',
    amount: '900000.00',
    currency: 'ARS',
    convertedAmount: null,
    category: 'salary',
    notes: 'Monthly salary.',
    accountId: null,
    source: 'manual',
    reconciliationId: null,
    accountReconciliationId: null,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
  },
  {
    id: -2,
    date: '2026-01-10',
    amount: '500.00',
    currency: 'USD',
    convertedAmount: null,
    category: 'freelance',
    notes: 'Design project.',
    accountId: null,
    source: 'manual',
    reconciliationId: null,
    accountReconciliationId: null,
    createdAt: SAMPLE_TIMESTAMP,
    updatedAt: SAMPLE_TIMESTAMP,
  },
];
