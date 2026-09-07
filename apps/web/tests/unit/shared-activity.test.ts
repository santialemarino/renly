import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import type { ActivityEntry } from '@/lib/api/group-activity';
import {
  ACTIVITY_ACTIONS,
  ACTIVITY_ENTITY_TYPES,
  ACTIVITY_VARIANTS,
} from '@/lib/constants/shared-activity';
import { activityHref, activityRow } from '@/lib/shared-activity';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * The activity feed's rendering rule and the copy behind it.
 *
 * Structural, because the failure modes are. An entry stores an entity, an action and a payload and
 * nothing else, so a pair with no translation, a variant the copy does not cover, or a placeholder no
 * payload supplies all produce the same thing on screen: a line that reads as a broken key path, or a
 * sentence with a literal `{member}` in the middle. None is a type error, and none is visible until
 * somebody performs that exact act in that exact language.
 *
 * The sibling of `notifications.test.ts`, deliberately: the two layers store the same shape for the
 * same reason, so they fail the same ways.
 */

const LOCALES = { en, es } as const;
const GROUP_ID = 10;

// Every (entity, action, variant?) combination the app can render, which is what the copy has to cover.
function allTextKeys(): string[] {
  return ACTIVITY_ENTITY_TYPES.flatMap((entity) =>
    (ACTIVITY_ACTIONS[entity] as readonly string[]).flatMap((action) => {
      const pair = `${entity}.${action}`;
      const variants = ACTIVITY_VARIANTS[pair as keyof typeof ACTIVITY_VARIANTS];
      // `base` is required alongside the variants, not optional: it is where an entry written before a
      // variant existed resolves, and entries are permanent.
      return variants ? [`${pair}.base`, ...variants.map((v) => `${pair}.${v}`)] : [pair];
    }),
  );
}

function entry(overrides: Partial<ActivityEntry> = {}): ActivityEntry {
  return {
    id: 1,
    entityType: 'group',
    entityId: 10,
    action: 'created',
    potId: null,
    actorName: 'Santi',
    payload: {},
    createdAt: '2026-09-04T12:00:00Z',
    ...overrides,
  };
}

const RENDER = {
  formatAmount: (amount: string, currency: string) => `${amount} ${currency}`.trim(),
  potFallback: 'Shared money',
  unknownActor: 'Someone',
};

// A payload carrying every value any sentence interpolates, so one render exercises them all.
const RENDER_PARAMS = {
  actor: 'Santi',
  group: 'Casa',
  pot: 'Depto',
  member: 'Ana',
  counterparty: 'Nico',
  from_member: 'Santi',
  to_member: 'Ana',
  amount: '90.000 ARS',
};

