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

// How many pages to keep either side of the current one before collapsing the rest into an ellipsis.
const PAGE_NEIGHBOURS = 1;

interface TablePaginationProps {
  page: number;
  totalPages: number;
  // Already-translated row count — the noun is per-entity ("12 expenses" / "12 movements"), so it
  // stays in each page's own namespace rather than being reconstructed here.
  totalLabel: string;
  onPageChange: (page: number) => void;
}

// Row count + page links for a paginated table. Renders nothing on a single page.
export function TablePagination({
  page,
  totalPages,
  totalLabel,
  onPageChange,
}: TablePaginationProps) {
  const tCommon = useTranslations('common');

  if (totalPages <= 1) return null;

  // Keep first, last, and the current page's neighbours; inject an ellipsis wherever there is a gap.
  const items = Array.from({ length: totalPages }, (_, i) => i + 1)
    .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= PAGE_NEIGHBOURS)
    .reduce<(number | 'ellipsis')[]>((acc, p, idx, arr) => {
      if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push('ellipsis');
      acc.push(p);
      return acc;
    }, []);

  return (
    <div className="flex items-center justify-between">
      <p className="text-paragraph-sm text-muted-foreground">{totalLabel}</p>
      <Pagination className="w-auto mx-0">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              href="#"
              onClick={(e) => {
                e.preventDefault();
                if (page > 1) onPageChange(page - 1);
              }}
              aria-disabled={page <= 1}
              className={page <= 1 ? 'pointer-events-none opacity-50' : ''}
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
                  isActive={item === page}
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
                if (page < totalPages) onPageChange(page + 1);
              }}
              aria-disabled={page >= totalPages}
              className={page >= totalPages ? 'pointer-events-none opacity-50' : ''}
              text={tCommon('pagination.next')}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}
