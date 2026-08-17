import { CARD_PERCEPTION_MULTIPLIER } from '@/lib/constants/currency';

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
  return oficialRate * CARD_PERCEPTION_MULTIPLIER;
}

// Pulls one pair's rate out of the latest-rates list as a number, or null when it isn't stored. The API
// returns rates as decimal strings, and a missing pair is normal (a fresh install has no rates yet).
export function rateForPair(rates: { pair: string; rate: string }[], pair: string): number | null {
  const found = rates.find((r) => r.pair === pair);
  if (!found) return null;
  const value = Number(found.rate);
  return Number.isFinite(value) && value > 0 ? value : null;
}
