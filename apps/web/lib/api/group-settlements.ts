/*
 * Server-only types + mappers for a group's balances and the settlements that clear them. Reads go
 * through the three functions here; mutations are server actions in
 * `app/(protected)/shared/settlement-actions.ts`.
 *
 * Three shapes of the API's honesty survive into these types unchanged:
 *
 *   * Balances NEVER net across currencies. One bucket per currency, each with its own zero-sum and
 *     its own settle line — owing dollars while being owed pesos is a real state, and merging the two
 *     would invent a rate nobody agreed to. `myConvertedBalance` is a glance figure at the viewer's
 *     own rate and is never what anybody settles.
 *   * `canConfirm` / `canDelete` are resolved SERVER-SIDE, because they follow from who the caller is
 *     and a second copy of them would be a second copy of a permission check. Render from them.
 *   * A settlement carries up to three amounts, and the two cash legs are each set only when that
 *     side crossed currencies. `null` there means "the account moved exactly what came off the
 *     bucket", not "unknown" — there is no stored rate anywhere, the pair of amounts is the record.
 *
 * Money figures stay STRINGS end to end, for the reason every other module keeps them: they are
 * NUMERIC(18,2) server-side and a JS number would round the digits a balance is checked against.
 */

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { SettlementStatus } from '@/lib/constants/group-settlements';
import type { SplitMethod } from '@/lib/constants/shared-expenses';

// --- Raw types (API JSON shape, snake_case) ---

interface GroupMemberBalanceRaw {
  member_id: number;
  display_name: string;
  amount: string;
  is_self: boolean;
}

interface GroupSettleSuggestionRaw {
  from_member_id: number;
  from_display_name: string;
  to_member_id: number;
  to_display_name: string;
  amount: string;
}

interface GroupCurrencyBalanceRaw {
  currency: string;
  balances: GroupMemberBalanceRaw[];
  suggestions: GroupSettleSuggestionRaw[];
  my_balance: string;
  my_converted_balance: string | null;
}

interface GroupBalancesRaw {
  group_id: number;
  buckets: GroupCurrencyBalanceRaw[];
  display_currency: string | null;
  skipped_currencies: string[];
}

interface GroupSettlementRaw {
  id: number;
  group_id: number;
  from_member_id: number;
  from_display_name: string;
  to_member_id: number;
  to_display_name: string;
  date: string;
  amount: string;
  currency: string;
  status: SettlementStatus;
  from_account_id: number | null;
  from_amount: string | null;
  to_account_id: number | null;
  to_amount: string | null;
  confirmed_at: string | null;
  notes: string | null;
  can_confirm: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
}

interface GroupMoneySettingsRaw {
  group_id: number;
  default_split_method: SplitMethod;
  auto_finalise_settlements: boolean;
}

// --- Frontend types (camelCase) ---

export interface GroupMemberBalance {
  memberId: number;
  displayName: string;
  // Positive when this member is owed, negative when they owe. A member who is square has no row at
  // all — a line of zeros on every screen says nothing.
  amount: string;
  isSelf: boolean;
}

export interface GroupSettleSuggestion {
  fromMemberId: number;
  fromDisplayName: string;
  toMemberId: number;
  toDisplayName: string;
  amount: string;
}

export interface GroupCurrencyBalance {
  currency: string;
  balances: GroupMemberBalance[];
  // The fewest payments that clear this bucket: the largest debtor pays the largest creditor and so
  // on, so A pays C directly rather than through B. Deterministic for the same balances.
  suggestions: GroupSettleSuggestion[];
  myBalance: string;
  // The viewer's own position converted for reading at a glance; null when no rate is available, and
  // never what anybody settles.
  myConvertedBalance: string | null;
}

export interface GroupBalances {
  groupId: number;
  // One per currency the group actually has an open position in, alphabetical. A bucket that has been
  // fully settled disappears entirely, so an empty list means everyone is square — or that nothing
  // has been shared yet, which the caller tells apart by whether any expense exists.
  buckets: GroupCurrencyBalance[];
  displayCurrency: string | null;
  skippedCurrencies: string[];
}

