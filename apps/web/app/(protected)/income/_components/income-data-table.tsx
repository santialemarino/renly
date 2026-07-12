'use client';

import { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CircleDollarSign, Pencil, Trash2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import {
  Button,
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { IncomeDeleteDialog } from '@/app/(protected)/income/_components/income-delete-dialog';
import { IncomeFormDialog } from '@/app/(protected)/income/_components/income-form-dialog';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { IncomeEntry, IncomeListResponse, IncomeSortField } from '@/lib/api/income';
import type { SortOrder } from '@/lib/api/types';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

function RowActions({
  income,
  preferredCurrencies,
  supportedCurrencies,
  onSuccess,
}: {
  income: IncomeEntry;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  onSuccess: () => void;
}) {
  const t = useTranslations('income');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  return (
    <>
      <div className="flex items-center justify-center gap-x-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              onClick={(e) => {
                e.stopPropagation();
                setEditOpen(true);
              }}
              aria-label="Edit"
            >
              <Pencil className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('actions.edit')}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteOpen(true);
              }}
              aria-label="Delete"
            >
              <Trash2 className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('actions.delete')}</TooltipContent>
        </Tooltip>
      </div>

      <IncomeFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        income={income}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        onSuccess={onSuccess}
      />

      <IncomeDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        income={income}
        onSuccess={onSuccess}
      />
    </>
  );
}

export function IncomeDataTable({
  data,
  preferredCurrencies,
  supportedCurrencies,
  activeCurrency,
  firstRun,
}: {
  data: IncomeListResponse;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  activeCurrency?: string;
  firstRun?: boolean;
}) {
  const locale = useLocale();
  const t = useTranslations('income');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const sortBy = (searchParams.get('sort_by') as IncomeSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.income}?${params.toString()}`));
  }

  function handleSortChange(column: IncomeSortField) {
    if (sortBy === column) {
      if (sortOrder === 'asc') {
        navigate({ sort_by: column, sort_order: 'desc', page: null });
      } else {
        navigate({ sort_by: null, sort_order: null, page: null });
      }
    } else {
      navigate({ sort_by: column, sort_order: 'asc', page: null });
    }
  }

  function handlePageChange(page: number) {
    navigate({ page: page > 1 ? String(page) : null });
  }

  const { items, total, page, pageSize } = data;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead
                label={t('table.date')}
                column="date"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.amount')}
                column="amount"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.category')}
                column="category"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.notes')}</TableHead>
              <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableEmptyRow
                colSpan={5}
                firstRun={firstRun}
                icon={CircleDollarSign}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>{formatDateForLocale(entry.date, locale)}</TableCell>
                  <TableCell className="text-paragraph-sm tabular-nums">
                    {formatAmount(
                      entry.convertedAmount ?? entry.amount,
                      locale,
                      entry.convertedAmount ? activeCurrency : entry.currency,
                    )}
                  </TableCell>
                  <TableCell>{entry.category ? t(`categories.${entry.category}`) : '—'}</TableCell>
                  <TableCell className="max-w-48 truncate text-muted-foreground">
                    {entry.notes ?? '—'}
                  </TableCell>
                  <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                    <RowActions
                      income={entry}
                      preferredCurrencies={preferredCurrencies}
                      supportedCurrencies={supportedCurrencies}
                      onSuccess={() => router.refresh()}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-paragraph-sm text-muted-foreground">{t('table.total', { total })}</p>
          <Pagination className="w-auto mx-0">
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    if (page > 1) handlePageChange(page - 1);
                  }}
                  aria-disabled={page <= 1}
                  className={page <= 1 ? 'pointer-events-none opacity-50' : ''}
                  text={t('pagination.previous')}
                />
              </PaginationItem>

              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                .reduce<(number | 'ellipsis')[]>((acc, p, idx, arr) => {
                  if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push('ellipsis');
                  acc.push(p);
                  return acc;
                }, [])
                .map((item, idx) =>
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
                          handlePageChange(item);
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
                    if (page < totalPages) handlePageChange(page + 1);
                  }}
                  aria-disabled={page >= totalPages}
                  className={page >= totalPages ? 'pointer-events-none opacity-50' : ''}
                  text={t('pagination.next')}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}
    </div>
  );
}
