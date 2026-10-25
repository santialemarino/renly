import type { ReactNode } from 'react';
import { act, render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DistributionDonut,
  type DistributionSlice,
} from '@/app/(protected)/_components/distribution-donut';
import en from '../../translations/en.json';

/*
 * The card animates its height to its legend's, measured by a ResizeObserver on the legend. The legend
 * only exists while there is data, so a card that first renders its empty label (a user with income
 * but no expenses, on the expense mode) and then switches to a set with data must start measuring the
 * legend that just mounted — measuring once on mount left that card at height 0 with its body hidden.
 */

type Observed = { element: Element; fire: (height: number) => void };
let observed: Observed[] = [];

class StubResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe(element: Element) {
    observed.push({
      element,
      fire: (height) =>
        this.callback(
          [{ target: element, contentRect: { height } } as unknown as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        ),
    });
  }
  unobserve() {}
  disconnect() {}
}

const SLICES: DistributionSlice[] = [
  { name: 'Rent', value: 600, percentage: 60 },
  { name: 'Food', value: 400, percentage: 40 },
];

function card(slices: DistributionSlice[], dataKey: string): ReactNode {
  return (
    <NextIntlClientProvider locale="en" messages={en} timeZone="UTC">
      <DistributionDonut
        title="Distribution"
        slices={slices}
        dataKey={dataKey}
        emptyLabel="Nothing yet"
      />
    </NextIntlClientProvider>
  );
}

beforeEach(() => {
  observed = [];
  vi.stubGlobal('ResizeObserver', StubResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DistributionDonut', () => {
  it('grows to the legend when data arrives after the empty label', () => {
    const view = render(card([], 'expense'));
    expect(view.getByText('Nothing yet')).toBeTruthy();

    view.rerender(card(SLICES, 'income'));
    // The animated wrapper is the one element whose height the card sets; the legend is its child.
    const wrapper = view.container.querySelector<HTMLElement>('[class*="transition-[height]"]');
    expect(wrapper).not.toBeNull();
    const legend = observed.find(({ element }) => element.parentElement === wrapper);
    expect(legend, 'nothing observes the legend that mounted with the data').toBeDefined();

    act(() => legend!.fire(120));
    expect(wrapper!.style.height).toBe('120px');
  });
});
