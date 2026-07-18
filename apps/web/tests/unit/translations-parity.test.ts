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
