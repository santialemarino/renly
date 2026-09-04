/*
 * The audit trail's vocabulary, mirroring the API's `AuditEntityType` and `AuditAction`. It lives here
 * rather than beside the fetcher for the reason NOTIFICATION_EVENTS does: every consumer is a client
 * component and `lib/api/*` is server-only, so importing a runtime value from there breaks the build.
 *
 * The API stores an entity, an action and a payload and never a sentence, so this is where the web
 * declares which combinations exist. Each one resolves to `shared.activity.entries.<entity>.<action>`,
 * and the parity test asserts every combination here has copy in both locales — because a combination
 * the API can write and the web has no key for renders as a broken key path to the reader, which is
 * not a type error and is invisible until somebody performs that exact act in that exact language.
 */

/** Every kind of shared thing the trail records, alphabetical as the API's enum is. */
export const ACTIVITY_ENTITY_TYPES = [
  'group',
  'group_invite',
  'group_member',
  'group_money_settings',
  'ownership_event',
  'pot',
  'settlement',
  'shared_expense',
  'shared_income',
] as const;

export type ActivityEntityType = (typeof ACTIVITY_ENTITY_TYPES)[number];

/*
 * Which actions each entity type can carry — the enumerated list that IS the contract between the two
 * sides. `group` has no `deleted`, and that is not an omission: deleting a group cascades its whole
 * trail away, so an entry saying so would be removed by the same statement that provoked it.
 */
export const ACTIVITY_ACTIONS = {
  group: ['created', 'updated'],
  group_invite: ['created', 'revoked'],
  group_member: ['added', 'joined', 'removed', 'updated'],
  group_money_settings: ['updated'],
  ownership_event: ['created', 'deleted'],
  pot: [
    'created',
    'updated',
    'deleted',
    'holdings_added',
    'holdings_removed',
    'permission_set',
    'permission_cleared',
  ],
  settlement: ['created', 'confirmed', 'unconfirmed', 'leg_set', 'deleted'],
  shared_expense: ['created', 'updated', 'deleted'],
  shared_income: ['created', 'updated', 'deleted'],
} as const satisfies Record<ActivityEntityType, readonly string[]>;

/*
 * The (entity, action) pairs whose copy has more than one form, and the forms each takes.
 *
 * A contribution and a withdrawal are one action on one entity; so are a payment and a write-off, and
 * a member leaving versus being removed. Declared as data for the same reason NOTIFICATION_VARIANTS is:
 * the row resolves `…<entity>.<action>.<variant>`, so a variant the API sends that the web has no key
 * for would be a blank row.
 *
 * `settlement.confirmed` and `settlement.unconfirmed` are absent on purpose even though their payloads
 * carry a variant: only a payment can be confirmed, so there is one sentence and the payload's value is
 * simply unread — the same way a notification payload carries values a given template does not use.
 *
 * Every pair listed here ALSO carries a `base` sentence in the copy, and that is a requirement rather
 * than a convention: entries are append-only and permanent, so one written before a variant existed
 * carries none at all, and without a base to fall back to it renders its own key path forever.
 */
export const ACTIVITY_VARIANTS = {
  'group_member.removed': ['self', 'by_admin'],
  'ownership_event.created': ['opening', 'contribution', 'withdrawal', 'reagreement'],
  'ownership_event.deleted': ['opening', 'contribution', 'withdrawal', 'reagreement'],
  'settlement.created': ['payment', 'write_off'],
  'settlement.deleted': ['payment', 'write_off'],
  'pot.permission_set': ['write', 'view', 'none'],
  'settlement.leg_set': ['attached', 'cleared'],
} as const;

/** How many entries the group hub's activity section shows. The API caps a request at 50. */
export const ACTIVITY_PAGE_SIZE = 12;
