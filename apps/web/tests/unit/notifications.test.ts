import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import type { AppNotification } from '@/lib/api/notifications';
import {
  NOTIFICATION_CHANNELS,
  NOTIFICATION_DETAIL_KEYS,
  NOTIFICATION_EVENTS,
  NOTIFICATION_VARIANTS,
  type NotificationEvent,
} from '@/lib/constants/notifications';
import { notificationHref, notificationRow } from '@/lib/notifications';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * The rendering rule and the copy behind it.
 *
 * Most of this is structural, because the failure modes are. A notification stores an event and a
 * payload and nothing else, so an event with no translation, a variant the copy does not cover, or a
 * placeholder no payload supplies all produce the same thing on screen: a row that reads as a broken
 * key, or worse, a sentence with a literal `{member}` in the middle of it. None of them is a type
 * error, and none is visible until somebody triggers that exact event in that exact language.
 */

const LOCALES = { en, es } as const;

// Every (event, variant) pair the app can render, which is what the copy has to cover.
function allBaseKeys(): string[] {
  return NOTIFICATION_EVENTS.flatMap((event) => {
    const variants = NOTIFICATION_VARIANTS[event as keyof typeof NOTIFICATION_VARIANTS];
    return variants ? variants.map((variant) => `${event}.${variant}`) : [event];
  });
}

function notification(
  event: NotificationEvent,
  payload: Record<string, unknown> = {},
): AppNotification {
  return { id: 1, event, payload, readAt: null, createdAt: '2026-09-02T12:00:00Z' };
}

const RENDER = {
  formatAmount: (amount: string, currency: string) => `${amount} ${currency}`.trim(),
  formatDate: (iso: string) => `on ${iso}`,
  potFallback: 'Shared money',
};

describe('notification copy covers every event', () => {
  it.each(Object.keys(LOCALES))('%s has a title for every event and variant', (locale) => {
    const messages = LOCALES[locale as keyof typeof LOCALES];
    const t = createTranslator({ locale, messages, namespace: 'notifications' });
    for (const base of allBaseKeys()) {
      // A missing key throws here, which is exactly the signal wanted: the alternative is a row that
      // renders its own key path to the user.
      expect(t(`events.${base}.title` as never, RENDER_PARAMS as never)).toBeTruthy();
    }
  });

  it.each(Object.keys(LOCALES))('%s has a label for every event, for the grid', (locale) => {
    const messages = LOCALES[locale as keyof typeof LOCALES];
    const t = createTranslator({ locale, messages, namespace: 'notifications' });
    for (const event of NOTIFICATION_EVENTS) {
      expect(t(`events.${event}.label` as never)).toBeTruthy();
    }
  });

  it.each(Object.keys(LOCALES))('%s has every declared detail line', (locale) => {
    const messages = LOCALES[locale as keyof typeof LOCALES];
    const t = createTranslator({ locale, messages, namespace: 'notifications' });
    for (const [base, suffixes] of Object.entries(NOTIFICATION_DETAIL_KEYS)) {
      for (const suffix of suffixes) {
        expect(t(`events.${base}.${suffix}` as never, RENDER_PARAMS as never)).toBeTruthy();
      }
    }
  });

  it.each(Object.keys(LOCALES))('%s names every channel column', (locale) => {
    const messages = LOCALES[locale as keyof typeof LOCALES];
    const t = createTranslator({ locale, messages, namespace: 'notifications' });
    for (const channel of NOTIFICATION_CHANNELS) {
      expect(t(`channels.${channel}` as never)).toBeTruthy();
    }
  });

  it('interpolates only placeholders the row actually supplies', () => {
    /*
     * The one that catches a Spanish string naming `{member}` where the English one names `{actor}`:
     * next-intl leaves an unsupplied placeholder in the output verbatim, so the reader sees the brace.
     * Checked against the params `notificationRow` builds rather than against a hand-written list, so
     * adding a placeholder to the copy without adding it there fails here.
     */
    const supplied = new Set(
      Object.keys(notificationRow(notification('member_joined'), RENDER).params),
    );
    for (const [locale, messages] of Object.entries(LOCALES)) {
      const events = (messages as { notifications: { events: Record<string, unknown> } })
        .notifications.events;
      for (const [event, block] of Object.entries(events)) {
        for (const [key, value] of Object.entries(block as Record<string, unknown>)) {
          const strings =
            typeof value === 'string' ? [value] : Object.values(value as Record<string, string>);
          for (const text of strings) {
            for (const [, name] of String(text).matchAll(/\{(\w+)\}/g)) {
              expect(
                supplied,
                `${locale}: notifications.events.${event}.${key} uses {${name}}`,
              ).toContain(name);
            }
          }
        }
      }
    }
  });
});