describe('activity copy covers every entity and action', () => {
  it.each(Object.keys(LOCALES))('%s has a sentence for every combination', (locale) => {
    const messages = LOCALES[locale as keyof typeof LOCALES];
    const t = createTranslator({ locale, messages, namespace: 'shared.activity' });
    for (const key of allTextKeys()) {
      /*
       * Asserted on the key path NOT appearing in the output, not merely on the result being truthy.
       * next-intl answers a missing message by returning its own key path, which is a non-empty string
       * — so `toBeTruthy()` passes on exactly the failure this test exists to catch. A mutation that
       * deleted a real sentence proved it.
       */
      const rendered = t(`entries.${key}` as never, RENDER_PARAMS as never);
      expect(rendered, `${locale}: entries.${key}`).not.toContain(key);
    }
  });

  it.each(Object.keys(LOCALES))('%s has the section chrome', (locale) => {
    const messages = LOCALES[locale as keyof typeof LOCALES];
    const t = createTranslator({ locale, messages, namespace: 'shared.activity' });
    for (const key of ['title', 'description', 'emptyTitle', 'emptyDescription', 'unknownActor']) {
      expect(t(key as never), `${locale}: ${key}`).not.toContain(key);
    }
  });

  it('declares every variant the copy has a block for', () => {
    /*
     * The direction allTextKeys cannot see, and the one that actually shipped broken in the sibling
     * notification layer: adding a variant's COPY without adding its name to the constant leaves the
     * resolver falling back to a base key that does not exist, so the row renders its own key path.
     * Every other test here iterates the constant, so every one of them would pass.
     *
     * Derived from the copy: a variant block is a sub-object under an action whose own values are
     * strings, which is exactly how it differs from an action that is one sentence.
     */
    const messages = LOCALES.en as unknown as {
      shared: { activity: { entries: Record<string, Record<string, unknown>> } };
    };
    for (const [entity, actions] of Object.entries(messages.shared.activity.entries)) {
      for (const [action, value] of Object.entries(actions)) {
        if (typeof value !== 'object' || value === null) continue;
        const declared: readonly string[] =
          ACTIVITY_VARIANTS[`${entity}.${action}` as keyof typeof ACTIVITY_VARIANTS] ?? [];
        for (const variant of Object.keys(value as Record<string, unknown>)) {
          if (variant === 'base') continue;
          expect(
            declared,
            `shared.activity.entries.${entity}.${action}.${variant} has copy but is not a declared variant`,
          ).toContain(variant);
        }
      }
    }
  });

  it('declares a variant list only for pairs that exist', () => {
    // The other direction: a variant block for an (entity, action) the API never writes is dead copy
    // that reads as coverage, and its keys would pass the sentence test above forever.
    for (const pair of Object.keys(ACTIVITY_VARIANTS)) {
      const [entity, action] = pair.split('.');
      expect(ACTIVITY_ENTITY_TYPES as readonly string[]).toContain(entity);
      expect(
        ACTIVITY_ACTIONS[entity as keyof typeof ACTIVITY_ACTIONS] as readonly string[],
      ).toContain(action);
    }
  });

  it('supplies no placeholder the copy never uses', () => {
    /*
     * The reverse of the test below, and the one that catches a PAYLOAD field nothing renders. Reading
     * the finished diff found five of them — an opening's owner count, a holdings move's two counts, a
     * member update's role, a settings change's two values — each stored on every entry, walked by no
     * test, and read by nobody. The parity test below only walks the COPY, so it is structurally blind
     * to them.
     *
     * `currency` is deliberately absent from the params: the amount already carries its code, so a
     * separate placeholder would invite a sentence that says it twice.
     */
    const used = new Set<string>();
    for (const messages of Object.values(LOCALES)) {
      const entries = (messages as { shared: { activity: { entries: Record<string, unknown> } } })
        .shared.activity.entries;
      for (const actions of Object.values(entries)) {
        for (const value of Object.values(actions as Record<string, unknown>)) {
          const strings =
            typeof value === 'string' ? [value] : Object.values(value as Record<string, string>);
          for (const sentence of strings) {
            for (const match of String(sentence).matchAll(/\{(\w+)\}/g)) used.add(match[1]!);
          }
        }
      }
    }
    for (const name of Object.keys(activityRow(entry(), GROUP_ID, RENDER).params)) {
      expect(used, `activityRow supplies {${name}} and no sentence uses it`).toContain(name);
    }
  });

  it('interpolates only placeholders the row actually supplies', () => {
    /*
     * The one that catches a Spanish string naming `{member}` where the English one names `{actor}`:
     * next-intl leaves an unsupplied placeholder in the output verbatim, so the reader sees the brace.
     * Checked against the params `activityRow` builds rather than a hand-written list, so adding a
     * placeholder to the copy without adding it there fails here.
     */
    const supplied = new Set(Object.keys(activityRow(entry(), GROUP_ID, RENDER).params));
    for (const [locale, messages] of Object.entries(LOCALES)) {
      const entries = (messages as { shared: { activity: { entries: Record<string, unknown> } } })
        .shared.activity.entries;
      for (const [entity, actions] of Object.entries(entries)) {
        for (const [action, value] of Object.entries(actions as Record<string, unknown>)) {
          const strings =
            typeof value === 'string' ? [value] : Object.values(value as Record<string, string>);
          for (const sentence of strings) {
            for (const [, name] of String(sentence).matchAll(/\{(\w+)\}/g)) {
              expect(
                supplied,
                `${locale}: shared.activity.entries.${entity}.${action} uses {${name}}`,
              ).toContain(name);
            }
          }
        }
      }
    }
  });
});

