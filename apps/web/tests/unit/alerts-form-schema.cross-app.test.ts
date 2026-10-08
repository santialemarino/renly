import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildAlertsFormSchema } from '@/app/(protected)/alerts/alerts-form-schema';
import { COLLECTION_WARNING_PCT_RANGE, MAX_COLLECTIONS_RANGE } from '@/lib/constants/collections';

/*
 * The two collection-limit fields accept exactly the range the API does. Before the API ranged them, it
 * stored a 4,000-digit limit and a negative percentage; a form that let either through would now be
 * refused with a 422 after the user pressed save, so the form states the same rule — read from the
 * API's source here rather than restated, so the two cannot drift.
 */

const SETTINGS_PY = join(__dirname, '..', '..', '..', 'api', 'app', 'schemas', 'settings.py');

function apiRange(name: string): [number, number] {
  const match = new RegExp(`^${name} = \\((\\d+), (\\d+)\\)$`, 'm').exec(
    readFileSync(SETTINGS_PY, 'utf8'),
  );
  if (!match) throw new Error(`${name} not found in settings.py`);
  return [Number(match[1]), Number(match[2])];
}

const schema = buildAlertsFormSchema({
  maxCollectionsInvalidMsg: 'max',
  collectionWarningPctInvalidMsg: 'pct',
  liquidityThresholdInvalidMsg: 'liquidity',
  savingsRateInvalidMsg: 'savings',
  incomeExpenseRatioInvalidMsg: 'ratio',
});

describe.each([
  ['maxCollections', 'MAX_COLLECTIONS_RANGE', MAX_COLLECTIONS_RANGE],
  ['collectionWarningPct', 'COLLECTION_WARNING_PCT_RANGE', COLLECTION_WARNING_PCT_RANGE],
] as const)('%s', (field, apiName, [min, max]) => {
  it('mirrors the range the API enforces', () => {
    expect([min, max]).toEqual(apiRange(apiName));
  });

  it('accepts both ends and a blank field', () => {
    expect(schema.safeParse({ [field]: String(min) }).success).toBe(true);
    expect(schema.safeParse({ [field]: String(max) }).success).toBe(true);
    expect(schema.safeParse({ [field]: '' }).success).toBe(true);
  });

  it('refuses one past either end and a fraction', () => {
    expect(schema.safeParse({ [field]: String(min - 1) }).success).toBe(false);
    expect(schema.safeParse({ [field]: String(max + 1) }).success).toBe(false);
    expect(schema.safeParse({ [field]: '1.5' }).success).toBe(false);
  });
});
