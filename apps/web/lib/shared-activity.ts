import { sharedGroupPath, sharedPotPath } from '@/config/routes';
import type { ActivityEntry } from '@/lib/api/group-activity';
import { ACTIVITY_VARIANTS } from '@/lib/constants/shared-activity';

/*
 * How one audit entry becomes a line a person can read: which translation key it uses, which values
 * that key interpolates, and where it links.
 *
 * The sibling of `lib/notifications.ts`, and deliberately the same shape, because the two solve the
 * same problem: the API stores an entity, an action and a payload and never a sentence, so the prose is
 * assembled here — in the reader's own language, from rows written months ago.
 *
 * Pure, no fetching and no JSX, for the reason every rule in this app is: the section that renders it
 * is a client component full of Radix primitives, which the web unit suite cannot mount at all, so a
 * rule living inside it is a rule nothing tests.
 */

/** Everything a line needs to render itself, resolved from the stored entity, action and payload. */
export interface ActivityRow {
  /** Key under `shared.activity.entries`, e.g. `ownership_event.created.contribution`. */
  textKey: string;
  /** Values the key interpolates. Keys stay snake_case — they are the placeholder names. */
  params: Record<string, string>;
  /** Where the line points, built from `config/routes` rather than from a stored path. */
  href: string;
}

// A payload value as a string, or an empty string when it is absent or null. next-intl renders a
// missing parameter as the literal `{name}`, so a payload that has lost a field (an older entry, an
// action whose shape changed) would otherwise show its own placeholder to the reader.
function text(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return value === null || value === undefined ? '' : String(value);
}

/** The sentence a varianted pair falls back to. Every such pair carries one — see below for why. */
const BASE_VARIANT = 'base';

/*
 * The translation key one entry resolves to.
 *
 * A pair with no variants is one sentence and the pair IS the key. A pair with variants resolves to
 * `<pair>.<variant>`, or to `<pair>.base` when the payload names one the web has no copy for — and that
 * base sentence is not a nicety, it is what keeps the trail readable forever. Entries are append-only
 * and permanent, so an entry written before a variant existed carries no variant at all; without a base
 * to fall back to it would render its own key path to the reader, which is exactly what the live walk
 * found. A less specific sentence that is still true is the only acceptable degradation here.
 *
 * The variant is also VALIDATED rather than trusted, which is what makes a payload carrying one for a
 * single-sentence pair (a confirmed settlement always being a payment) simply ignored.
 */
function textKeyFor(entry: ActivityEntry): string {
  const pair = `${entry.entityType}.${entry.action}`;
  const allowed = ACTIVITY_VARIANTS[pair as keyof typeof ACTIVITY_VARIANTS] as
    | readonly string[]
    | undefined;
  if (!allowed) return pair;
  const variant = text(entry.payload, 'variant');
  return `${pair}.${allowed.includes(variant) ? variant : BASE_VARIANT}`;
}

/*
 * Resolves one entry into its key, its interpolation values and its link.
 *
 * `formatAmount`, `potFallback` and `unknownActor` are passed in rather than imported, for the reason
 * `notificationRow`'s are: the first is locale-bound and the other two are localized strings, and the
 * locale comes from a hook the caller already holds. Threading a locale in here would be the silent
 * `en-US` fallback the i18n layer exists to prevent.
 *
 * `unknownActor` covers a deleted account. The entry's actor column is SET NULL rather than cascaded,
 * so the record of what somebody did to money other people share outlives their account — which means
 * the sentence has to have a subject when the name is gone.
 *
 * The params are exactly the placeholders the copy interpolates, and the payloads carry exactly those
 * values — no more. A payload field nothing renders is a value nothing reads: it looks like coverage,
 * is never checked by the parity test (which only walks the copy), and drifts silently. Reading the
 * finished diff is what found five of them.
 */
export function activityRow(
  entry: ActivityEntry,
  groupId: number,
  {
    formatAmount,
    potFallback,
    unknownActor,
  }: {
    formatAmount: (amount: string, currency: string) => string;
    potFallback: string;
    unknownActor: string;
  },
): ActivityRow {
  const { payload } = entry;

  return {
    textKey: textKeyFor(entry),
    params: {
      actor: entry.actorName ?? unknownActor,
      group: text(payload, 'group'),
      // The pot's own name when it has one, and the localized default label when it does not — A4
      // leaves a group's default pot unnamed, and a null interpolated into copy fails by PRINTING.
      pot: text(payload, 'pot') || potFallback,
      member: text(payload, 'member'),
      counterparty: text(payload, 'counterparty'),
      from_member: text(payload, 'from_member'),
      to_member: text(payload, 'to_member'),
      // No "is there an amount" guard: formatAmount passes a blank straight through, so the guard
      // could not change an answer — and a mutation sweep proved exactly that by deleting it.
      amount: formatAmount(text(payload, 'amount'), text(payload, 'currency')),
    },
    href: activityHref(entry, groupId),
  };
}

/*
 * Where an entry points. Built from `config/routes` rather than from a path the API stored: routing is
 * the web's own concern, and a stored path would silently outlive a rename.
 *
 * A pot entry links to the pot, everything else to the group hub — which is where the reader already
 * is, so the link is what makes an entry actionable rather than merely informative. `pot.deleted` is
 * the one pot action written with no pot id, so it falls through to the group, correctly: there is no
 * pot page left to open.
 *
 * The group id is a PARAMETER rather than a payload field: the entry carries it as a column the response
 * does not expose, and the only caller is a section that already knows which group it is rendering —
 * which is also why there is no "or the groups list" fallback here, unlike `notificationHref`, whose id
 * comes out of a payload and can genuinely be absent.
 */
export function activityHref(entry: ActivityEntry, groupId: number): string {
  if (entry.potId !== null && entry.potId > 0) return sharedPotPath(entry.potId);
  return sharedGroupPath(groupId);
}
