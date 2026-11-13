import { createElement, type ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { DashboardFooter } from '@/app/(protected)/dashboard/_components/dashboard-footer';
import type { DashboardLiquidity, DashboardOverview } from '@/lib/api/dashboard';
import messages from '../../translations/en.json';

// Radix primitives cannot mount in this suite (a second React), so the card's shell renders plain.
vi.mock('@repo/ui/components', () => {
  const plain = (tag: string) =>
    function Plain({ children }: { children?: ReactNode }) {
      return createElement(tag, null, children);
    };
  return {
    Card: plain('div'),
    Tooltip: plain('span'),
    TooltipContent: plain('span'),
    TooltipTrigger: ({ children }: { children?: ReactNode }) => children,
  };
});

/*
 * The savings-rate card. Past ten times the income the API withholds the rate (a sliver of income
 * against ordinary spending once printed -3,923,637%), and the card says why rather than printing a
 * bare dash or the absurd figure.
 */

const LIQUIDITY: DashboardLiquidity = {
  ratio: null,
  state: 'unknown',
  fixedMonthlyCommitments: 0,
  monthlyIncome: 0,
  threshold: 30,
  incomeWindowDays: 90,
  actualWindowDays: 0,
  currency: 'ARS',
  skippedEntities: [],
};

function renderFooter(over: Partial<DashboardOverview>) {
  const overview = {
    totalIncome: 0,
    totalExpenses: 0,
    savingsRate: null,
    savingsRateOffScale: false,
    incomeExpenseRatio: null,
    ...over,
  } as DashboardOverview;
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <DashboardFooter
        overview={overview}
        liquidity={LIQUIDITY}
        savingsRateHealthyPct={20}
        savingsRateModeratePct={10}
        incomeExpenseRatioHealthy={1.5}
      />
    </NextIntlClientProvider>,
  );
}

describe('the savings-rate card', () => {
  it('shows a dash that explains itself when the rate is off the scale', () => {
    renderFooter({ totalIncome: 0.05, totalExpenses: 1961.87, savingsRateOffScale: true });
    const note = screen.getByTestId('savings-rate-off-scale');
    expect(note.textContent).toBe('—');
    expect(note.getAttribute('aria-label')).toBe(messages.dashboard.health.savingsRateOffScale);
    // Reachable by keyboard, so the tooltip is not mouse-only.
    expect(note.getAttribute('tabindex')).toBe('0');
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('prints an ordinary rate as a percentage', () => {
    renderFooter({ totalIncome: 1000, totalExpenses: 800, savingsRate: 0.2 });
    expect(screen.queryByTestId('savings-rate-off-scale')).toBeNull();
    expect(screen.getByText(/20/)).toBeTruthy();
  });

  it('keeps a plain dash, with no explanation, when there is no income at all', () => {
    renderFooter({});
    expect(screen.queryByTestId('savings-rate-off-scale')).toBeNull();
  });
});