// A payload carrying every value any template interpolates, so a render test exercises them all.
const RENDER_PARAMS = {
  group: 'Casa',
  pot: 'Depto',
  actor: 'Santi',
  member: 'Ana',
  inviter: 'Santi',
  invitee: 'Nico',
  from_member: 'Santi',
  to_member: 'Ana',
  creditor: 'Ana',
  amount: '90.000',
  currency: 'ARS',
  date: '12 Jul',
};

describe('a row resolves from its event and payload', () => {
  it('uses the variant the payload names', () => {
    const row = notificationRow(
      notification('pot_movement', { variant: 'withdrawal', pot: 'Depto' }),
      RENDER,
    );
    expect(row.titleKey).toBe('pot_movement.withdrawal.title');
  });

  it('falls back to the base copy for a variant it does not know', () => {
    // A payload written by a newer API than this build. Rendering the base sentence is wrong-ish;
    // resolving a key that does not exist is a broken row, which is worse.
    const row = notificationRow(notification('pot_movement', { variant: 'gifted' }), RENDER);
    expect(row.titleKey).toBe('pot_movement.title');
  });

  it('labels a nameless pot with the localized default', () => {
    // A group's default pot has no name at all, and the label is localized — which is why the payload
    // carries null rather than a label baked in at write time.
    const row = notificationRow(notification('snapshot_due', { pot: null }), RENDER);
    expect(row.params.pot).toBe('Shared money');
  });

  it('keeps a pot that does have a name', () => {
    const row = notificationRow(notification('snapshot_due', { pot: 'Depto' }), RENDER);
    expect(row.params.pot).toBe('Depto');
  });

  it('renders a missing payload field as empty rather than as its own placeholder', () => {
    // next-intl prints an unsupplied parameter verbatim, so an older row that predates a field would
    // otherwise show "{actor}" to the user.
    const row = notificationRow(notification('member_joined', {}), RENDER);
    expect(row.params.member).toBe('');
  });

  it("formats the amount through the caller's formatter and never raw", () => {
    const row = notificationRow(
      notification('shared_expense_added', { amount: '90000.00', currency: 'ARS' }),
      RENDER,
    );
    expect(row.params.amount).toBe('90000.00 ARS');
  });

  it('leaves the amount empty when there is none, rather than formatting nothing', () => {
    const row = notificationRow(notification('member_joined', {}), RENDER);
    expect(row.params.amount).toBe('');
  });

  it('chooses the dated detail when a valuation date is known', () => {
    const row = notificationRow(
      notification('snapshot_due', { valued_as_of: '2026-07-12' }),
      RENDER,
    );
    expect(row.detailKey).toBe('snapshot_due.detailValued');
    expect(row.params.date).toBe('on 2026-07-12');
  });

  it('chooses the never-valued detail when it is not', () => {
    // Two different sentences, and the null is what separates them.
    const row = notificationRow(notification('snapshot_due', { valued_as_of: null }), RENDER);
    expect(row.detailKey).toBe('snapshot_due.detailNever');
  });

  it('gives a row with no second line a null detail key', () => {
    const row = notificationRow(notification('member_joined', {}), RENDER);
    expect(row.detailKey).toBeNull();
  });
});

describe('a row links where it is about', () => {
  it('points a pot event at the pot', () => {
    expect(notificationHref(notification('pot_movement', { group_id: 3, pot_id: 5 }))).toBe(
      '/shared/pots/5',
    );
  });

  it('points a group event at the group, even when a pot id happens to be present', () => {
    expect(notificationHref(notification('shared_expense_added', { group_id: 3, pot_id: 5 }))).toBe(
      '/shared/3',
    );
  });

  it('falls back to the group when a pot event names no pot', () => {
    expect(notificationHref(notification('snapshot_due', { group_id: 3 }))).toBe('/shared/3');
  });

  it('falls back to the module when it can name neither', () => {
    // A link is not worth a broken row: an id that is missing, null or not a number lands somewhere
    // real rather than on "/shared/undefined".
    expect(notificationHref(notification('member_joined', {}))).toBe('/shared');
    expect(notificationHref(notification('member_joined', { group_id: 'x' }))).toBe('/shared');
    expect(notificationHref(notification('member_joined', { group_id: 0 }))).toBe('/shared');
  });
});
