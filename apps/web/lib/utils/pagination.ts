// How many pages to keep either side of the current one before collapsing the rest into an ellipsis.
const PAGE_NEIGHBOURS = 1;

export type PageItem = number | 'ellipsis';

/*
 * The page numbers a pager should render: always the first and last, the current page's immediate
 * neighbours, and an `'ellipsis'` marker wherever that leaves a gap. Built from the ~5 visible
 * numbers rather than by filtering every page, so a 200-page ledger doesn't allocate 200 entries on
 * each render. Returns an empty list for a single page — there is nothing to navigate.
 */
export function visiblePages(page: number, totalPages: number): PageItem[] {
  if (totalPages <= 1) return [];
  const nearby = Array.from(
    { length: PAGE_NEIGHBOURS * 2 + 1 },
    (_, i) => page - PAGE_NEIGHBOURS + i,
  ).filter((p) => p > 1 && p < totalPages);
  const pages = [...new Set([1, ...nearby, totalPages])].sort((a, b) => a - b);
  return pages.reduce<PageItem[]>((acc, p, idx) => {
    if (idx > 0 && p - (pages[idx - 1] as number) > 1) acc.push('ellipsis');
    acc.push(p);
    return acc;
  }, []);
}
