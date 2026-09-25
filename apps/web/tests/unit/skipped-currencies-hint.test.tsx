import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { createTranslator, NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DashboardPage from '@/app/(protected)/dashboard/page';
import ExpensesPage from '@/app/(protected)/expenses/page';
import FinanceDashboardPage from '@/app/(protected)/finance-dashboard/page';
import IncomePage from '@/app/(protected)/income/page';
import PaymentsCalendarPage from '@/app/(protected)/payments-calendar/page';
import en from '../../translations/en.json';

/*
 * A page whose totals left a currency out has to SAY so — and this is the half of that contract a
 * source scan cannot reach. `skipped-currencies-contract.test.ts` proves the web declares and maps the
 * field; only rendering the page proves the hint appears. Setting `show={false}` on the finance
 * dashboard's and the calendar's hints left that scan, and every other test, green.
 *
 * So every page that reads a skip set is rendered for real — the population derived from the source,
 * not listed: its async server function is awaited with the API layer mocked, and the element tree it
 * returns is mounted. The hint is the one real child. Everything else a page composes is stubbed to
 * nothing — the charts, pickers and lists are tested where they live, and several render Radix
 * primitives, which this suite cannot mount (see the testing skill).
 *
 * Asserted against the real English copy, because the sentence naming the codes is the point.
 */

const SKIPPED = ['CHF', 'JPY'];

const data = vi.hoisted(() => ({ skipped: { value: [] as string[] } }));

vi.mock('next/headers', () => ({ cookies: async () => ({ get: () => undefined }) }));
vi.mock('next-intl/server', async () => {
  const messages = (await import('../../translations/en.json')).default;
  return {
    getTranslations: async (namespace: string) =>
      createTranslator({ locale: 'en', messages, namespace: namespace as never }),
  };
});
vi.mock('@/lib/i18n/formatters-server', async () => {
  const { createFormatters } = await import('@/lib/i18n/create-formatters');
  return { getFormatters: async () => createFormatters('en', 'UTC') };
});
vi.mock('@/lib/utils/page-metadata', () => ({ generatePageMetadata: async () => ({}) }));

// --- The API layer, answering with the skip set under test ---

vi.mock('@/lib/api/settings', () => ({
  getSettings: async () => null,
  getPageSettings: async () => ({ settings: null, creditCards: [] }),
}));
vi.mock('@/lib/api/finance-metrics', () => {
  const response = () => ({ skippedCurrencies: data.skipped.value });
  return {
    getFinanceOverview: async () => response(),
    getFinanceMonthly: async () => response(),
    getExpenseBreakdown: async () => response(),
    getIncomeBreakdown: async () => response(),
  };
});
vi.mock('@/lib/api/payments-calendar', () => ({
  getPaymentsCalendar: async () => ({ items: [], skippedCurrencies: data.skipped.value }),
}));
vi.mock('@/lib/api/expenses', () => ({
  getExpenses: async () => ({ items: [], skippedCurrencies: data.skipped.value }),
}));
vi.mock('@/lib/api/income', () => ({
  getIncome: async () => ({ items: [], skippedCurrencies: data.skipped.value }),
}));
vi.mock('@/lib/api/dashboard', () => ({
  getDashboardOverview: async () => ({
    hasHoldings: false,
    hasShared: false,
    skippedCurrencies: data.skipped.value,
  }),
  getDashboardEvolution: async () => ({ skippedCurrencies: data.skipped.value }),
  getDashboardComposition: async () => ({ items: [], skippedCurrencies: data.skipped.value }),
  getDashboardLiquidity: async () => ({}),
}));
vi.mock('@/lib/api/accounts', () => ({ getAccounts: async () => [] }));
vi.mock('@/lib/api/exchange-rates', () => ({ getSupportedCurrencies: async () => [] }));
vi.mock('@/lib/api/groups', () => ({ getGroups: async () => [] }));
vi.mock('@/lib/api/installments', () => ({ getInstallments: async () => [] }));
vi.mock('@/lib/api/onboarding', () => ({ getOnboardingStatus: async () => null }));
vi.mock('@/lib/api/payment-obligations', () => ({ getPaymentObligations: async () => [] }));
vi.mock('@/lib/api/subscriptions', () => ({ getSubscriptions: async () => [] }));

// --- Everything the pages compose besides the hint ---

vi.mock('@/app/(protected)/_components/page-header', () => ({ PageHeader: () => null }));
vi.mock('@/app/(protected)/_components/dashboard-period-picker', () => ({
  DashboardPeriodPicker: () => null,
}));
vi.mock('@/components/concept-hint', () => ({ ConceptHint: () => null }));
vi.mock('@/components/dismissable-currency-hint', () => ({ DismissableCurrencyHint: () => null }));
vi.mock('@/app/(protected)/dashboard/_components/dashboard-composition', () => ({
  DashboardComposition: () => null,
}));
vi.mock('@/app/(protected)/dashboard/_components/dashboard-evolution', () => ({
  DashboardEvolutionChart: () => null,
}));
vi.mock('@/app/(protected)/dashboard/_components/dashboard-footer', () => ({
  DashboardFooter: () => null,
}));
vi.mock('@/app/(protected)/dashboard/_components/dashboard-metric-cards', () => ({
  DashboardMetricCards: () => null,
}));
vi.mock('@/app/(protected)/dashboard/_components/onboarding-welcome', () => ({
  OnboardingWelcome: () => null,
}));
vi.mock('@/app/(protected)/expenses/_components/expenses-data-table', () => ({
  ExpensesDataTable: () => null,
}));
vi.mock('@/app/(protected)/expenses/_components/expenses-toolbar', () => ({
  ExpensesToolbar: () => null,
}));
vi.mock('@/app/(protected)/expenses/_components/sample-expenses-table', () => ({
  SampleExpensesTable: () => null,
}));
vi.mock('@/app/(protected)/income/_components/income-data-table', () => ({
  IncomeDataTable: () => null,
}));
vi.mock('@/app/(protected)/income/_components/income-toolbar', () => ({
  IncomeToolbar: () => null,
}));
vi.mock('@/app/(protected)/income/_components/sample-income-table', () => ({
  SampleIncomeTable: () => null,
}));
vi.mock('@/app/(protected)/finance-dashboard/_components/finance-dashboard-distribution', () => ({
  FinanceDashboardDistribution: () => null,
}));
vi.mock('@/app/(protected)/finance-dashboard/_components/finance-dashboard-metric-cards', () => ({
  FinanceDashboardMetricCards: () => null,
}));
vi.mock('@/app/(protected)/finance-dashboard/_components/finance-dashboard-monthly-chart', () => ({
  FinanceDashboardMonthlyChart: () => null,
}));
vi.mock('@/app/(protected)/payments-calendar/_components/payments-calendar-header', () => ({
  PaymentsCalendarHeader: () => null,
}));
vi.mock('@/app/(protected)/payments-calendar/_components/payments-calendar-list', () => ({
  PaymentsCalendarList: () => null,
}));

const NO_PARAMS = { searchParams: Promise.resolve({}) };

// [route segment, translation namespace, the page's own render].
const PAGES: [string, keyof typeof en, () => Promise<ReactNode>][] = [
  ['dashboard', 'dashboard', () => DashboardPage(NO_PARAMS)],
  ['expenses', 'expenses', () => ExpensesPage(NO_PARAMS)],
  ['finance-dashboard', 'financeDashboard', () => FinanceDashboardPage(NO_PARAMS)],
  ['income', 'income', () => IncomePage(NO_PARAMS)],
  ['payments-calendar', 'paymentsCalendar', () => PaymentsCalendarPage(NO_PARAMS)],
];

const PROTECTED = join(__dirname, '..', '..', 'app', '(protected)');

// Every protected route whose page reads a `skippedCurrencies` field, by folder — derived from the
// source, so a page that starts reading one is held to rendering it without anybody listing it here.
function pagesReadingTheField(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === 'page.tsx' && readFileSync(full, 'utf8').includes('.skippedCurrencies'))
        found.push(relative(PROTECTED, dir));
    }
  };
  walk(PROTECTED);
  return found.sort();
}

