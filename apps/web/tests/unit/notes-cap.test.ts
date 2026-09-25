import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildPotContributeFormSchema } from '@/app/(protected)/shared/pot-form-schema';
import { EXPENSE_NOTES_MAX, SEARCH_MAX } from '@/lib/constants/api-constants';

/*
 * Every free-text `notes` field the web collects is capped at the length the API accepts.
 *
 * The API caps every request `notes` at 500. A form that does not says nothing until the save comes
 * back as a generic failure, after the user wrote the note — the six pot forms were exactly that. Both
 * sides are read from source and the population is derived, so a seventh form or a changed API cap is
 * held to the rule without anybody listing it.
 */

const WEB = join(__dirname, '..', '..');
const API_SCHEMAS = join(WEB, '..', 'api', 'app', 'schemas');

function formSchemas(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return formSchemas(full);
    return entry.endsWith('form-schema.ts') ? [full] : [];
  });
}

// Every `notes: z.string()…` chain in a web form schema, as [file, the chain up to its comma].
function webNotesFields(): [string, string][] {
  return formSchemas(join(WEB, 'app')).flatMap((file) =>
    [...readFileSync(file, 'utf8').matchAll(/notes: (z\s*\.string\(\)[^,\n]*)/g)].map(
      (match): [string, string] => [relative(WEB, file), match[1] ?? ''],
    ),
  );
}

// The whole `notes` declaration in a class body — annotation AND default — from `notes:` to the end of
// the statement: the first newline reached with every bracket closed. Read as one statement so neither
// a Field split across lines nor a cap carried in the annotation (`notes: Annotated[str | None,
// Field(max_length=600)] = Field(default=None)`) is skipped.
function notesDeclarations(body: string): string[] {
  return [...body.matchAll(/^[ \t]+notes:/gm)].map((match) => {
    const start = match.index ?? 0;
    let depth = 0;
    let end = start;
    while (end < body.length) {
      const char = body[end];
      if ('([{'.includes(char ?? '')) depth += 1;
      if (')]}'.includes(char ?? '')) depth -= 1;
      if (char === '\n' && depth === 0) break;
      end += 1;
    }
    return body.slice(start, end);
  });
}

// Every `max_length` on every `notes` field of an API REQUEST schema (a class inheriting RequestBase),
// wherever in the declaration it sits. A notes field with no `max_length` at all reads as NaN, which the
// equality below refuses.
function apiNotesCaps(): number[] {
  return readdirSync(API_SCHEMAS)
    .filter((f) => f.endsWith('.py'))
    .flatMap((f) =>
      readFileSync(join(API_SCHEMAS, f), 'utf8')
        .split(/^class /m)
        .filter((body) => /^\w+\([^)]*RequestBase[^)]*\):/.test(body))
        .flatMap((body) =>
          notesDeclarations(body).flatMap((declaration) => {
            const caps = [...declaration.matchAll(/max_length\s*=\s*(\d+)/g)].map((m) =>
              Number(m[1]),
            );
            return caps.length > 0 ? caps : [Number.NaN];
          }),
        ),
    );
}

describe('notes caps', () => {
  it('caps every web notes field at EXPENSE_NOTES_MAX', () => {
    const uncapped = webNotesFields()
      .filter(([, chain]) => !chain.includes('.max(EXPENSE_NOTES_MAX)'))
      .map(([file, chain]) => `${file}: ${chain}`);
    expect(uncapped).toEqual([]);
  });

  it('mirrors the cap every API request schema puts on notes', () => {
    const caps = apiNotesCaps();
    expect(caps.length).toBeGreaterThanOrEqual(10);
    expect([...new Set(caps)]).toEqual([EXPENSE_NOTES_MAX]);
  });

  it('is reading the pot forms', () => {
    // Anti-vacuity: the six pot forms are certain to exist.
    const pot = webNotesFields().filter(([file]) => file.endsWith('pot-form-schema.ts'));
    expect(pot).toHaveLength(6);
  });

  it('stops the list search box where the API search cap is', () => {
    // Same pairing for the one free-text query parameter a web control types into: past the API's
    // `SEARCH_MAX_LENGTH` the list request is a 422, so the box must not accept more.
    const params = readFileSync(join(API_SCHEMAS, 'params.py'), 'utf8');
    expect(Number(/^SEARCH_MAX_LENGTH = (\d+)$/m.exec(params)?.[1])).toBe(SEARCH_MAX);
  });

  it('refuses a note one character past the cap', () => {
    const schema = buildPotContributeFormSchema('required');
    expect(
      schema.safeParse({ holding: 'account:1', notes: 'x'.repeat(EXPENSE_NOTES_MAX) }).success,
    ).toBe(true);
    expect(
      schema.safeParse({ holding: 'account:1', notes: 'x'.repeat(EXPENSE_NOTES_MAX + 1) }).success,
    ).toBe(false);
  });
});
