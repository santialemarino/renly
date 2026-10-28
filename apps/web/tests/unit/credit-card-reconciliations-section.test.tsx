import { createElement, type ReactNode } from 'react';
import { act, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CreditCardReconciliationsSection } from '@/app/(protected)/credit-cards/_components/credit-card-reconciliations-section';
import messages from '../../translations/en.json';

/*
 * The statements list under a credit-card row holds its loading line for the 500 ms display floor, on
 * the first load AND on the reload after a reconciliation is saved or deleted: without the floor a fast
 * answer swaps the list for the loading line and back too quickly to read.
 *
 * Motion is replaced with plain elements and the Radix dialogs with stubs that hand the test their
 * `onSuccess`, so what is asserted is the panel's own state, not the animation library's timing.
 */

vi.mock('motion/react', () => {
  const MOTION_PROPS = new Set(['initial', 'animate', 'exit', 'transition', 'layout']);
  const motion = new Proxy(
    {},
    {
      get: (_, tag: string) =>
        function MotionElement(props: Record<string, unknown>) {
          const rest = Object.fromEntries(
            Object.entries(props).filter(([key]) => !MOTION_PROPS.has(key)),
          );
          return createElement(tag, rest);
        },
    },
  );
  return { AnimatePresence: ({ children }: { children: ReactNode }) => children, motion };
});

const dialogs = vi.hoisted(() => ({ onFormSuccess: () => {} }));
vi.mock('@/app/(protected)/credit-cards/_components/reconciliation-form-dialog', () => ({
  ReconciliationFormDialog: ({ onSuccess }: { onSuccess: () => void }) => {
    dialogs.onFormSuccess = onSuccess;
    return null;
  },
}));
vi.mock('@/app/(protected)/credit-cards/_components/reconciliation-delete-dialog', () => ({
  ReconciliationDeleteDialog: () => null,
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const actions = vi.hoisted(() => ({ fetchStatements: vi.fn() }));
vi.mock('@/app/(protected)/credit-cards/credit-card-actions', () => actions);

const COPY = messages.creditCards.reconciliations;

function section() {
  return (
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <CreditCardReconciliationsSection cardId={3} bucketCurrencies={['ARS']} expanded />
    </NextIntlClientProvider>
  );
}

async function elapse(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

// The panel's own loading line (the bucket header repeats the same copy, so both are counted).
function loadingLines() {
  return screen.queryAllByText(COPY.loading).length;
}

beforeEach(() => {
  vi.useFakeTimers();
  // An empty list keeps the table (and its Radix tooltip) out of the render.
  actions.fetchStatements.mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('the credit-card statements list', () => {
  it('holds the loading line for the display floor on the first load', async () => {
    render(section());
    await elapse(400);
    expect(loadingLines()).toBeGreaterThan(0);
    await elapse(200);
    expect(loadingLines()).toBe(0);
    expect(screen.getByText(COPY.empty)).toBeTruthy();
  });

  it('holds it for the floor again on the reload after a reconciliation lands', async () => {
    render(section());
    await elapse(600);
    act(() => dialogs.onFormSuccess());
    await elapse(400);
    expect(actions.fetchStatements).toHaveBeenCalledTimes(2);
    expect(loadingLines()).toBeGreaterThan(0);
    await elapse(200);
    expect(loadingLines()).toBe(0);
  });
});
