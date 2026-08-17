import { CARD_PERCEPTION_MULTIPLIER } from '@/lib/constants/currency';

// Ceiling on the decimals a sub-1 rate renders with, so an absurd pair can't produce a 300-char number.
// Three significant figures is the goal; this only bounds the pathological tail.
const MAX_RATE_DECIMALS = 10;

/*
 * The read-back and sanity-check for a cross-currency card settlement.
 *
 * Nothing here ever PREFILLS the amount. The user types the real blended figure their bank debited, and
 * that figure stays authoritative — the whole model rests on recording what actually left the account,
 * so anchoring them to a computed estimate would defeat it. These two numbers exist only so a 10× typo
 * is visible in either direction: the rate their entry implies, beside the rate today's dólar tarjeta
 * suggests.
 *
 * Deliberately NOT stored anywhere. #170 built an `implied_rate` column for transfers and removed it: no
 * single direction reads correctly both ways, and the division has unbounded precision. The two amounts
 * ARE the record; this is presentation.
 */

// The rate a typed pair implies: how many units of the account's currency per unit of the bucket's.
// Null when either side is missing or non-positive, so a half-filled form shows nothing rather than
// Infinity or NaN.
export function impliedRate(bucketAmount: string, accountAmount: string): number | null {
  const bucket = Number(bucketAmount);
  const account = Number(accountAmount);
  if (!Number.isFinite(bucket) || !Number.isFinite(account) || bucket <= 0 || account <= 0)
    return null;
  return account / bucket;
}

/*
 * What today's "dólar tarjeta" implies for the same pair, or null when it can't be computed.
 *
 * `oficialRate` MUST be the USD_ARS_OFICIAL pair, never the user's dollar-rate preference: the card
 * rate is built on oficial even for someone viewing MEP, so reading the preference here would be a
 * quiet correctness bug rather than a display choice.
 *
 * Only the ARS-from-USD direction is estimated. The perception is an Argentine tax on foreign-currency
 * card consumption, so it has no meaning for, say, a EUR bucket paid from a BRL account — and showing a
 * confidently wrong number is worse than showing none. Every other pair gets the implied rate alone.
 */
export function estimatedCardRate(
  bucketCurrency: string,
  accountCurrency: string,
  oficialRate: number | null,
): number | null {
  if (bucketCurrency !== 'USD' || accountCurrency !== 'ARS') return null;
  if (oficialRate === null || !Number.isFinite(oficialRate) || oficialRate <= 0) return null;
  // The PRODUCT is re-checked, not just the inputs: the multiplier comes from deploy-time env, where a
  // typo like `1e400` or `-1` arrives as Infinity or a negative and would render as "around ∞".
  const estimate = oficialRate * CARD_PERCEPTION_MULTIPLIER;
  return Number.isFinite(estimate) && estimate > 0 ? estimate : null;
}

/*
 * How many decimals a rate needs to stay legible. A rate is only ever read to check an order of
 * magnitude, and a fixed 2 decimals destroys that in one whole direction: an ARS bucket paid from a USD
 * account implies ~0.00077, which renders as "0" — and a genuine 10x typo renders as "0" too, so the
 * guard silently stops guarding. Sub-1 rates therefore get enough decimals for three significant
 * figures, while ordinary rates in the hundreds or thousands keep the usual 2.
 */
export function rateDecimals(rate: number): number {
  if (rate >= 1) return 2;
  return Math.min(MAX_RATE_DECIMALS, Math.ceil(-Math.log10(rate)) + 2);
}

// Pulls one pair's rate out of the latest-rates list as a number, or null when it isn't stored. The API
// returns rates as decimal strings, and a missing pair is normal (a fresh install has no rates yet).
export function rateForPair(rates: { pair: string; rate: string }[], pair: string): number | null {
  const found = rates.find((r) => r.pair === pair);
  if (!found) return null;
  const value = Number(found.rate);
  return Number.isFinite(value) && value > 0 ? value : null;
}

// The date the same pair's rate is FOR. Rendered beside the estimate so it never passes itself off as
// today's figure — the stored rate can be days behind, and the settlement is usually backdated anyway.
export function rateDateForPair(
  rates: { pair: string; date: string }[],
  pair: string,
): string | null {
  return rates.find((r) => r.pair === pair)?.date ?? null;
}