export interface GroupSettlement {
  id: number;
  groupId: number;
  fromMemberId: number;
  fromDisplayName: string;
  toMemberId: number;
  toDisplayName: string;
  date: string;
  amount: string;
  currency: string;
  status: SettlementStatus;
  /*
   * The two cash legs, each belonging to one side. Each amount is set only when that side's account
   * was denominated differently from the bucket — within one currency the account moved exactly what
   * the bucket cleared, so a second copy of the figure would be a second thing to keep in step.
   */
  fromAccountId: number | null;
  fromAmount: string | null;
  toAccountId: number | null;
  toAmount: string | null;
  confirmedAt: string | null;
  notes: string | null;
  // Resolved server-side from who the caller is. Render from these rather than re-deriving the rule.
  canConfirm: boolean;
  canDelete: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface GroupMoneySettings {
  groupId: number;
  defaultSplitMethod: SplitMethod;
  autoFinaliseSettlements: boolean;
}

// --- Mappers ---

function mapMemberBalance(raw: GroupMemberBalanceRaw): GroupMemberBalance {
  return {
    memberId: raw.member_id,
    displayName: raw.display_name,
    amount: raw.amount,
    isSelf: raw.is_self,
  };
}

function mapSuggestion(raw: GroupSettleSuggestionRaw): GroupSettleSuggestion {
  return {
    fromMemberId: raw.from_member_id,
    fromDisplayName: raw.from_display_name,
    toMemberId: raw.to_member_id,
    toDisplayName: raw.to_display_name,
    amount: raw.amount,
  };
}

function mapCurrencyBalance(raw: GroupCurrencyBalanceRaw): GroupCurrencyBalance {
  return {
    currency: raw.currency,
    balances: raw.balances.map(mapMemberBalance),
    suggestions: raw.suggestions.map(mapSuggestion),
    myBalance: raw.my_balance,
    myConvertedBalance: raw.my_converted_balance,
  };
}

function mapBalances(raw: GroupBalancesRaw): GroupBalances {
  return {
    groupId: raw.group_id,
    buckets: raw.buckets.map(mapCurrencyBalance),
    displayCurrency: raw.display_currency,
    skippedCurrencies: raw.skipped_currencies,
  };
}

function mapSettlement(raw: GroupSettlementRaw): GroupSettlement {
  return {
    id: raw.id,
    groupId: raw.group_id,
    fromMemberId: raw.from_member_id,
    fromDisplayName: raw.from_display_name,
    toMemberId: raw.to_member_id,
    toDisplayName: raw.to_display_name,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    status: raw.status,
    fromAccountId: raw.from_account_id,
    fromAmount: raw.from_amount,
    toAccountId: raw.to_account_id,
    toAmount: raw.to_amount,
    confirmedAt: raw.confirmed_at,
    notes: raw.notes,
    canConfirm: raw.can_confirm,
    canDelete: raw.can_delete,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function mapMoneySettings(raw: GroupMoneySettingsRaw): GroupMoneySettings {
  return {
    groupId: raw.group_id,
    defaultSplitMethod: raw.default_split_method,
    autoFinaliseSettlements: raw.auto_finalise_settlements,
  };
}

// --- API functions ---

/*
 * Every member's position per currency, plus the fewest payments that clear each bucket.
 *
 * `currency` asks for the glance figure beside each bucket only — the buckets themselves are always
 * in their own currency and are never converted, because that is what a settle line has to be.
 *
 * Returns null for a group that does not exist or that the caller is not a member of, so the hub
 * renders notFound() either way and an id cannot be probed.
 */
export async function getGroupBalances(
  groupId: number,
  currency?: string,
): Promise<GroupBalances | null> {
  const query = currency ? `?currency=${encodeURIComponent(currency)}` : '';
  const res = await authenticatedFetch(`/groups/${groupId}/balances${query}`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch group balances');
  return mapBalances(await res.json());
}

// The group's recorded settlements and write-offs, newest first. Null for the same two reasons.
export async function getGroupSettlements(groupId: number): Promise<GroupSettlement[] | null> {
  const res = await authenticatedFetch(`/groups/${groupId}/settlements`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch group settlements');
  const raw: GroupSettlementRaw[] = await res.json();
  return raw.map(mapSettlement);
}

// The money the group holds in common: the split a new expense starts on, and whether a recorded
// settlement is confirmed on the spot. Null for the same two reasons.
export async function getGroupMoneySettings(groupId: number): Promise<GroupMoneySettings | null> {
  const res = await authenticatedFetch(`/groups/${groupId}/money-settings`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch group money settings');
  return mapMoneySettings(await res.json());
}
