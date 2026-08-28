'use server';

import { toResult, type SharedMutationResult } from '@/app/(protected)/shared/mutation-result';
import type {
  PotFormValues,
  PotMovementFormValues,
  PotOpeningFormValues,
  PotPermissionFormValues,
  PotReagreementFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
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

export async function createPot(
  groupId: number,
  values: PotFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch('/pots', {
    method: 'POST',
    body: {
      group_id: groupId,
      name: values.name?.trim() || null,
      base_currency: values.baseCurrency,
      visibility: values.visibility,
    },
  });
  return toResult(res, 'Failed to create pot');
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

export async function setPotPermission(
  potId: number,
  memberId: number,
  values: PotPermissionFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/permissions/${memberId}`, {
    method: 'PUT',
    body: { can_view: values.canView, can_write: values.canWrite },
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
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/holdings${into ? '' : '/remove'}`, {
    method: 'POST',
    body: { investment_ids: investmentIds, account_ids: accountIds },
  });
  return toResult(res, 'Failed to move pot holdings');
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
 * Records a contribution or a withdrawal, mapping the form's two account fields onto the API's
 * directional legs. The form asks "which private account" and "which pot account" because that is what
 * the user knows; the API stores `from` and `to`, and which is which depends on the direction — a
 * contribution runs private → pot and a withdrawal the other way.
 *
 * `amount_currency` is sent only when it differs from the pot's base currency, matching what the API
 * stores: it keeps the column null whenever the movement is single-currency, so a row with a currency
 * set always means a real conversion happened.
 */
export async function recordPotMovement(
  potId: number,
  baseCurrency: string,
  values: PotMovementFormValues,
): Promise<SharedMutationResult> {
  const isContribution = values.type === 'contribution';
  const privateLeg = values.privateAccountId ? Number(values.privateAccountId) : null;
  const potLeg = values.potAccountId ? Number(values.potAccountId) : null;
  const crossCurrency = values.amountCurrency !== baseCurrency;

  const res = await authenticatedFetch(`/pots/${potId}/ownership/movements`, {
    method: 'POST',
    body: {
      type: values.type,
      date: values.date,
      member_id: Number(values.memberId),
      amount: values.amount,
      amount_currency: crossCurrency ? values.amountCurrency : null,
      base_amount: crossCurrency ? values.baseAmount : null,
      from_account_id: isContribution ? privateLeg : potLeg,
      to_account_id: isContribution ? potLeg : privateLeg,
      notes: values.notes || null,
    },
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

// Deletes a ledger entry. Unit balances are derived, so the series simply recomputes without it —
// there is no stored total to correct, which is the same property that makes back-dating safe.
export async function deletePotOwnershipEvent(
  potId: number,
  eventId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/pots/${potId}/ownership/${eventId}`, { method: 'DELETE' });
  return toResult(res, 'Failed to delete the ledger entry');
}
