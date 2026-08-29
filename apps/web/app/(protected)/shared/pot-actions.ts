'use server';

import {
  toDataResult,
  toResult,
  type SharedDataResult,
  type SharedMutationResult,
} from '@/app/(protected)/shared/mutation-result';
import type {
  PotBuyOutFormValues,
  PotFormValues,
  PotMovementFormValues,
  PotOpeningFormValues,
  PotReagreementFormValues,
  PotTakeOutFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import { mapPot, type Pot, type PotRaw } from '@/lib/api/pots';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

/*
 * Mutations on a pot and its ownership ledger. Every one returns its refusal as data through
 * `toResult` — see `mutation-result.ts` for why — and the pot refusals worth surfacing are the ones a
 * user could not have known: read-only access (403 pot_write_required), a second baseline
 * (409 pot_already_opened), percentages that do not total 100 (400), no value on that date so units
 * cannot be priced (400 pot_valuation_required), a withdrawal larger than the seat holds
 * (400 pot_insufficient_units), and taking a holding out of an already-divided pot
 * (409 pot_already_divided).
 *
 * Percentages and amounts are sent as STRINGS exactly as typed. The API's fields are Decimal, and
 * routing a money figure through a JS number on the way out is how 5.85 becomes 5.849999999999999 and
 * gets refused by a `decimal_places=2` validator for a reason the user cannot act on.
 */

// Returns the created pot rather than only success: the guided flow's next step moves holdings into
// the very pot this call made, so the id has to come back with it.
export async function createPot(
  groupId: number,
  values: PotFormValues,
): Promise<SharedDataResult<Pot>> {
  const res = await authenticatedFetch('/pots', {
    method: 'POST',
    body: {
      group_id: groupId,
      name: values.name?.trim() || null,
      base_currency: values.baseCurrency,
      visibility: values.visibility,
    },
  });
  return toDataResult<PotRaw, Pot>(res, mapPot, 'Failed to create pot');
}

// base_currency is deliberately absent: it is the unit of every figure already in the ledger, and the
// API's update body has no such field at all.
export async function updatePot(
  potId: number,
  values: PotFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}`, {
    method: 'PUT',
    body: { name: values.name?.trim() || null, visibility: values.visibility },
  });
  return toResult(res, 'Failed to update pot');
}

export async function deletePot(potId: number): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}`, { method: 'DELETE' });
  return toResult(res, 'Failed to delete pot');
}

// Two booleans rather than a form: the permissions table sets them from switches, so there is nothing
// for a zod schema to validate. `can_write` implies `can_view` server-side (a table CHECK enforces it
// too), so the pair is sent as chosen and the API resolves the implication.
export async function setPotPermission(
  potId: number,
  memberId: number,
  access: { canView: boolean; canWrite: boolean },
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/permissions/${memberId}`, {
    method: 'PUT',
    body: { can_view: access.canView, can_write: access.canWrite },
  });
  return toResult(res, 'Failed to set pot permission');
}

// Drops the explicit row so the seat follows the pot's visibility default again. Separate from setting
// it to false: "no opinion" and "denied" differ the moment the pot's own default changes.
export async function clearPotPermission(
  potId: number,
  memberId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/permissions/${memberId}`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to clear pot permission');
}

// Moves holdings into the pot or back out of it. One action for both directions because the payload is
// identical and only the endpoint differs — two would be two places for the same body to drift.
export async function movePotHoldings(
  potId: number,
  investmentIds: number[],
  accountIds: number[],
  into: boolean,
): Promise<SharedDataResult<Pot>> {
  const res = await authenticatedFetch(`/pots/${potId}/holdings${into ? '' : '/remove'}`, {
    method: 'POST',
    body: { investment_ids: investmentIds, account_ids: accountIds },
  });
  // The pot comes back rather than a bare success because its `nav` is the answer to the question the
  // guided flow asks next — what the things just moved in are actually worth. Re-reading for it would
  // be a second round trip for a figure this response already carries.
  return toDataResult<PotRaw, Pot>(res, mapPot, 'Failed to move pot holdings');
}

/*
 * Records the opening baseline. A blank percentage means "owns none of it", so those rows are dropped
 * rather than sent as 0 — the API issues one event per owner named, and a 0% owner would be an event
 * granting nobody anything, sitting in the history forever.
 */
