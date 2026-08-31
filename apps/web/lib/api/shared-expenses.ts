/*
 * Server-only types + mappers for a group's shared expenses — the flow half of shared money. Reads go
 * through `getSharedExpenses`; mutations are server actions in
 * `app/(protected)/shared/shared-expense-actions.ts`.
 *
 * Two shapes of the API's honesty survive into these types unchanged, and the UI must respect both:
 *
 *   * A member's position in one expense is TWO figures, not one: what they consumed (`amount`) and
 *     what they fronted (`paidAmount`). Their balance is the difference, and both columns sum to the
 *     expense's total — which is what makes the group's balances sum to zero. Never render one as if
 *     it were the other.
 *   * `payerMemberId` is DERIVED from the funding and is null whenever a SHARED account fronted it,
 *     including a pot with exactly one owner. There is no payer column precisely because joint money
 *     is fronted by that pot's owners in their own proportions, so "X paid" must never appear on a
 *     shared-account expense however its ownership happens to be divided.
 *
 * Money figures stay STRINGS end to end, as everywhere else in the app: they are NUMERIC(18,2)
 * server-side, and parsing them into a JS number would round exactly the digits the balance depends on.
 */

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { SplitMethod } from '@/lib/constants/shared-expenses';

// --- Raw types (API JSON shape, snake_case) ---

interface SharedExpenseSplitRaw {
  member_id: number;
  display_name: string;
  amount: string;
  paid_amount: string;
  is_self: boolean;
}

interface SharedExpenseRaw {
  id: number;
  group_id: number;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  split_method: SplitMethod;
  paid_from_account_id: number | null;
  paid_from_account_name: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  payer_member_id: number | null;
  payer_display_name: string | null;
  my_share: string | null;
  splits: SharedExpenseSplitRaw[];
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface SharedExpenseSplit {
  memberId: number;
  displayName: string;
  // What this member consumed — their share, and the figure that becomes their own expense.
  amount: string;
  // What this member fronted. Zero for a participant who paid nothing, and the whole amount for a
  // single payer; for a shared-account expense every owner fronts their ownership proportion.
  paidAmount: string;
  isSelf: boolean;
}

export interface SharedExpense {
  id: number;
  groupId: number;
  date: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  category: string | null;
  notes: string | null;
  splitMethod: SplitMethod;
  paidFromAccountId: number | null;
  // Denormalized so a row reads without a second request, and so it still names the account after it
  // has been archived — the same reason a card settlement carries its account's name.
  paidFromAccountName: string | null;
  paymentMethod: string | null;
  creditCardId: number | null;
  /*
   * Who fronted it, DERIVED from the funding rather than stored. Null whenever a shared account did:
   * the pot's owners fronted it in their own proportions, which no single column could say.
   */
  payerMemberId: number | null;
  payerDisplayName: string | null;
  // The viewer's own share, or null when they took no part in this expense.
  myShare: string | null;
  splits: SharedExpenseSplit[];
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapSplit(raw: SharedExpenseSplitRaw): SharedExpenseSplit {
  return {
    memberId: raw.member_id,
    displayName: raw.display_name,
    amount: raw.amount,
    paidAmount: raw.paid_amount,
    isSelf: raw.is_self,
  };
}

function mapSharedExpense(raw: SharedExpenseRaw): SharedExpense {
  return {
    id: raw.id,
    groupId: raw.group_id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    category: raw.category,
    notes: raw.notes,
    splitMethod: raw.split_method,
    paidFromAccountId: raw.paid_from_account_id,
    paidFromAccountName: raw.paid_from_account_name,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    payerMemberId: raw.payer_member_id,
    payerDisplayName: raw.payer_display_name,
    myShare: raw.my_share,
    splits: raw.splits.map(mapSplit),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

/*
 * A group's shared expenses, newest first, each with every member's position in it.
 *
 * Returns null for a group that does not exist OR that the caller is not a member of — the API
 * answers 404 for both, so the hub renders notFound() either way and an id cannot be probed. The
 * whole list comes back unpaginated, which is what the API offers; the hub pages it client-side.
 */
export async function getSharedExpenses(groupId: number): Promise<SharedExpense[] | null> {
  const res = await authenticatedFetch(`/groups/${groupId}/expenses`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch shared expenses');
  const raw: SharedExpenseRaw[] = await res.json();
  return raw.map(mapSharedExpense);
}
