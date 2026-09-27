import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it } from 'vitest';

import { DashboardSharedBreakdown } from '@/app/(protected)/dashboard/_components/dashboard-shared-breakdown';
import { MetricCard } from '@/components/metric-card';
import { MoneyFigure } from '@/components/money-figure';
import { SignedAmountCell } from '@/components/signed-amount-cell';
import { TableSectionRow } from '@/components/table-section-row';
import type { DashboardOverview } from '@/lib/api/dashboard';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * The money display components carry the `data-money` marker, and the marker sits on the element that
 * holds the WHOLE figure.
 *
 * The e2e overflow sweep finds figures by this attribute and nothing else, so it is only as good as
 * the components that put it there: a component that dropped it would make its figures invisible to
 * the sweep, and the sweep's "found at least one" floor only notices when a page loses ALL of them.
 * This pins each shared component individually, and pins what the marked element contains — the sign
 * and the currency code are part of the figure a reader sees, so they must be inside the box the sweep
 * measures, or a clipped code would pass.
 */

function withIntl(locale: 'en' | 'es', node: ReactNode) {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === 'en' ? en : es} timeZone="UTC">
      {node}
    </NextIntlClientProvider>,
  );
}

function figures(container: HTMLElement): string[] {
  return [...container.querySelectorAll('[data-money]')].map((el) => el.textContent ?? '');
}

describe('MoneyFigure', () => {
  it('marks the figure and keeps it on one line', () => {
    const { container } = render(<MoneyFigure>5,296,553.12</MoneyFigure>);
    const el = container.querySelector('[data-money]');
    expect(el?.textContent).toBe('5,296,553.12');
    expect(el?.className).toContain('whitespace-nowrap');
  });

  // What `fit` does to the SIZE is not asserted here: jsdom's CSS parser drops a `cqi` value, so the
  // style would read empty whatever the component wrote. The e2e money sweep measures it in a real
  // browser instead, at the widths where it has to engage.
});

describe('the shared money components', () => {
  it('MetricCard marks an amount, formatted in the reader’s locale', () => {
    expect(
      figures(withIntl('en', <MetricCard label="Net worth" amount={-3923637.12} />).container),
    ).toEqual(['-3,923,637.12']);
    expect(
      figures(withIntl('es', <MetricCard label="Patrimonio" amount={-3923637.12} />).container),
    ).toEqual(['-3.923.637,12']);
  });

  it('MetricCard does NOT mark a figure that is not money', () => {
    const { container } = withIntl('en', <MetricCard label="TWR" text="+12.5%" />);
    expect(figures(container)).toEqual([]);
    expect(container.textContent).toContain('+12.5%');
  });

  it('SignedAmountCell marks the sign together with the amount', () => {
    const { container } = withIntl(
      'en',
      <SignedAmountCell amount="5296553.12" currency="ARS" outgoing />,
    );
    expect(figures(container)).toHaveLength(1);
    expect(figures(container)[0]).toMatch(/^−.*5,296,553\.12/);
  });

  it('TableSectionRow marks each total WITH its currency code', () => {
    const { container } = withIntl(
      'en',
      <table>
        <tbody>
          <TableSectionRow
            section={{
              scope: 'private',
              potId: null,
              potName: null,
              groupId: null,
              groupName: null,
              canWrite: true,
              count: 2,
              totals: [
                { currency: 'ARS', amount: '1452000' },
                { currency: 'USD', amount: '200' },
              ],
            }}
            colSpan={4}
            countLabel="2 expenses"
          />
        </tbody>
      </table>,
    );
    const marked = figures(container);
    expect(marked).toHaveLength(2);
    expect(marked[0]).toMatch(/1,452,000.*ARS$/);
    expect(marked[1]).toMatch(/200 USD$/);
  });

  it('the dashboard’s shared breakdown marks every figure it shows', () => {
    const overview = {
      netWorth: 1630,
      privateNetWorth: 1200,
      sharedNetWorth: 430,
      sharedPotValue: 400,
      sharedReceivable: 55,
      sharedPayable: 20,
      hasShared: true,
      undividedPots: [],
    } as unknown as DashboardOverview;
    const { container } = withIntl('en', <DashboardSharedBreakdown overview={overview} />);
    expect(figures(container)).toEqual(['1,200', '430', '55', '20']);
  });
});
