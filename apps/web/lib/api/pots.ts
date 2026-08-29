/*
 * Server-only types + mappers for pots — the container co-ownership attaches to. Reads go through
 * the four functions here; mutations are server actions in `app/(protected)/shared/pot-actions.ts`.
 *
 * Two shapes of the API's honesty survive into these types unchanged, and the UI must respect both:
 *
 *   * `nav` and `unitPrice` are `null` when unknown, never 0. A pot with no holdings, or one holding
 *     a currency with no stored rate, has no value to state — and "we do not know" must never render
 *     as "it is worth nothing", because only one of those is safe to price units against.
 *   * A pot the caller may not see answers 404 exactly as one that does not exist, so `getPot`
 *     returns null for both and the page renders notFound() either way. An id cannot be probed.
 *
 * Money and unit figures stay STRINGS end to end, as everywhere else in the app: they are
 * NUMERIC(18,2) / NUMERIC(18,6) server-side, and parsing them into a JS number would round exactly
 * the digits the ledger exists to keep.
 */

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type {
  OwnershipEventType,
  PotCadence,
  PotSeriesInterval,
  PotVisibility,
} from '@/lib/constants/pots';

// --- Raw types (API JSON shape, snake_case) ---

interface PotMemberShareRaw {
  member_id: number;
  display_name: string;
  units: string;
  percentage: string;
  value: string | null;
  is_self: boolean;
}

interface PotPermissionRaw {
  member_id: number;
  display_name: string;
  can_view: boolean;
  can_write: boolean;
}

export interface PotRaw {
  id: number;
  group_id: number;
  name: string | null;
  base_currency: string;
  snapshot_cadence: PotCadence;
  visibility: PotVisibility;
  is_default: boolean;
  nav: string | null;
  valued_as_of: string | null;
  is_stale: boolean;
  unit_price: string | null;
  total_units: string;
  my_percentage: string;
  can_write: boolean;
  shares: PotMemberShareRaw[];
  permissions: PotPermissionRaw[];
  created_at: string;
  updated_at: string;
}

interface PotHoldingRaw {
  id: number;
  name: string;
  currency: string;
  value: string | null;
  base_value: string | null;
  is_active: boolean;
  valued_on: string | null;
}

interface PotHoldingsRaw {
  investments: PotHoldingRaw[];
  accounts: PotHoldingRaw[];
}

interface PotValueSeriesPointRaw {
  date: string;
  nav: string | null;
  my_value: string | null;
}

interface PotValueSeriesRaw {
  interval: PotSeriesInterval;
  points: PotValueSeriesPointRaw[];
}

interface PotOwnershipEventRaw {
  id: number;
  pot_id: number;
  type: OwnershipEventType;
  date: string;
  member_id: number;
  member_name: string;
  counterparty_member_id: number | null;
  counterparty_name: string | null;
  amount: string | null;
  amount_currency: string | null;
  base_amount: string | null;
  units: string;
  unit_price: string;
  from_account_id: number | null;
  to_account_id: number | null;
  notes: string | null;
  created_at: string;
}

// --- Frontend types (camelCase) ---

export interface PotMemberShare {
  memberId: number;
  displayName: string;
  units: string;
  percentage: string;
  // Share value in the pot's base currency; null when the NAV is unknown.
  value: string | null;
  isSelf: boolean;
}

export interface PotPermission {
  memberId: number;
  displayName: string;
  canView: boolean;
  canWrite: boolean;
}

export interface Pot {
  id: number;
  groupId: number;
  // Null for a group's default pot: the container is deliberately not a thing to name until there
  // is a second one to tell apart.
  name: string | null;
  baseCurrency: string;
  // How often the pot is expected to be re-valued. An expectation, not a schedule — it decides what
  // counts as an overdue valuation and how far apart the value series' points sit, nothing else.
  snapshotCadence: PotCadence;
  visibility: PotVisibility;
  isDefault: boolean;
  nav: string | null;
  /*
   * The date the value is current to, and whether the cadence considers it overdue. A different
   * question from `nav`, and the three can honestly disagree: a pot whose holdings are all
   * snapshotted but one of which cannot be converted has a real `valuedAsOf` and a null `nav`.
   * `valuedAsOf` is null when nothing here has ever been valued, which is a state of its own — the
   * page says "never valued" rather than showing a date.
   */
  valuedAsOf: string | null;
  isStale: boolean;
  unitPrice: string | null;
  totalUnits: string;
  myPercentage: string;
  canWrite: boolean;
  // Largest holder first, and only members actually holding units — someone bought out entirely is
  // not a 0.00% row on every screen.
  shares: PotMemberShare[];
  permissions: PotPermission[];
  createdAt: string;
  updatedAt: string;
}

export interface PotHolding {
  id: number;
  name: string;
  currency: string;
  value: string | null;
  baseValue: string | null;
  isActive: boolean;
  // The date this figure was recorded on. Null for an ACCOUNT, whose balance is derived at the date
  // it is asked for rather than recorded on one — so there is no valuation date to state.
  valuedOn: string | null;
}

export interface PotHoldings {
  investments: PotHolding[];
  accounts: PotHolding[];
}

export interface PotValueSeriesPoint {
  date: string;
  // Both null in the same case and for the same reason the NAV is. `myValue` is additionally null
  // while no units are outstanding: before the baseline nobody owns any share of anything.
  nav: string | null;
  myValue: string | null;
}

export interface PotValueSeries {
  // The grid the points sit on, which an `ad_hoc` pot's cadence does not name — it is plotted monthly.
  interval: PotSeriesInterval;
  points: PotValueSeriesPoint[];
}