describe('resolving one entry', () => {
  it('appends the variant only when the pair has one', () => {
    expect(
      activityRow(
        entry({
          entityType: 'ownership_event',
          action: 'created',
          payload: { variant: 'withdrawal' },
        }),
        GROUP_ID,
        RENDER,
      ).textKey,
    ).toBe('ownership_event.created.withdrawal');
    // A settlement's payload always carries a payment/write-off variant, but `confirmed` has one
    // sentence — so the variant is read past rather than appended to a key that does not exist.
    expect(
      activityRow(
        entry({ entityType: 'settlement', action: 'confirmed', payload: { variant: 'payment' } }),
        GROUP_ID,
        RENDER,
      ).textKey,
    ).toBe('settlement.confirmed');
  });

  it('falls back to a real base sentence, never to a key that does not exist', () => {
    /*
     * Two ways a variant goes missing, and both resolve to `<pair>.base`.
     *
     * An API that grew a fifth ownership event type before the web learned its name is one. The other
     * is the one the live walk actually hit: an entry written BEFORE a variant existed carries none at
     * all, and entries are append-only and permanent — so falling back to the bare pair would have
     * rendered `shared.activity.entries.pot.permission_set` to the reader, forever.
     */
    for (const payload of [{ variant: 'merger' }, {}]) {
      expect(
        activityRow(
          entry({ entityType: 'ownership_event', action: 'created', payload }),
          GROUP_ID,
          RENDER,
        ).textKey,
      ).toBe('ownership_event.created.base');
    }
  });

  it('names the actor, and says "someone" once the account is gone', () => {
    expect(activityRow(entry(), GROUP_ID, RENDER).params.actor).toBe('Santi');
    // actor_user_id is SET NULL rather than cascaded, so the record outlives the account — which means
    // the sentence needs a subject when the name does not.
    expect(activityRow(entry({ actorName: null }), GROUP_ID, RENDER).params.actor).toBe('Someone');
  });

  it('routes a nameless pot through the localized fallback', () => {
    // A group's default pot has no name (A4), and a null interpolated into copy fails by PRINTING.
    const row = activityRow(
      entry({ entityType: 'pot', action: 'updated', payload: { pot: null } }),
      GROUP_ID,
      RENDER,
    );
    expect(row.params.pot).toBe('Shared money');
  });

  it('formats the amount with its currency code', () => {
    // Every currency a group has used sits side by side and unconverted in one trail, so a bare figure
    // leaves the reader to guess which one it is.
    const row = activityRow(
      entry({
        entityType: 'shared_expense',
        action: 'created',
        payload: { amount: '90000', currency: 'ARS' },
      }),
      GROUP_ID,
      RENDER,
    );
    expect(row.params.amount).toBe('90000 ARS');
  });

  it('leaves the amount empty rather than formatting a missing one', () => {
    // Most actions carry no figure at all, and `formatAmount('')` would render a zero.
    expect(activityRow(entry(), GROUP_ID, RENDER).params.amount).toBe('');
  });
});

describe('where an entry points', () => {
  it('links a pot entry to the pot and everything else to the group', () => {
    expect(activityHref(entry({ potId: 7 }), GROUP_ID)).toBe('/shared/pots/7');
    expect(activityHref(entry(), GROUP_ID)).toBe('/shared/10');
  });

  it('links a deleted pot to the group, because there is no pot page left', () => {
    // `pot.deleted` is the one pot action written with a null pot id — deliberately, so it stays
    // readable after app_can_view_pot can no longer answer for the pot it describes.
    expect(
      activityHref(entry({ entityType: 'pot', action: 'deleted', potId: null }), GROUP_ID),
    ).toBe('/shared/10');
  });
});
