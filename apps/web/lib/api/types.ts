// Cross-entity API contract types shared by the lib/api feature modules.

export type SortOrder = 'asc' | 'desc';

/*
 * Which scopes a list read asks for (X2). `all` is the grouped view; the other two narrow it to one
 * scope, which is what the pill does. A scope selection FILTERS and is never a mode.
 *
 * The default differs per list, and deliberately: `/investments`, `/accounts` and the snapshots grid
 * default to `private`, because their endpoints have never returned a co-owned row and nine pickers
 * elsewhere in the app read them; `/expenses` and `/income` default to `all`, because they have
 * unioned each member's share since PR 5a. In both cases the default is the one that changes nothing.
 */
export type ListScope = 'all' | 'private' | 'shared';

// --- Raw types (API JSON shape, snake_case) ---

interface SectionTotalRaw {
  currency: string;
  amount: string;
}

export interface ListSectionRaw {
  scope: string;
  pot_id: number | null;
  pot_name: string | null;
  group_id: number | null;
  group_name: string | null;
  can_write: boolean;
  count: number;
  totals: SectionTotalRaw[];
}

// --- Frontend types (camelCase) ---

export interface SectionTotal {
  currency: string;
  // A string, like every other money field on the web: the formatters take one, and round-tripping a
  // decimal through a float is how a figure gains a digit it never had.
  amount: string;
}

/*
 * One labelled section of a scope-grouped list, totalled over the WHOLE filtered set rather than the
 * page shown — a header figure that changed as the reader paged would answer a question nobody asked.
 *
 * `potName` is null for a group's unnamed default pot (A4 leaves it unnamed on purpose); the renderer
 * supplies the fallback through `potLabel`, so no surface can forget it. `canWrite` belongs to the
 * SECTION and not to its rows because write access is granted per (pot, member) and never per row.
 *
 * One shape for four lists plus the grid: `/investments`, `/accounts` and the grid group by POT, while
 * `/expenses` and `/income` group by GROUP, and the fields a list does not group by are simply null.
 */
export interface ListSection {
  scope: 'private' | 'shared';
  potId: number | null;
  potName: string | null;
  groupId: number | null;
  groupName: string | null;
  canWrite: boolean;
  count: number;
  totals: SectionTotal[];
}

// --- Mappers ---

// Exported because five lib/api modules map the same wire shape, and two copies of it would mean the
// next field reaches one call site and silently misses the others.
export function mapListSection(raw: ListSectionRaw): ListSection {
  return {
    scope: raw.scope === 'shared' ? 'shared' : 'private',
    potId: raw.pot_id,
    potName: raw.pot_name,
    groupId: raw.group_id,
    groupName: raw.group_name,
    canWrite: raw.can_write,
    count: raw.count,
    totals: raw.totals.map((total) => ({ currency: total.currency, amount: total.amount })),
  };
}

// Thrown when the API denies admin access (403). Admin pages map this to a 404 (notFound) so the
// page's existence stays hidden from non-admins (not a 403). Shared by every admin-only feature.
export class AdminForbiddenError extends Error {
  constructor() {
    super('admin_forbidden');
    this.name = 'AdminForbiddenError';
  }
}