export interface PotOwnershipEvent {
  id: number;
  potId: number;
  type: OwnershipEventType;
  date: string;
  memberId: number;
  memberName: string;
  counterpartyMemberId: number | null;
  counterpartyName: string | null;
  // Money moved in the PRIVATE account's currency; baseAmount is the same movement in the pot's.
  amount: string | null;
  amountCurrency: string | null;
  baseAmount: string | null;
  units: string;
  unitPrice: string;
  fromAccountId: number | null;
  toAccountId: number | null;
  notes: string | null;
  createdAt: string;
}

// --- Mappers ---

function mapShare(raw: PotMemberShareRaw): PotMemberShare {
  return {
    memberId: raw.member_id,
    displayName: raw.display_name,
    units: raw.units,
    percentage: raw.percentage,
    value: raw.value,
    isSelf: raw.is_self,
  };
}

function mapPermission(raw: PotPermissionRaw): PotPermission {
  return {
    memberId: raw.member_id,
    displayName: raw.display_name,
    canView: raw.can_view,
    canWrite: raw.can_write,
  };
}

export function mapPot(raw: PotRaw): Pot {
  return {
    id: raw.id,
    groupId: raw.group_id,
    name: raw.name,
    baseCurrency: raw.base_currency,
    snapshotCadence: raw.snapshot_cadence,
    visibility: raw.visibility,
    isDefault: raw.is_default,
    nav: raw.nav,
    valuedAsOf: raw.valued_as_of,
    isStale: raw.is_stale,
    unitPrice: raw.unit_price,
    totalUnits: raw.total_units,
    myPercentage: raw.my_percentage,
    canWrite: raw.can_write,
    shares: raw.shares.map(mapShare),
    permissions: raw.permissions.map(mapPermission),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function mapHolding(raw: PotHoldingRaw): PotHolding {
  return {
    id: raw.id,
    name: raw.name,
    currency: raw.currency,
    value: raw.value,
    baseValue: raw.base_value,
    isActive: raw.is_active,
    valuedOn: raw.valued_on,
  };
}

function mapValueSeries(raw: PotValueSeriesRaw): PotValueSeries {
  return {
    interval: raw.interval,
    points: raw.points.map((point) => ({
      date: point.date,
      nav: point.nav,
      myValue: point.my_value,
    })),
  };
}

function mapOwnershipEvent(raw: PotOwnershipEventRaw): PotOwnershipEvent {
  return {
    id: raw.id,
    potId: raw.pot_id,
    type: raw.type,
    date: raw.date,
    memberId: raw.member_id,
    memberName: raw.member_name,
    counterpartyMemberId: raw.counterparty_member_id,
    counterpartyName: raw.counterparty_name,
    amount: raw.amount,
    amountCurrency: raw.amount_currency,
    baseAmount: raw.base_amount,
    units: raw.units,
    unitPrice: raw.unit_price,
    fromAccountId: raw.from_account_id,
    toAccountId: raw.to_account_id,
    notes: raw.notes,
    createdAt: raw.created_at,
  };
}

// --- API functions ---

// Every pot the caller may see, optionally narrowed to one group. A pot they own 0% of is included:
// membership is not ownership, and the monitoring surface is not gated on holding a share.
export async function getPots(groupId?: number): Promise<Pot[]> {
  const endpoint = groupId === undefined ? '/pots' : `/pots?group_id=${groupId}`;
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch pots');
  const raw: PotRaw[] = await res.json();
  return raw.map(mapPot);
}

/*
 * One pot with its ownership breakdown. Returns null for a pot that does not exist OR that the caller
 * may not see — the API answers 404 for both, so the page renders notFound() either way and an id
 * cannot be used to discover which pots exist.
 *
 * `asOfDate` values it at a past date, which is what a back-dated guided flow needs: the share it is
 * about is worth what it was worth THEN, and pricing the confirmation step at today's figure would
 * state a number the event will not be recorded at.
 */
export async function getPot(potId: number, asOfDate?: string): Promise<Pot | null> {
  const query = asOfDate === undefined ? '' : `?as_of_date=${asOfDate}`;
  const res = await authenticatedFetch(`/pots/${potId}${query}`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch pot');
  return mapPot(await res.json());
}

// Everything the pot holds, archived holdings included and flagged. Null for the same two reasons
// getPot is, so a page can fetch both and take one notFound() decision.
export async function getPotHoldings(potId: number): Promise<PotHoldings | null> {
  const res = await authenticatedFetch(`/pots/${potId}/holdings`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch pot holdings');
  const raw: PotHoldingsRaw = await res.json();
  return { investments: raw.investments.map(mapHolding), accounts: raw.accounts.map(mapHolding) };
}

/*
 * The pot's value at each point of its cadence's grid, plus the caller's own share value at each.
 * Oldest first, the last point being today, and never starting before the pot's ownership anchor.
 *
 * Null for the same two reasons getPot is, so a page can fetch both and take one notFound() decision.
 * A point's figures are null wherever the value cannot be stated in full on that date — which on a
 * real pot is most of the early points, and drawing a zero there would read as growth from nothing.
 */
export async function getPotSeries(
  potId: number,
  periods?: number,
): Promise<PotValueSeries | null> {
  const query = periods === undefined ? '' : `?periods=${periods}`;
  const res = await authenticatedFetch(`/pots/${potId}/series${query}`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch pot value series');
  return mapValueSeries(await res.json());
}

// The pot's ownership ledger in replay order — oldest first, which is the order the unit balances are
// derived in and therefore the only order the history reads correctly in.
export async function getPotOwnershipEvents(potId: number): Promise<PotOwnershipEvent[] | null> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch pot ownership events');
  const raw: PotOwnershipEventRaw[] = await res.json();
  return raw.map(mapOwnershipEvent);
}
