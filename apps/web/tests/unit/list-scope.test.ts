import { describe, expect, it } from 'vitest';

import type { ListSection } from '@/lib/api/types';
import {
  bySectionGroup,
  bySectionPot,
  hasVisibleSections,
  resolveGridInterval,
  resolveListScope,
  sectionedRows,
} from '@/lib/list-scope';

/*
 * X2's web-side rules, all of them pure: which scope the URL asks for, whether a header is worth
 * drawing, and where the headers go in a page of rows.
 *
 * Tested here rather than through the tables because a component that renders a Radix primitive
 * cannot be driven in this suite at all — apps/web and packages/ui declare different React ranges and
 * the render dies from inside Radix. Keeping the rules out of the components is what makes them
 * testable, and the components then hold only markup.
 */

interface Row {
  id: number;
  potId: number | null;
  groupId: number | null;
  scope: 'private' | 'shared';
}

function row(id: number, container: number | null): Row {
  return {
    id,
    potId: container,
    groupId: container,
    scope: container === null ? 'private' : 'shared',
  };
}

function section(overrides: Partial<ListSection> = {}): ListSection {
  return {
    scope: 'shared',
    potId: 4,
    potName: 'Viaje',
    groupId: 2,
    groupName: 'Casa',
    canWrite: true,
    count: 1,
    totals: [],
    ...overrides,
  };
}

const OWN = section({
  scope: 'private',
  potId: null,
  potName: null,
  groupId: null,
  groupName: null,
});

const potAccessors = {
  rowKey: (r: Row) => String(r.id),
  scopeKey: (r: Row) => r.potId,
  sectionKey: bySectionPot,
};

describe('resolveListScope', () => {
  it('defaults to the grouped view, which is what a list page renders', () => {
    // The ENDPOINTS default to `private` — the fail-closed direction for the pickers that read them —
    // while a page asks for `all`. The two defaults differ on purpose.
    expect(resolveListScope(undefined)).toBe('all');
    expect(resolveListScope('all')).toBe('all');
  });

  it('reads the two narrowing values', () => {
    expect(resolveListScope('private')).toBe('private');
    expect(resolveListScope('shared')).toBe('shared');
  });

  it('falls back rather than erroring on a value the pill never writes', () => {
    // A hand-edited URL, and the same posture the sort params take.
    expect(resolveListScope('everything')).toBe('all');
    expect(resolveListScope('')).toBe('all');
  });
});

describe('resolveGridInterval', () => {
  it('defaults to monthly, which is the grid every existing user has', () => {
    expect(resolveGridInterval(undefined)).toBe('monthly');
    expect(resolveGridInterval('monthly')).toBe('monthly');
  });

  it('reads the weekly toggle', () => {
    // A toggle rather than something derived: the grid mixes private holdings that declare no cadence
    // with the holdings of several pots that may each declare a different one.
    expect(resolveGridInterval('weekly')).toBe('weekly');
  });

  it('falls back on a value the toggle never writes', () => {
    expect(resolveGridInterval('daily')).toBe('monthly');
  });
});

describe('hasVisibleSections', () => {
  it('is false for a lone private section', () => {
    // A "Yours" header labels every row on the page, which is what the page title already does — and
    // it would appear the moment somebody joined a group, before they had shared anything.
    expect(hasVisibleSections([OWN])).toBe(false);
  });

  it('is false for no sections at all', () => {
    expect(hasVisibleSections([])).toBe(false);
  });

  it('is true once a shared section exists', () => {
    expect(hasVisibleSections([OWN, section()])).toBe(true);
    expect(hasVisibleSections([section()])).toBe(true);
  });
});

describe('sectionedRows', () => {
  it('returns a flat list when nothing is shared', () => {
    // Exactly the table every existing user has: a solo user's page is unchanged by X2.
    const rows = [row(1, null), row(2, null)];
    expect(sectionedRows(rows, [OWN], potAccessors)).toEqual([
      { kind: 'row', key: '1', row: rows[0] },
      { kind: 'row', key: '2', row: rows[1] },
    ]);
  });

  it('opens a header wherever the scope changes', () => {
    const rows = [row(1, null), row(2, null), row(3, 4), row(4, 4)];
    const sections = [OWN, section({ potId: 4 })];
    expect(sectionedRows(rows, sections, potAccessors).map((e) => e.key)).toEqual([
      'section-own',
      '1',
      '2',
      'section-4',
      '3',
      '4',
    ]);
  });

  it('draws one header per container and not one per row', () => {
    // The rows arrive SCOPE-MAJOR, which is what makes a header drawable: two rows of one pot are
    // contiguous, so the second must not repeat the header.
    const rows = [row(1, 4), row(2, 4), row(3, 9)];
    const sections = [section({ potId: 4 }), section({ potId: 9, potName: 'Depto' })];
    const headers = sectionedRows(rows, sections, potAccessors).filter((e) => e.kind === 'header');
    expect(headers.map((h) => (h.kind === 'header' ? h.section.potId : null))).toEqual([4, 9]);
  });

  it('repeats a header when a section continues onto the next page', () => {
    // A section that spans a page boundary is the common case at 25 rows a page, and page two starting
    // mid-section with no header at all would leave its rows unlabelled.
    const pageTwo = [row(26, 4), row(27, 4)];
    const rendered = sectionedRows(pageTwo, [OWN, section({ potId: 4 })], potAccessors);
    expect(rendered[0]).toMatchObject({ kind: 'header' });
  });

  it('keys a group-grouped list by its group and not by a pot', () => {
    // The trap this guards: `pot_sections` fills in the pot's GROUP as well, so a section carries
    // both ids. Inferring the key from the shape would silently merge two pots of one household.
    const rows = [row(1, 2), row(2, 7)];
    const sections = [
      section({ potId: null, groupId: 2, groupName: 'Casa' }),
      section({ potId: null, groupId: 7, groupName: 'Viaje' }),
    ];
    const rendered = sectionedRows(rows, sections, {
      rowKey: (r: Row) => String(r.id),
      scopeKey: (r: Row) => r.groupId,
      sectionKey: bySectionGroup,
    });
    expect(rendered.filter((e) => e.kind === 'header')).toHaveLength(2);
  });

  it('emits no header for a row no section describes', () => {
    // Unreachable — the row query is bounded by exactly the pots the sections are built from — and
    // failing closed is right: a header nobody can read is worse than a row joining the one above.
    const rows = [row(1, 4), row(2, 99)];
    const rendered = sectionedRows(rows, [section({ potId: 4 })], potAccessors);
    expect(rendered.map((e) => e.key)).toEqual(['section-4', '1', '2']);
  });

  it('keeps the row keys the caller supplies, which the unioned lists need', () => {
    // Ids are unique per TABLE and not across them, so a private and a shared row really can share a
    // number — as a bare id that is a duplicate React key.
    const rows = [row(2, null), row(2, 4)];
    const rendered = sectionedRows(rows, [OWN, section({ potId: 4 })], {
      rowKey: (r: Row) => `${r.scope}-${r.id}`,
      scopeKey: (r: Row) => r.potId,
      sectionKey: bySectionPot,
    });
    expect(rendered.filter((e) => e.kind === 'row').map((e) => e.key)).toEqual([
      'private-2',
      'shared-2',
    ]);
  });

  it('returns nothing for no rows', () => {
    expect(sectionedRows([], [OWN, section()], potAccessors)).toEqual([]);
  });
});
