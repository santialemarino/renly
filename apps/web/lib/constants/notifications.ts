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
 * Every event, in the order the preferences grid lists them: your own recurring money first, then the
 * group's activity, then the pot events, then the money that moves between people. The order is the
 * one a person would scan — not alphabetical, which would interleave "a pot's split changes" with
 * "shared income is added".
 *
 * The two PRIVATE events lead because they are the only ones somebody who belongs to no group can ever
 * receive, so a solo account's grid opens on the rows that apply to it. That order is also declared in
 * the Postgres enum (`01_create_tables.sql`, plus each migration's BEFORE clause), and
 * `apps/api/tests/unit/test_notification_event_surface.py` asserts the two lists — and their order —
 * against each other. Until that test existed this constant and the API's `NotificationEvent` were two
 * independent transcriptions of one list with nothing comparing them.
 */
export const NOTIFICATION_EVENTS = [
  'obligation_due',
  'plan_charged',
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
 * read from the payer's seat rather than the payee's. A reconciliation of a shared account rides
 * `pot_movement` too, because what it does to a reader is exactly what those two do — the pot's money
 * moved — and an event value is a migration where a variant is a line of copy.
 *
 * Declared as data because the feed row resolves its translation key as
 * `notifications.events.<event>.<variant>`, and a variant the API sends that the web has no key for
 * would otherwise be a blank row. The parity test asserts every combination here resolves in both
 * locales.
 */
export const NOTIFICATION_VARIANTS = {
  plan_charged: ['subscription', 'installment'],
  ownership_changed: ['opening', 'reagreement', 'deleted', 'confirmed', 'unconfirmed'],
  pot_movement: [
    'contribution',
    'withdrawal',
    'reconciliation_surplus',
    'reconciliation_shortfall',
    'reconciliation_removed',
  ],
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
  obligation_due: ['detail'],
  'ownership_changed.reagreement': ['detail'],
  'settle_marked_paid.payee': ['detail'],
  snapshot_due: ['detailValued', 'detailNever'],
} as const;

/*
 * How often Renly emails somebody about the events they have email turned on for. Mirrors the API's
 * `EmailCadence`; the page renders it as one switch, because two values is what a switch is for.
 *
 * A CADENCE rather than a fourth channel: the two would be mutually exclusive with nothing saying so.
 * It governs email alone — the feed is already a summary you read when you look, and a batched
 * lock-screen interrupt is a contradiction.
 */
export const NOTIFICATION_EMAIL_CADENCES = ['immediate', 'daily'] as const;

export type NotificationEmailCadence = (typeof NOTIFICATION_EMAIL_CADENCES)[number];

/*
 * How many rows the bell's popover shows. Small on purpose: it is the glance, and everything past it
 * is one click away on the page.
 */
export const NOTIFICATION_POPOVER_SIZE = 8;
