'use client';

import { useTranslations } from 'next-intl';

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@repo/ui/components';
import { visiblePages } from '@/lib/utils/pagination';

interface TablePaginationProps {
  page: number;
  totalPages: number;
  // Already-translated row count — the noun is per-entity ("12 expenses" / "12 movements"), so it
  // stays in each page's own namespace rather than being reconstructed here.
  totalLabel: string;
  onPageChange: (page: number) => void;
}

// Row count + page links for a paginated table. The count always shows — it describes the list, not
// the pager — while the page links appear only once there is more than one page.
export function TablePagination({
  page,
  totalPages,
  totalLabel,
  onPageChange,
}: TablePaginationProps) {
  const tCommon = useTranslations('common');

  /*
   * A page past the end reads as the last real page, and that is what makes an out-of-range page
   * RECOVERABLE rather than a trap. It is reachable two ways — a hand-typed or bookmarked `?page=50`,
   * and deleting the last row of the last page, which shortens the list under a page number that no
   * longer exists. Without the clamp the pager highlights nothing, `visiblePages` drops the current
   * page (it keeps only `1 < p < totalPages`), and Previous decrements one nonexistent page per click.
   */
  const current = Math.min(Math.max(page, 1), totalPages);

  const items = visiblePages(current, totalPages);

  return (
    <div className="flex items-center justify-between">
      <p className="text-paragraph-sm text-muted-foreground">{totalLabel}</p>
      {totalPages > 1 && (
        <Pagination className="w-auto mx-0">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  if (current > 1) onPageChange(current - 1);
                }}
                aria-disabled={current <= 1}
                className={current <= 1 ? 'pointer-events-none opacity-50' : ''}
                text={tCommon('pagination.previous')}
              />
            </PaginationItem>

            {items.map((item, idx) =>
              item === 'ellipsis' ? (
                <PaginationItem key={`ellipsis-${idx}`}>
                  <PaginationEllipsis />
                </PaginationItem>
              ) : (
                <PaginationItem key={item}>
                  <PaginationLink
                    href="#"
                    isActive={item === current}
                    onClick={(e) => {
                      e.preventDefault();
                      onPageChange(item);
                    }}
                  >
                    {item}
                  </PaginationLink>
                </PaginationItem>
              ),
            )}

            <PaginationItem>
              <PaginationNext
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  if (current < totalPages) onPageChange(current + 1);
                }}
                aria-disabled={current >= totalPages}
                className={current >= totalPages ? 'pointer-events-none opacity-50' : ''}
                text={tCommon('pagination.next')}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
    </div>
  );
}
