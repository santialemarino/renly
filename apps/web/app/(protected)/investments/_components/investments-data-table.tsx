'use client';

import { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Archive, ArchiveRestore, ArrowDown, ArrowUp, ChevronsUpDown, Pencil } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

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
import { cn } from '@repo/ui/lib';
import { InvestmentArchiveFormDialog } from '@/app/(protected)/investments/_components/investment-archive-form-dialog';
import { InvestmentFormDialog } from '@/app/(protected)/investments/_components/investment-form-dialog';
import { unarchiveInvestment } from '@/app/(protected)/investments/investments-actions';
import { ROUTES } from '@/config/routes';
import type {
  Investment,
  InvestmentGroup,
  InvestmentListResponse,
  InvestmentSortField,
  SortOrder,
} from '@/lib/api/investments';

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: InvestmentSortField;
  sortBy: InvestmentSortField | null;
  sortOrder: SortOrder;
}) {
  const active = sortBy === column;
  const isAsc = active && sortOrder === 'asc';
  const isDesc = active && sortOrder === 'desc';
  // All three icons share the same grid cell; only one is visible at a time via opacity/scale.
  return (
    <span className="grid shrink-0">
      <ChevronsUpDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-400 transition-all duration-200',
          active ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
        )}
      />
      <ArrowUp
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isAsc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
      <ArrowDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isDesc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
    </span>
  );
}

function RowActions({
  investment,
  groups,
  pinnedCurrencies,
  preferredCurrencies,
  onSuccess,
}: {
  investment: Investment;
  groups: InvestmentGroup[];
  pinnedCurrencies?: string[];
  preferredCurrencies?: string[];
  onSuccess: () => void;
}) {
  const t = useTranslations('investments');
  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [unarchiving, setUnarchiving] = useState(false);

  async function handleUnarchive(e: React.MouseEvent) {
    e.stopPropagation();
    setUnarchiving(true);
    try {
      await unarchiveInvestment(investment.id);
      toast.success(t('unarchiveSuccess'));
      onSuccess();
    } catch {
      toast.error(t('unarchiveError'));
    } finally {
      setUnarchiving(false);
    }
  }

  if (!investment.isActive) {
    return (
      <div className="flex items-center justify-center">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              onClick={handleUnarchive}
              disabled={unarchiving}
              aria-label={t('actions.unarchive')}
            >
              <ArchiveRestore className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('actions.unarchive')}</TooltipContent>
        </Tooltip>
      </div>
    );
  }

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
              aria-label={t('actions.edit')}
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
              className="size-8 text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                setArchiveOpen(true);
              }}
              aria-label={t('actions.archive')}
            >
              <Archive className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('actions.archive')}</TooltipContent>
        </Tooltip>
      </div>

      {editOpen && (
        <InvestmentFormDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          investment={investment}
          groups={groups}
          pinnedCurrencies={pinnedCurrencies}
          preferredCurrencies={preferredCurrencies}
          onSuccess={onSuccess}
        />
      )}

      {archiveOpen && (
        <InvestmentArchiveFormDialog
          open={archiveOpen}
          onOpenChange={setArchiveOpen}
          investment={investment}
          onSuccess={onSuccess}
        />
      )}
    </>
  );
}

export function InvestmentsDataTable({
  data,
  groups,
  pinnedCurrencies,
  preferredCurrencies,
}: {
  data: InvestmentListResponse;
  groups: InvestmentGroup[];
  pinnedCurrencies?: string[];
  preferredCurrencies?: string[];
}) {
  const t = useTranslations('investments');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const sortBy = (searchParams.get('sort_by') as InvestmentSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.investments}?${params.toString()}`));
  }

  function handleSortChange(column: InvestmentSortField) {
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

  function handleRowClick(investment: Investment) {
    router.push(`${ROUTES.dashboard}?investment_id=${investment.id}`);
  }

  const { items, total, page, pageSize } = data;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">{t('table.id')}</TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('name')}
                  className="flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:animate-focus-bump"
                >
                  {t('table.name')}
                  <SortIcon column="name" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>{t('table.groups')}</TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('category')}
                  className="flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:animate-focus-bump"
                >
                  {t('table.category')}
                  <SortIcon column="category" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('base_currency')}
                  className="flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:animate-focus-bump"
                >
                  {t('table.currency')}
                  <SortIcon column="base_currency" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>{t('table.ticker')}</TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('broker')}
                  className="flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:animate-focus-bump"
                >
                  {t('table.broker')}
                  <SortIcon column="broker" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-10 rounded-sm text-center text-muted-foreground"
                >
                  {t('table.empty')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((investment) => (
                <TableRow
                  key={investment.id}
                  className="cursor-pointer"
                  onClick={() => handleRowClick(investment)}
                >
                  <TableCell className="text-muted-foreground">{investment.id}</TableCell>
                  <TableCell className="text-paragraph-sm-medium">{investment.name}</TableCell>
                  <TableCell>
                    {investment.groups.length > 0 ? (
                      <div className="flex flex-wrap gap-x-1 gap-y-1">
                        {investment.groups.map((g) => (
                          <span
                            key={g.id}
                            className="px-1.5 py-0.5 rounded text-paragraph-xs bg-muted text-muted-foreground"
                          >
                            {g.name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>{tCommon(`categories.${investment.category}`)}</TableCell>
                  <TableCell>{investment.baseCurrency}</TableCell>
                  <TableCell className="text-muted-foreground font-mono">
                    {investment.ticker ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {investment.broker ?? '—'}
                  </TableCell>
                  <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                    <RowActions
                      investment={investment}
                      groups={groups}
                      pinnedCurrencies={pinnedCurrencies}
                      preferredCurrencies={preferredCurrencies}
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

              {/* Keep first, last, and the two neighbours of the current page; inject ellipsis where there is a gap. */}
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
