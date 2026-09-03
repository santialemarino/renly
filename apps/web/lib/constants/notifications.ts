/*
 * The notification enums, mirroring the API's `notification_event` and `notification_channel`. They
 * live here rather than beside the notifications fetcher for the same reason POT_CADENCES does: every
 * consumer is a client component and `lib/api/*` is server-only, so importing a runtime value from
 * there breaks the build.
 *
 * Each array is exhaustive and in display order, so adding an event to the API without adding its
 * translation is a type error at the grid rather than a missing label at runtime.
 */

/*
 * Every event, in the order the preferences grid lists them: the group's own activity first, then the
 * pot events, then the money that moves between people. The order is the one a person would scan —
 * not alphabetical, which would interleave "a pot's split changes" with "shared income is added".
 */
export const NOTIFICATION_EVENTS = [
  'group_invited',
  'member_joined',
  'ownership_changed',
  'pot_movement',
  'snapshot_due',
  'settle_marked_paid',
  'settle_confirmed',
  'balance_written_off',
  'shared_expense_added',
  'shared_income_added',
] as const;

export type NotificationEvent = (typeof NOTIFICATION_EVENTS)[number];

/*
 * The three channels, in the order the grid's columns run: the feed first because it is always on by
 * default, then the two that leave the app.
 */
export const NOTIFICATION_CHANNELS = ['in_app', 'email', 'push'] as const;

export type NotificationChannel = (typeof NOTIFICATION_CHANNELS)[number];

/*
 * The events whose copy has more than one form, and the forms each one takes. A contribution and a
 * withdrawal are the same event; so are a first division and a re-agreement, and a recorded payment
 * read from the payer's seat rather than the payee's.
 *
 * Declared as data because the feed row resolves its translation key as
 * `notifications.events.<event>.<variant>`, and a variant the API sends that the web has no key for
 * would otherwise be a blank row. The parity test asserts every combination here resolves in both
 * locales.
 */
export const NOTIFICATION_VARIANTS = {
  ownership_changed: ['opening', 'reagreement'],
  pot_movement: ['contribution', 'withdrawal'],
  settle_marked_paid: ['payee', 'payer'],
} as const satisfies Partial<Record<NotificationEvent, readonly string[]>>;

/*
 * Which rows carry a muted SECOND line, and what its key is called.
 *
 * Declared rather than probed at render time. next-intl answers a missing key by throwing in
 * development and by rendering the key path in production, so asking "does this row have a detail?"
 * with a lookup would mean either a crash or the string `notifications.events.x.detail` on screen.
 * Declaring it makes a missing translation a failure of the parity test instead — which is where a
 * missing translation should fail.
 *
 * `snapshot_due` is the one event whose detail depends on its payload rather than on its variant:
 * "Last valued 12 Jul" and "It has never been valued" are different sentences, and the null date is
 * what chooses between them.
 */
export const NOTIFICATION_DETAIL_KEYS = {
  'ownership_changed.reagreement': ['detail'],
  'settle_marked_paid.payee': ['detail'],
  snapshot_due: ['detailValued', 'detailNever'],
} as const;

/*
 * How many rows the bell's popover shows. Small on purpose: it is the glance, and everything past it
 * is one click away on the page.
 */
export const NOTIFICATION_POPOVER_SIZE = 8;

/** How many rows the /notifications page shows per page. The API caps a request at 50. */
export const NOTIFICATION_PAGE_SIZE = 20;
