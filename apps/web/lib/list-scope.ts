import type { ListScope, ListSection } from '@/lib/api/types';

/*
 * The scope-grouped list, on the web side: reading the pill's selection out of the URL, and turning a
 * page of rows into a render list with a header wherever the scope changes (X2).
 *
 * Pure, and that is the point — every rule here is testable without rendering a table, which matters
 * because a component that renders a Radix primitive cannot be driven in the web unit suite at all.
 */

/*
 * The scope the URL asks for, defaulting to the GROUPED view because that is what X2 specifies for a
 * list page — the endpoints themselves default to `private`, which is the fail-closed direction for
 * the nine pickers that read them.
 *
 * An unrecognised value falls back rather than erroring: the pill writes from a fixed set, so anything
 * else is a hand-edited URL, and that is the same posture the sort params already take.
 */
export function resolveListScope(raw: string | undefined): ListScope {
  return raw === 'private' || raw === 'shared' ? raw : 'all';
}

export type SectionedRow<T> =
  | { kind: 'header'; key: string; section: ListSection }
  | { kind: 'row'; key: string; row: T };

/*
 * How a list identifies its sections. Stated by the caller rather than inferred, because a pot-grouped
 * section carries BOTH ids — `pot_sections` fills in the pot's group as well — so guessing from the
 * shape would silently key `/investments` by group and merge two pots of one household into one header.
 */
export const bySectionPot = (section: ListSection): number | null => section.potId;
export const bySectionGroup = (section: ListSection): number | null => section.groupId;

/*
 * A lone "Yours" section is not worth a header: it labels every row on the page, which is exactly what
 * the page title already does, and it would appear the moment somebody joined a group — before they
 * had shared anything at all. So headers are drawn only once a SHARED section exists.
 *
 * The API reports its sections faithfully either way; deciding a header adds nothing is the renderer's
 * call, and keeping it here means all five surfaces make it identically.
 */
export function hasVisibleSections(sections: ListSection[]): boolean {
  return sections.some((section) => section.scope === 'shared');
}

interface SectionAccessors<T> {
  // A stable React key for the row, which on the unioned lists must include the scope: ids are unique
  // per TABLE and not across them, so a private and a shared row really can share a number.
  rowKey: (row: T) => string;
  // The container the row belongs to — its pot id, or its group id — and null for the caller's own.
  scopeKey: (row: T) => number | null;
  // The same container read off a section: bySectionPot or bySectionGroup.
  sectionKey: (section: ListSection) => number | null;
}

/*
 * The page's rows with a header inserted wherever the section changes.
 *
 * The rows arrive SCOPE-MAJOR from the server — the caller's own first, then each container by id —
 * which is what makes a header drawable at all: a section can only be labelled where its rows are
 * contiguous. A section that spans a page boundary therefore gets its header again at the top of the
 * next page, which is the honest behaviour and falls out of walking each page from scratch.
 *
 * A row whose key matches no section emits no header rather than an unlabelled one. It is unreachable
 * — the row query is bounded by exactly the pots the sections are built from — and failing closed is
 * the right direction: a header nobody can read is worse than a row that quietly joins the one above.
 */
export function sectionedRows<T>(
  rows: T[],
  sections: ListSection[],
  { rowKey, scopeKey, sectionKey }: SectionAccessors<T>,
): SectionedRow<T>[] {
  if (!hasVisibleSections(sections)) {
    return rows.map((row) => ({ kind: 'row', key: rowKey(row), row }) as const);
  }

  const byKey = new Map<number | null, ListSection>(
    sections.map((section) => [sectionKey(section), section]),
  );
  const out: SectionedRow<T>[] = [];
  let previous: number | null | undefined;

  rows.forEach((row) => {
    const key = scopeKey(row);
    if (key !== previous) {
      const section = byKey.get(key);
      if (section) out.push({ kind: 'header', key: `section-${key ?? 'own'}`, section });
      previous = key;
    }
    out.push({ kind: 'row', key: rowKey(row), row });
  });

  return out;
}
