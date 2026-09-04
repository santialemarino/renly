import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import { FEATURE_ICONS } from '@/app/(public)/_components/landing-features';
import type { ProseSectionData } from '@/app/(public)/_components/prose-section';
import { SIDEBAR_NAV_KEYS } from '@/config/nav';
import { HELP_ANCHORS } from '@/config/routes';
import { ENTRY_TYPES } from '@/lib/constants/entries';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Flattens a nested message object into dotted leaf key paths (e.g. "form.language.label"). Arrays
 * recurse with their index as a path segment ("help.sections.1.paragraphs.2"), so a section or a
 * paragraph present in one locale and not the other shows up as a missing key like any other —
 * stopping at arrays would report each one as a single opaque leaf.
 */
function flattenKeys(value: unknown, prefix = ''): string[] {
  if (Array.isArray(value)) {
    // The array's own path is emitted too, so an empty array still registers as a key.
    return [prefix, ...value.flatMap((item, index) => flattenKeys(item, `${prefix}.${index}`))];
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, child]) =>
      flattenKeys(child, prefix ? `${prefix}.${key}` : key),
    );
  }
  return [prefix];
}

/*
 * Flattens to dotted path -> string value, for checks that need the MESSAGE rather than just its key.
 * Non-string leaves (numbers, booleans, nulls) are skipped: nothing here asks anything of them.
 */
function flattenLeaves(value: unknown, prefix = ''): Record<string, string> {
  if (typeof value === 'string') return prefix ? { [prefix]: value } : {};
  if (Array.isArray(value)) {
    return Object.assign(
      {},
      ...value.map((item, index) => flattenLeaves(item, `${prefix}.${index}`)),
    );
  }
  if (value && typeof value === 'object') {
    return Object.assign(
      {},
      ...Object.entries(value).map(([key, child]) =>
        flattenLeaves(child, prefix ? `${prefix}.${key}` : key),
      ),
    );
  }
  return {};
}

describe('translation keyset parity', () => {
  const enKeys = new Set(flattenKeys(en));
  const esKeys = new Set(flattenKeys(es));

  it('has no EN keys missing from ES', () => {
    const missing = [...enKeys].filter((k) => !esKeys.has(k));
    expect(missing).toEqual([]);
  });

  it('has no orphan ES keys absent from EN', () => {
    const orphan = [...esKeys].filter((k) => !enKeys.has(k));
    expect(orphan).toEqual([]);
  });

  it('shares the same top-level namespaces', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(es).sort());
  });
});

/*
 * Every interpolated message in either locale must actually RENDER. next-intl parses ICU lazily, so a
 * malformed placeholder — an unbalanced brace, a plural with no `other` branch, a misspelled keyword —
 * fails only when that one message is used, and an error-code message can go a long time without being.
 * That is the break the keyset checks above structurally cannot see: both locales have the key, and one
 * of them is unusable.
 *
 * Deliberately scoped by "contains a brace" rather than by an ICU-shaped regex. A regex looking for
 * `plural,` stops matching the moment someone typos it — so the very edit most likely to break a
 * message would also remove it from the set being checked, which reads as coverage and is the opposite.
 */
describe('interpolated messages render', () => {
  const interpolated = (locale: 'en' | 'es', messages: object) =>
    Object.entries(flattenLeaves(messages))
      .filter(([, value]) => value.includes('{'))
      .map(([key, value]) => ({ locale, key, value }));

  const cases = [...interpolated('en', en), ...interpolated('es', es)];

  it('finds messages to check', () => {
    // A guard on the guard: were the filter ever to match nothing, every assertion below would pass
    // vacuously.
    expect(cases.length).toBeGreaterThan(100);
  });

  it('renders every one of them, for one and for many', () => {
    /*
     * EVERY placeholder gets a value, not just a plural's: next-intl returns the bare key when any
     * argument is missing, which would report a perfectly good message as broken. `{name}` and
     * `{count,` both match; the prose inside a plural branch does not, because a word there is followed
     * by more prose rather than by a comma or a brace.
     */
    const broken = cases.flatMap(({ locale, key, value }) => {
      const names = [...value.matchAll(/\{\s*(\w+)\s*[,}]/g)].map((match) => match[1]);
      // Rich-text tags (<bold>…</bold>) are arguments too — next-intl needs a renderer for each, and
      // returns the bare key without one. An identity renderer keeps the assertion about parsing.
      const tags = [...value.matchAll(/<(\w+)>/g)].map((match) => match[1]);
      const t = createTranslator({ locale, messages: locale === 'en' ? en : es });
      return [1, 3].flatMap((count) => {
        const args = {
          ...Object.fromEntries(names.map((name) => [name, count])),
          ...Object.fromEntries(tags.map((tag) => [tag, (chunks: unknown) => chunks])),
        };
        const rendered = String(t(key as never, args as never));
        // A message next-intl cannot parse comes back as the key itself rather than throwing, and a
        // leftover brace means a placeholder was never substituted.
        const failed = rendered === key || rendered.includes('{');
        return failed ? [`${locale}:${key} (n=${count}) -> ${rendered}`] : [];
      });
    });
    expect(broken).toEqual([]);
  });
});

