import { expect, request as playwrightRequest, type APIRequestContext } from '@playwright/test';

import { e2eCredentials } from './auth';
import { testMarker } from './factories';

// Where the API is. A shell var like E2E_EMAIL — see the e2e-testing skill — with the local default.
// eslint-disable-next-line turbo/no-undeclared-env-vars
const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

/*
 * The figures the money sweep needs, seeded through the API and removed again afterwards.
 *
 * The harness account is a REAL account whose own figures may all be short, and a sweep over short
 * figures passes whatever the layout does — the defect only shows on a figure long enough to run out
 * of its card. So the seed carries the lengths that matter, in the account's own primary currency (a
 * figure the dashboard converts would shrink):
 *
 *   * the audit's own figures: 5,296,553.12 of expenses against 1,372,916.00 of income, so the net
 *     cash flow reads -3,923,637.12 — thirteen characters, negative, the typical long case;
 *   * one figure no card can hold at its design size: an account opened at 123,456,789,012.34, which
 *     is what makes the cash and net-worth cards exercise `fit` at the narrow widths — without it, a
 *     layout that had lost the fit would still pass;
 *   * six expense categories with the longest Spanish names ("Hogar y Mantenimiento", "Comida y
 *     Supermercado", …), because the finance legend truncated all six of six at 390px;
 *   * one expense on a card, for a card balance; and a subscription, an installment plan and an
 *     obligation due NEXT month, so the scheduler never turns them into expenses mid-run.
 *
 * Everything is named or noted with one marker and deleted in `cleanup`. Investments are not seeded:
 * the API can archive one but never delete it, so a spec against a real account would leave it behind.
 *
 * The seed owns its request context rather than borrowing a fixture's: it is created in a `beforeAll`
 * and removed in an `afterAll`, and Playwright refuses a `beforeAll`'s `request` fixture anywhere else —
 * which made the first version's cleanup fail on every row, and only warn.
 */

export interface MoneySeed {
  accountId: number;
  // The month the scheduled items fall in, for the payments calendar.
  scheduledYear: number;
  scheduledMonth: number;
  cleanup: () => Promise<void>;
}

// The six expense lines: category → amount. They sum to 5,296,553.12.
const EXPENSES: [string, string][] = [
  ['home_maintenance', '1500000.00'],
  ['food', '1200000.00'],
  ['dining', '900000.00'],
  ['sports', '700000.00'],
  ['personal_care', '600000.00'],
];
const CARD_EXPENSE: [string, string] = ['entertainment', '396553.12'];
const INCOME_AMOUNT = '1372916.00';
const OPENING_BALANCE = '123456789012.34';
const SCHEDULED_AMOUNT = '2468013.57';

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

async function apiToken(request: APIRequestContext): Promise<string> {
  const credentials = e2eCredentials();
  if (credentials === null) throw new Error('E2E_EMAIL / E2E_PASSWORD are required for this spec');
  const response = await request.post(`${API_BASE}/auth/login`, { data: credentials });
  expect(response.ok(), `login to ${API_BASE} failed with ${response.status()}`).toBe(true);
  return (await response.json()).access_token;
}

export async function seedMoney(): Promise<MoneySeed> {
  const request = await playwrightRequest.newContext();
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const marker = testMarker('money');
  const undo: (() => Promise<unknown>)[] = [];

  async function create(path: string, data: Record<string, unknown>): Promise<number> {
    const response = await request.post(`${API_BASE}${path}`, { headers, data });
    expect(response.ok(), `POST ${path}: ${response.status()} ${await response.text()}`).toBe(true);
    const id: number = (await response.json()).id;
    undo.push(async () => {
      const deleted = await request.delete(`${API_BASE}${path}/${id}`, { headers });
      if (!deleted.ok()) throw new Error(`DELETE ${path}/${id}: ${deleted.status()}`);
    });
    return id;
  }

  // Undo in reverse, never throwing: a cleanup that raises would replace the assertion that failed.
  async function cleanup() {
    for (const step of undo.reverse()) {
      try {
        await step();
      } catch (error) {
        console.warn(`e2e cleanup could not remove a row marked ${marker}:`, error);
      }
    }
    await request.dispose();
  }

  try {
    const settings = await (await request.get(`${API_BASE}/settings`, { headers })).json();
    const currency: string = settings.primary_currency ?? 'ARS';
    const today = new Date();
    const scheduled = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() + 1, 10));

    const accountId = await create('/accounts', {
      name: marker,
      type: 'bank',
      currency,
      opening_balance: OPENING_BALANCE,
      opening_date: isoDate(today),
    });
    const cardId = await create('/credit-cards', {
      name: marker,
      closing_day: 20,
      due_day: 5,
      currency,
    });
    for (const [category, amount] of EXPENSES) {
      await create('/expenses', {
        date: isoDate(today),
        amount,
        currency,
        category,
        notes: marker,
        payment_method: 'cash',
      });
    }
    await create('/expenses', {
      date: isoDate(today),
      amount: CARD_EXPENSE[1],
      currency,
      category: CARD_EXPENSE[0],
      notes: marker,
      payment_method: 'credit_card',
      credit_card_id: cardId,
    });
    await create('/income', {
      date: isoDate(today),
      amount: INCOME_AMOUNT,
      currency,
      category: 'salary',
      notes: marker,
    });
    await create('/subscriptions', {
      name: marker,
      amount: SCHEDULED_AMOUNT,
      currency,
      billing_cycle: 'monthly',
      next_billing_date: isoDate(scheduled),
    });
    await create('/installments', {
      name: marker,
      total_amount: '29616162.84',
      installment_amount: SCHEDULED_AMOUNT,
      currency,
      installments_count: 12,
      start_date: isoDate(scheduled),
    });
    await create('/payment-obligations', {
      name: marker,
      amount: SCHEDULED_AMOUNT,
      currency,
      next_due_date: isoDate(scheduled),
    });

    return {
      accountId,
      scheduledYear: scheduled.getUTCFullYear(),
      scheduledMonth: scheduled.getUTCMonth() + 1,
      cleanup,
    };
  } catch (error) {
    await cleanup();
    throw error;
  }
}
