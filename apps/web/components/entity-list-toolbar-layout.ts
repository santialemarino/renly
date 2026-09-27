/*
 * The list toolbar's LAYOUT, in one place: `EntityListToolbar` renders its row from these, and so does
 * the route loading state's toolbar placeholder (`PageSkeleton`), so the two wrap at the same widths
 * and the swap from one to the other moves nothing. A plain module rather than exports of the toolbar
 * itself, which is a client component — a server component importing a constant from one gets a client
 * reference, not the string.
 */

// The row: everything wraps, so a narrow screen stacks rather than overflows.
export const TOOLBAR_ROW = 'flex flex-wrap items-center gap-x-3 gap-y-2';

// The search item grows; `min-w-48` matches `SearchInput`'s own container minimum (see the toolbar).
export const TOOLBAR_SEARCH = 'min-w-48 flex-1';

// The filters group takes its own row until `lg`, where it joins the search row.
export const TOOLBAR_FILTERS =
  'flex flex-wrap items-center gap-x-3 gap-y-2 basis-full lg:basis-auto';

// The trailing actions group (archived pill, extra actions, add) takes its own row until `md`.
export const TOOLBAR_ACTIONS =
  'flex flex-wrap basis-full md:basis-auto items-center gap-x-3 gap-y-2';

// One control inside the filters or actions group: never narrower than its content, sharing the rest.
export const TOOLBAR_ITEM = 'min-w-fit flex-1';