async function renderPage(page: () => Promise<ReactNode>) {
  const tree = await page();
  return render(
    <NextIntlClientProvider locale="en" messages={en} timeZone="UTC">
      {tree}
    </NextIntlClientProvider>,
  );
}

function hintFor(namespace: keyof typeof en, codes: string[]): string {
  const t = createTranslator({ locale: 'en', messages: en, namespace: namespace as never });
  return (t as unknown as (key: string, values: object) => string)('skippedCurrencies', {
    currencies: new Intl.ListFormat('en', { type: 'conjunction' }).format(codes),
  });
}

describe('the pages under test', () => {
  it('are every page that reads a skip set', () => {
    // Anti-vacuity and completeness at once: the derived list is non-empty, and the rendered list is
    // exactly it. A sixth page reading the field fails here until it is rendered below.
    const derived = pagesReadingTheField();
    expect(derived.length).toBeGreaterThanOrEqual(5);
    expect(derived).toEqual(PAGES.map(([route]) => route).sort());
  });
});

describe.each(PAGES)('/%s', (_route, namespace, page) => {
  beforeEach(() => {
    data.skipped.value = [];
  });

  it('names every skipped currency in the warning', async () => {
    data.skipped.value = SKIPPED;
    await renderPage(page);
    const text = hintFor(namespace, SKIPPED);
    // The copy itself, resolved — not a key path handed back by a missing message.
    expect(text).not.toContain('skippedCurrencies');
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('says nothing when every row converted', async () => {
    await renderPage(page);
    expect(screen.queryByText(hintFor(namespace, SKIPPED))).not.toBeInTheDocument();
    expect(screen.queryByText(/CHF/)).not.toBeInTheDocument();
  });
});
