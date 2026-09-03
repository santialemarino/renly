import { ROUTES, sharedGroupPath, sharedPotPath } from '@/config/routes';
import type { AppNotification } from '@/lib/api/notifications';
import {
  NOTIFICATION_DETAIL_KEYS,
  NOTIFICATION_VARIANTS,
  type NotificationEvent,
} from '@/lib/constants/notifications';

/*
 * How one notification becomes a row a person can read: which translation keys it uses, which values
 * those keys interpolate, and where it links.
 *
 * Three files carry the notification layer on the web and they divide cleanly, which is worth stating
 * because the names are close: `lib/constants/notifications.ts` holds the enums (client-safe values),
 * `lib/api/notifications.ts` is the server-only fetcher, and this is the rendering RULE — pure, no
 * fetching, no JSX, so both the sidebar's popover and the /notifications page resolve a row the same
 * way rather than each interpreting a payload for itself.
 *
 * The API stores an event and a payload and never a sentence, which is the whole reason this exists:
 * the prose is assembled here, so the feed reads in whatever language its reader is using now and a
 * copy fix reaches rows written months ago.
 */

/*
 * The events whose link is the POT rather than the group. Restated here rather than imported from the
 * API side because it is the WEB's routing decision — and the two are checked against each other by
 * the one property that matters: both fall back to the group when no pot is named.
 */
const POT_LINKED_EVENTS = new Set<NotificationEvent>([
  'ownership_changed',
  'pot_movement',
  'snapshot_due',
]);

/*
 * The payload key each event reads its date from, when it has one. Only `snapshot_due` does today; it
 * is a map rather than a special case so a second dated event needs one line here instead of a branch
 * in the resolver.
 */
const DATE_KEYS: Partial<Record<NotificationEvent, string>> = {
  snapshot_due: 'valued_as_of',
};

/** Everything a row needs to render itself, resolved from the stored event and payload. */
export interface NotificationRow {
  /** Key under the `notifications.events` namespace, e.g. `pot_movement.contribution.title`. */
  titleKey: string;
  /** The muted second line's key, or null when this event has none. */
  detailKey: string | null;
  /** Values the two keys interpolate. Keys stay snake_case — they are the placeholder names. */
  params: Record<string, string>;
  /** Where the row points, built from `config/routes` rather than from a stored path. */
  href: string;
}

// A payload value as a string, or an empty string when it is absent or null. next-intl renders a
// missing parameter as the literal `{name}`, so a payload that has lost a field (an older row, an
// event whose shape changed) would otherwise show its own placeholder to the user.
function text(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return value === null || value === undefined ? '' : String(value);
}

// The `variant` the payload names, when it is one this event actually has. Validated against
// NOTIFICATION_VARIANTS rather than trusted, so a value the web has no key for degrades to the event's
// base copy instead of resolving to a key that does not exist.
function variantOf(notification: AppNotification): string | null {
  const allowed = NOTIFICATION_VARIANTS[notification.event as keyof typeof NOTIFICATION_VARIANTS];
  if (!allowed) return null;
  const variant = text(notification.payload, 'variant');
  return (allowed as readonly string[]).includes(variant) ? variant : null;
}

/*
 * Resolves one notification into its keys, its interpolation values and its link.
 *
 * `formatAmount` and `formatDate` are passed in rather than imported, because both are locale-bound
 * and the locale comes from a hook the caller already holds (`useFormatters`) — threading a locale in
 * here would be the silent-`en-US`-fallback shape the i18n layer exists to prevent.
 *
 * `potFallback` is the label a NAMELESS pot reads under (a group's default pot has no name). It is a
 * parameter for the same reason: the label is localized and the payload is shared by every recipient
 * whatever language each of them uses, so the fallback belongs to the reader's own render.
 */
export function notificationRow(
  notification: AppNotification,
  {
    formatAmount,
    formatDate,
    potFallback,
  }: {
    formatAmount: (amount: string, currency: string) => string;
    formatDate: (iso: string) => string;
    potFallback: string;
  },
): NotificationRow {
  const { event, payload } = notification;
  const variant = variantOf(notification);
  const base = variant ? `${event}.${variant}` : event;

  const amount = text(payload, 'amount');
  const currency = text(payload, 'currency');
  const dateKey = DATE_KEYS[event];
  const dateValue = dateKey ? text(payload, dateKey) : '';

  const params: Record<string, string> = {
    group: text(payload, 'group'),
    // The pot's own name when it has one, and the localized default label when it does not.
    pot: text(payload, 'pot') || potFallback,
    actor: text(payload, 'actor'),
    member: text(payload, 'member'),
    inviter: text(payload, 'inviter'),
    invitee: text(payload, 'invitee'),
    from_member: text(payload, 'from_member'),
    to_member: text(payload, 'to_member'),
    creditor: text(payload, 'creditor'),
    amount: amount ? formatAmount(amount, currency) : '',
    currency,
    date: dateValue ? formatDate(dateValue) : '',
  };

  return {
    titleKey: `${base}.title`,
    detailKey: detailKeyFor(base, dateValue),
    params,
    href: notificationHref(notification),
  };
}

/*
 * The muted second line, or null when this row has none.
 *
 * Read from NOTIFICATION_DETAIL_KEYS rather than guessed, so a row without a detail resolves to null
 * instead of to a key that does not exist — see that constant for why a lookup would be worse.
 */
function detailKeyFor(base: string, dateValue: string): string | null {
  const suffixes = NOTIFICATION_DETAIL_KEYS[base as keyof typeof NOTIFICATION_DETAIL_KEYS];
  if (!suffixes) return null;
  if (suffixes.length === 1) return `${base}.${suffixes[0]}`;
  // Two suffixes means the payload chooses, which today is only the dated/undated pair.
  return `${base}.${dateValue ? suffixes[0] : suffixes[1]}`;
}

/*
 * Where a notification points. Built from `config/routes` rather than from a path the API stored:
 * routing is the web's own concern, and a stored path would silently outlive a rename.
 *
 * A pot event whose payload names no pot falls back to the group, exactly as the API's own link builder
 * does — a link is not worth a broken row.
 */
export function notificationHref(notification: AppNotification): string {
  const potId = Number(notification.payload.pot_id);
  if (POT_LINKED_EVENTS.has(notification.event) && Number.isFinite(potId) && potId > 0) {
    return sharedPotPath(potId);
  }
  const groupId = Number(notification.payload.group_id);
  return Number.isFinite(groupId) && groupId > 0 ? sharedGroupPath(groupId) : ROUTES.shared;
}
