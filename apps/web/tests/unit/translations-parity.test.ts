import { describe, expect, it } from 'vitest';

import { FEATURE_ICONS } from '@/app/(public)/_components/landing-features';
import type { ProseSectionData } from '@/app/(public)/_components/prose-section';
import { HELP_ANCHORS } from '@/config/routes';
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
