import { expect, request as playwrightRequest, type APIRequestContext } from '@playwright/test';

import { API_BASE, apiToken } from './api';
import { testMarker } from './factories';

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
 *   * two holdings in the categories with the longest Spanish names ("Obligaciones Negociables",
 *     "Bonos Soberanos"), for the investor dashboard's figures and its donut legend;
 *   * one expense on a card, for a card balance and a card due-date row on the payments calendar;
 *     and a subscription, an installment plan and an obligation due NEXT month, so the scheduler
 *     never turns them into expenses mid-run.
 *
 * Every deletable row is named or noted with a per-run marker starting `e2e-money-`, and removed in
 * `cleanup`. A run that is KILLED never reaches `cleanup`, so the seed also begins by deleting every row
 * whose marker starts with that prefix — a leftover from any earlier run, whatever it was called.
 *
 * Holdings are the exception, because the API can archive an investment but never delete one. So they
 * are not per-run: each is ONE row per account under a fixed name, found again and unarchived by every
 * run and archived by its cleanup. Archived investments count nowhere (every metric reads active ones
 * only), so between runs the account carries two hidden rows and their snapshots — at most one snapshot
 * per day a run happened — and never more, however many runs are killed.
 */

export interface MoneySeed {
  accountId: number;
  // The month the scheduled items fall in, for the payments calendar.
  scheduledYear: number;
  scheduledMonth: number;
  cleanup: () => Promise<void>;
}

export const MONEY_MARKER_PREFIX = 'e2e-money-';

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
// Fixed names, so every run finds the same two rows (see above). Deliberately NOT under the
// `e2e-money-` prefix: the leftover sweep deletes that prefix, and these cannot be deleted.
const HOLDINGS: [string, string, string][] = [
  ['e2e-sweep-holding-corporate-bonds', 'corporate_bonds', '8250000.00'],
  ['e2e-sweep-holding-government-bonds', 'government_bonds', '6100000.00'],
];

// The list endpoints a leftover can sit in, in the order they must be deleted (an expense before the
// card it was charged to, a card before nothing, the account last), and the field carrying the marker.
const LEFTOVERS: { path: string; query: string; field: 'name' | 'notes' }[] = [
  { path: '/expenses', query: 'scope=private&page_size=100', field: 'notes' },
  { path: '/income', query: 'scope=private&page_size=100', field: 'notes' },
  { path: '/subscriptions', query: 'show_archived=true', field: 'name' },
  { path: '/installments', query: 'show_archived=true', field: 'name' },
  { path: '/payment-obligations', query: 'show_archived=true', field: 'name' },
  { path: '/credit-cards', query: 'show_archived=true', field: 'name' },
  { path: '/accounts', query: 'show_archived=true&scope=private&page_size=100', field: 'name' },
];

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

// A list endpoint's rows, whether it answers with a bare array or a page.
function rows(body: unknown): Record<string, unknown>[] {
  if (Array.isArray(body)) return body;
  return ((body as { items?: Record<string, unknown>[] })?.items ?? []) as Record<
    string,
    unknown
  >[];
}

// Deletes every row a previous run left behind, and returns how many it found.
export async function removeMoneyLeftovers(
  request: APIRequestContext,
  headers: Record<string, string>,
): Promise<number> {
  let removed = 0;
  for (const { path, query, field } of LEFTOVERS) {
    const url = `${API_BASE}${path}?${query}&search=${encodeURIComponent(MONEY_MARKER_PREFIX)}`;
    const listed = await request.get(url, { headers });
    expect(listed.ok(), `GET ${path}: ${listed.status()}`).toBe(true);
    const stale = rows(await listed.json()).filter((row) =>
      String(row[field] ?? '').startsWith(MONEY_MARKER_PREFIX),
    );
    for (const row of stale) {
      const deleted = await request.delete(`${API_BASE}${path}/${row.id}`, { headers });
      expect(deleted.ok(), `DELETE ${path}/${row.id}: ${deleted.status()}`).toBe(true);
      removed += 1;
    }
  }
  return removed;
}

export async function seedMoney(): Promise<MoneySeed> {
  const token = await apiToken();
  const request = await playwrightRequest.newContext();
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

  // Finds the fixed-name holding (active or archived) or creates it, makes it active, values it today.
  async function holding(name: string, category: string, value: string, currency: string) {
    const listed = await request.get(
      `${API_BASE}/investments?active_only=false&page_size=100&search=${encodeURIComponent(name)}`,
      { headers },
    );
    expect(listed.ok(), `GET /investments: ${listed.status()}`).toBe(true);
    const existing = rows(await listed.json()).find((row) => row.name === name);
    let id = existing?.id as number | undefined;
    if (id === undefined) {
      const created = await request.post(`${API_BASE}/investments`, {
        headers,
        data: { name, category, base_currency: currency },
      });
      expect(created.ok(), `POST /investments: ${created.status()}`).toBe(true);
      id = (await created.json()).id as number;
    } else {
      const unarchived = await request.patch(`${API_BASE}/investments/${id}/unarchive`, {
        headers,
      });
      expect(unarchived.ok(), `PATCH unarchive: ${unarchived.status()}`).toBe(true);
    }
    undo.push(async () => {
      const archived = await request.patch(`${API_BASE}/investments/${id}/archive`, { headers });
      if (!archived.ok()) throw new Error(`PATCH /investments/${id}/archive: ${archived.status()}`);
    });
    const snapshot = await request.post(`${API_BASE}/investments/${id}/snapshots`, {
      headers,
      data: { date: isoDate(new Date()), value, currency },
    });
    expect(snapshot.ok(), `POST snapshot: ${snapshot.status()} ${await snapshot.text()}`).toBe(
      true,
    );
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
    await removeMoneyLeftovers(request, headers);

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
    // Closing on the 31st (the month's last day) and due on the 10th: the bill due NEXT month is the
    // statement closing at the end of THIS one, which holds today's charge whatever today is — so the
    // payments calendar's month shows a card due-date row, with the card's marker-long name beside it.
    const cardId = await create('/credit-cards', {
      name: marker,
      closing_day: 31,
      due_day: 10,
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
    for (const [name, category, value] of HOLDINGS) await holding(name, category, value, currency);

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
