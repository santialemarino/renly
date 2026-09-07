import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Every entity the restore flow can NAME must have a label in both locales.
 *
 * Two places name one: the per-entity preview table walks `RESTORE_SPECS` (what will be inserted) and
 * the "Not restored by this tool" line walks `SKIPPED_ENTITIES` (what deliberately will not be). Both
 * render `data.restore.entities.<key>`, and next-intl answers a missing message by returning its own
 * key path — so an unlabelled entity shows the user `data.restore.entities.notifications` in the middle
 * of a sentence about their own backup. Nothing else catches it: not tsc, not ESLint, not the build,
 * and not the keyset-parity test, which only compares EN against ES and is perfectly happy when a key
 * is absent from both.
 *
 * It has already shipped once. PR 7 added the two notification tables to SKIPPED_ENTITIES and never
 * labelled them, so every real export's preview rendered two key paths — for two PRs.
 *
 * The key list is read from the API's own `restore_specs.py` rather than restated here, for the same
 * reason `api-error-coverage.test.ts` reads `errors.py`: the failure being guarded IS the drift, and a
 * restated list agrees with itself forever.
 */
const RESTORE_SPECS_PY = join(import.meta.dirname, '../../../api/app/domain/restore_specs.py');

function restoreEntityKeys(): { restorable: string[]; skipped: string[] } {
  const source = readFileSync(RESTORE_SPECS_PY, 'utf8');

  // `RestoreSpec("investments", …)` — the first positional argument is the export key. `\s*` because
  // the longer specs wrap, putting the key on its own line.
  const restorable = [...source.matchAll(/RestoreSpec\(\s*"([a-z_]+)"/g)].map(
    (match) => match[1] as string,
  );

  /*
   * Sliced from `SKIPPED_ENTITIES = (` to the first line-initial `)` before pulling strings out, so the
   * prose above the tuple — which quotes phrases of its own — cannot contribute a phantom entity.
   */
  const start = source.indexOf('SKIPPED_ENTITIES = (');
  const body = source.slice(start, source.indexOf('\n)', start));
  const skipped = [...body.matchAll(/"([a-z_]+)"/g)].map((match) => match[1] as string);

  return { restorable, skipped };
}

describe('restore entity labels', () => {
  const { restorable, skipped } = restoreEntityKeys();
  const named = [...restorable, ...skipped];

  // The parse itself has to be load-bearing, or an expression that silently matched nothing would make
  // every assertion below vacuously true. Both counts are asserted against the real files elsewhere
  // (the API's own coverage guards); here it is enough that neither list came back empty and that the
  // two do not overlap, which is the shape restore_specs guarantees.
  it('reads both key lists out of the API source', () => {
    expect(restorable.length).toBeGreaterThan(10);
    expect(skipped.length).toBeGreaterThan(10);
    expect(restorable.filter((key) => skipped.includes(key))).toEqual([]);
  });

  it.each(['en', 'es'])('%s labels every entity the restore flow can name', (locale) => {
    const labels = (locale === 'en' ? en : es).data.restore.entities as Record<string, string>;
    expect(named.filter((key) => !labels[key])).toEqual([]);
  });

  // The other direction, so a label for an entity the restore no longer knows about does not linger as
  // copy nobody can reach — the same pair of guards the sidebar nav and the entry-type toggle carry.
  it('has no label for an entity the restore flow never names', () => {
    const known = new Set(named);
    expect(Object.keys(en.data.restore.entities).filter((key) => !known.has(key))).toEqual([]);
  });
});