export async function recordPotOpening(
  potId: number,
  values: PotOpeningFormValues,
): Promise<SharedMutationResult> {
  const shares = Object.fromEntries(
    values.shares
      .filter((share) => share.percentage !== '' && Number(share.percentage) > 0)
      .map((share) => [String(share.memberId), share.percentage]),
  );
  const res = await authenticatedFetch(`/pots/${potId}/ownership/opening`, {
    method: 'POST',
    body: { date: values.date, value: values.value, shares, notes: values.notes || null },
  });
  return toResult(res, 'Failed to record the opening baseline');
}

/*
 * The movements endpoint's request body, built in ONE place because two callers send it: the manual
 * movement form and the guided take-a-share-out flow. They differ in exactly two things — the type,
 * and whether the units come from the money or from the member's whole balance — so hand-building the
 * body twice would be two places for the wire shape to drift, and the second one would be the one
 * that misses the next field.
 *
 * The form asks "which private account" and "which pot account" because that is what the user knows;
 * the API stores `from` and `to`, and which is which depends on the direction — a contribution runs
 * private → pot and a withdrawal the other way.
 *
 * `amount_currency` is sent only when it differs from the pot's base currency, matching what the API
 * stores: it keeps the column null whenever the movement is single-currency, so a row with a currency
 * set always means a real conversion happened.
 */
function movementBody(
  baseCurrency: string,
  values: PotMovementFormValues | (PotTakeOutFormValues & { type: 'withdrawal' }),
  wholeShare: boolean,
) {
  const isContribution = values.type === 'contribution';
  const privateLeg = values.privateAccountId ? Number(values.privateAccountId) : null;
  const potLeg = values.potAccountId ? Number(values.potAccountId) : null;
  const crossCurrency = values.amountCurrency !== baseCurrency;

  return {
    type: values.type,
    date: values.date,
    member_id: Number(values.memberId),
    amount: values.amount,
    amount_currency: crossCurrency ? values.amountCurrency : null,
    base_amount: crossCurrency ? values.baseAmount : null,
    from_account_id: isContribution ? privateLeg : potLeg,
    to_account_id: isContribution ? potLeg : privateLeg,
    whole_share: wholeShare,
    notes: values.notes || null,
  };
}

// Records a contribution or a withdrawal for an amount the user stated.
export async function recordPotMovement(
  potId: number,
  baseCurrency: string,
  values: PotMovementFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership/movements`, {
    method: 'POST',
    body: movementBody(baseCurrency, values, false),
  });
  return toResult(res, 'Failed to record the movement');
}

export async function recordPotReagreement(
  potId: number,
  values: PotReagreementFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership/reagreements`, {
    method: 'POST',
    body: {
      date: values.date,
      from_member_id: Number(values.fromMemberId),
      to_member_id: Number(values.toMemberId),
      percentage: values.percentage,
      notes: values.notes || null,
    },
  });
  return toResult(res, 'Failed to record the re-agreement');
}

/*
 * Takes a member's whole share out: the same withdrawal body, with `whole_share` set — so the API
 * redeems the balance the member holds rather than dividing the money by the unit price and landing
 * near it. That is the only difference, which is why it shares the builder above.
 */
export async function takePotShareOut(
  potId: number,
  baseCurrency: string,
  values: PotTakeOutFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership/movements`, {
    method: 'POST',
    body: movementBody(baseCurrency, { ...values, type: 'withdrawal' }, true),
  });
  return toResult(res, 'Failed to take the share out');
}

/*
 * Buys a member out: their whole stake moves to another member, and no money is recorded at all.
 *
 * `whole_share` rather than a percentage because the seller has to end on exactly zero — a percentage
 * of the pot leaves them holding a residual that renders as a 0.00% owner and never goes away. The
 * body omits `percentage` entirely, which the API's schema requires when the flag is set.
 *
 * The cash the buyer pays the seller is NOT recorded, because it cannot be: it moves between two
 * different people's private accounts, and no Renly movement spans those. The flow says so in words
 * rather than silently recording half of what happened.
 */
export async function buyPotShareOut(
  potId: number,
  values: PotBuyOutFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership/reagreements`, {
    method: 'POST',
    body: {
      date: values.date,
      from_member_id: Number(values.fromMemberId),
      to_member_id: Number(values.toMemberId),
      whole_share: true,
      notes: values.notes || null,
    },
  });
  return toResult(res, 'Failed to buy the share out');
}

// Deletes a ledger entry. Unit balances are derived, so the series simply recomputes without it —
// there is no stored total to correct, which is the same property that makes back-dating safe.
export async function deletePotOwnershipEvent(
  potId: number,
  eventId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership/${eventId}`, { method: 'DELETE' });
  return toResult(res, 'Failed to delete the ledger entry');
}
