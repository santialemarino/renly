import { describe, expect, it } from 'vitest';

import en from '../../translations/en.json';
import es from '../../translations/es.json';

// Flattens a nested message object into dotted leaf key paths (e.g. "form.language.label").
function flattenKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return value && typeof value === 'object' && !Array.isArray(value)
      ? flattenKeys(value as Record<string, unknown>, path)
      : [path];
  });
}

describe('translation keyset parity', () => {
  const enKeys = new Set(flattenKeys(en as Record<string, unknown>));
  const esKeys = new Set(flattenKeys(es as Record<string, unknown>));

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
 * Collects every array in the message tree keyed by dotted path, with its length — including arrays
 * nested inside array elements (e.g. "help.sections.2.paragraphs"). `flattenKeys` above stops at an
 * array and reports it as a single leaf, so on its own it cannot see that one locale grew a section
 * or a paragraph the other did not.
 */
function collectArrayLengths(
  value: unknown,
  path = '',
  out = new Map<string, number>(),
): Map<string, number> {
  if (Array.isArray(value)) {
    out.set(path, value.length);
    value.forEach((item, index) => collectArrayLengths(item, `${path}.${index}`, out));
  } else if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      collectArrayLengths(child, path ? `${path}.${key}` : key, out);
    }
  }
  return out;
}

// Sorted "path=length" lines, so a mismatch reports which array diverged rather than a diff of maps.
function arrayShape(messages: unknown): string[] {
  return [...collectArrayLengths(messages)].map(([path, length]) => `${path}=${length}`).sort();
}

describe('translation array parity', () => {
  it('has arrays of the same length at every path in both locales', () => {
    expect(arrayShape(es)).toEqual(arrayShape(en));
  });
});

interface ContentSection {
  id?: string;
  heading: string;
}

/*
 * Help anchors the app deep-links to. A help section id is a public URL fragment: renaming one
 * breaks every link silently (the browser simply does not scroll), so the ids in use are pinned
 * here. Call sites: the accounts and dashboard hints link "#accuracy", the snapshots hint links
 * "#snapshots", and the investor-dashboard metrics hint links "#returns".
 */
const LINKED_HELP_ANCHORS = ['accuracy', 'returns', 'snapshots'];

describe('help page anchors', () => {
  const enSections = en.help.sections as ContentSection[];
  const esSections = es.help.sections as ContentSection[];

  it('gives every section a non-empty id', () => {
    expect(enSections.filter((section) => !section.id)).toEqual([]);
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

  it('still defines every anchor the app links to', () => {
    const ids = new Set(enSections.map((section) => section.id));
    expect(LINKED_HELP_ANCHORS.filter((anchor) => !ids.has(anchor))).toEqual([]);
  });
});
