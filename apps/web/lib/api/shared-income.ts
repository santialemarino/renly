/*
 * Server-only types + mappers for a group's shared income — the income half of the flow half. Reads go
 * through `getSharedIncome`; mutations are server actions in
 * `app/(protected)/shared/shared-income-actions.ts`.
 *
 * Two shapes of the API's honesty survive into these types unchanged, and the UI must respect both.
 * They are the mirror of the shared-expense pair, with the two sides swapped:
 *
 *   * A member's position in one income row is TWO figures, not one: what they are entitled to
 *     (`amount`) and what actually reached them (`receivedAmount`). Their balance is the difference,
 *     and both columns sum to the row's total — which is what makes the group's balances sum to zero.
 *     Never render one as if it were the other.
 *   * `receivedByMemberId` is DERIVED from the destination and is null whenever the money landed in a
 *     SHARED account, including a pot with exactly one owner. There is no receiver column precisely
 *     because joint money reaches that pot's owners in their own proportions, so "X received it" must
 *     never appear on a joint row however its ownership happens to be divided.
 *
 * Money figures stay STRINGS end to end, as everywhere else in the app: they are NUMERIC(18,2)
 * server-side, and parsing them into a JS number would round exactly the digits the balance depends on.
 */

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { SplitMethod } from '@/lib/constants/shared-expenses';
import type { IncomeDestination } from '@/lib/constants/shared-income';

// --- Raw types (API JSON shape, snake_case) ---

interface SharedIncomeSplitRaw {
  member_id: number;
  display_name: string;
  amount: string;
  received_amount: string;
  is_self: boolean;
}

interface SharedIncomeRaw {
  id: number;
  group_id: number;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  split_method: SplitMethod;
  destination: IncomeDestination;
  source_investment_id: number | null;
  source_investment_name: string | null;
  paid_to_account_id: number | null;
  paid_to_account_name: string | null;
  received_by_member_id: number | null;
  received_by_display_name: string | null;
  my_share: string | null;
  splits: SharedIncomeSplitRaw[];
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface SharedIncomeSplit {
  memberId: number;
  displayName: string;
  // What this member is entitled to — their share, and the figure that becomes their own income.
  amount: string;
  // What actually reached this member. Zero for somebody still waiting for theirs, the whole amount
  // for a single collector; for a joint row every owner receives their ownership proportion.
  receivedAmount: string;
  isSelf: boolean;
}

export interface SharedIncome {
  id: number;
  groupId: number;
  date: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  category: string | null;
  notes: string | null;
  splitMethod: SplitMethod;
  destination: IncomeDestination;
  // The co-owned asset it came from, which is what seeds the default split (F1).
  sourceInvestmentId: number | null;
  /*
   * That asset's name. Null in two legitimate cases rather than one: the asset is gone (the FK is ON
   * DELETE SET NULL, because the money arrived whatever later happened to the asset), or it sits in a
   * pot this viewer is not permitted to see.
   */
  sourceInvestmentName: string | null;
  paidToAccountId: number | null;
  // Denormalized so a row reads without a second request, and so it still names the account after it
  // has been archived — the same reason a card settlement carries its account's name.
  paidToAccountName: string | null;
  /*
   * Who holds it, DERIVED from the destination rather than stored. Null whenever a shared account
   * received it: the pot's owners did, in their own proportions, which no single column could say.
   */
  receivedByMemberId: number | null;
  receivedByDisplayName: string | null;
  // The viewer's own share, or null when they are entitled to none of this row.
  myShare: string | null;
  splits: SharedIncomeSplit[];
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapSplit(raw: SharedIncomeSplitRaw): SharedIncomeSplit {
  return {
    memberId: raw.member_id,
    displayName: raw.display_name,
    amount: raw.amount,
    receivedAmount: raw.received_amount,
    isSelf: raw.is_self,
  };
}

function mapSharedIncome(raw: SharedIncomeRaw): SharedIncome {
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
    destination: raw.destination,
    sourceInvestmentId: raw.source_investment_id,
    sourceInvestmentName: raw.source_investment_name,
    paidToAccountId: raw.paid_to_account_id,
    paidToAccountName: raw.paid_to_account_name,
    receivedByMemberId: raw.received_by_member_id,
    receivedByDisplayName: raw.received_by_display_name,
    myShare: raw.my_share,
    splits: raw.splits.map(mapSplit),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

/*
 * A group's shared income, newest first, each row with every member's position in it.
 *
 * Returns null for a group that does not exist OR that the caller is not a member of — the API
 * answers 404 for both, so the hub renders notFound() either way and an id cannot be probed. The whole
 * list comes back unpaginated, which is what the API offers; the hub pages it client-side.
 */
export async function getSharedIncome(groupId: number): Promise<SharedIncome[] | null> {
  const res = await authenticatedFetch(`/groups/${groupId}/income`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch shared income');
  const raw: SharedIncomeRaw[] = await res.json();
  return raw.map(mapSharedIncome);
}