describe('help page anchors', () => {
  const enSections = en.help.sections as ProseSectionData[];
  const esSections = es.help.sections as ProseSectionData[];

  it('gives every section a non-empty id', () => {
    expect(enSections.filter((section) => !section.id).map((section) => section.heading)).toEqual(
      [],
    );
  });

  it('gives every section a unique id', () => {
    const ids = enSections.map((section) => section.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('anchors the same sections in the same order in both locales', () => {
    expect(esSections.map((section) => section.id)).toEqual(
      enSections.map((section) => section.id),
    );
  });

  /*
   * A help section's id is a public URL fragment: rename one and every deep link to it breaks
   * silently (the browser simply does not scroll). HELP_ANCHORS is the single source those links are
   * built from, so asserting over its values covers every call site, including ones added later.
   */
  it('still defines every anchor the app links to', () => {
    const ids = new Set(enSections.map((section) => section.id));
    expect(Object.values(HELP_ANCHORS).filter((anchor) => !ids.has(anchor))).toEqual([]);
  });
});

describe('sidebar nav labels', () => {
  /*
   * Every item the sidebar renders has to have a label in both locales. Without this, a nav item added
   * without its translation renders its own key path — "sidebar.nav.notifications" — in the sidebar, and
   * nothing else catches it: not tsc, not ESLint, not the build, not any other test. It shipped exactly
   * once, which is why this exists.
   */
  it.each(['en', 'es'])('%s labels every nav item', (locale) => {
    const nav = (locale === 'en' ? en : es).sidebar.nav as Record<string, string>;
    const missing = SIDEBAR_NAV_KEYS.filter((key) => !nav[key]);
    expect(missing).toEqual([]);
  });

  it('has no nav label for an item the sidebar no longer renders', () => {
    // The other direction, so a removed item's label does not linger as copy nobody can reach.
    const known = new Set<string>(SIDEBAR_NAV_KEYS);
    expect(Object.keys(en.sidebar.nav).filter((key) => !known.has(key))).toEqual([]);
  });
});

describe('entry-type labels', () => {
  /*
   * The quick-add's type toggle resolves its labels DYNAMICALLY (`entryType.${type}` over
   * ENTRY_TYPES), which is exactly the shape the sidebar guard above exists for: a missing label
   * renders its own key path in the control, and nothing else notices — not tsc, not ESLint, not the
   * build. Both directions, so a removed value's copy does not linger either.
   */
  it.each(['en', 'es'])('%s labels every entry type', (locale) => {
    const labels = (locale === 'en' ? en : es).common.entryType as Record<string, string>;
    expect(ENTRY_TYPES.filter((type) => !labels[type])).toEqual([]);
  });

  it('has no entry-type label for a value the toggle no longer offers', () => {
    const known = new Set<string>([...ENTRY_TYPES, 'label']);
    expect(Object.keys(en.common.entryType).filter((key) => !known.has(key))).toEqual([]);
  });
});

describe('landing feature icons', () => {
  it('names an icon on every feature item, in both locales', () => {
    const missing = [...en.landing.features.items, ...es.landing.features.items].filter(
      (item) => !('icon' in item) || !item.icon,
    );
    expect(missing).toEqual([]);
  });

  it('names an icon that the component can actually resolve', () => {
    const known = new Set(Object.keys(FEATURE_ICONS));
    const unknown = [...en.landing.features.items, ...es.landing.features.items]
      .map((item) => item.icon)
      .filter((icon) => !known.has(icon));
    expect(unknown).toEqual([]);
  });

  it('gives each locale the same icons, so the two lists describe the same six cards', () => {
    const icons = (items: { icon: string }[]) => items.map((item) => item.icon);
    expect(icons(es.landing.features.items)).toEqual(icons(en.landing.features.items));
  });
});
