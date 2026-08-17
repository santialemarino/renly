'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { CircleDollarSign, Lock, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { IncomeDeleteDialog } from '@/app/(protected)/income/_components/income-delete-dialog';
import { IncomeFormDialog } from '@/app/(protected)/income/_components/income-form-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { TablePagination } from '@/components/table-pagination';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { IncomeEntry, IncomeListResponse, IncomeSortField } from '@/lib/api/income';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { useFormatters } from '@/lib/i18n/formatters';
import { isReconciliationOwned } from '@/lib/reconciliation';
import { isSystemIncomeCategory } from '@/lib/utils/categories';

function RowActions({
  income,
  preferredCurrencies,
  supportedCurrencies,
  accounts,
  onSuccess,
}: {
  income: IncomeEntry;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  accounts?: Account[];
  onSuccess: () => void;
}) {
  const t = useTranslations('income');
  const tCommon = useTranslations('common');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  // Mirrors the expenses table: reconciliation ownership withholds both actions (the API refuses
  // both), a system category withholds Edit only (the form cannot round-trip the row). Each reason
  // gets its own explanation rather than an action that silently disappears.
  const reconciliationOwned = isReconciliationOwned(income);
  const systemCategory = isSystemIncomeCategory(income.category);
  const canEdit = !reconciliationOwned && !systemCategory;

  return (
    <>
      <div className="flex items-center justify-center gap-x-1">
        {canEdit ? (
          <RowActionButton
            icon={Pencil}
            tooltip={t('actions.edit')}
            ariaLabel="Edit"
            onClick={(e) => {
              e.stopPropagation();
              setEditOpen(true);
            }}
          />
        ) : (
          <RowLockedIndicator
            icon={Lock}
            tooltip={tCommon(
              reconciliationOwned ? 'lockedRow.reconciliationOwned' : 'lockedRow.systemCategory',
            )}
            ariaLabel={
              reconciliationOwned ? 'Managed by a reconciliation' : 'Category is system-generated'
            }
          />
        )}
        {!reconciliationOwned && (
          <RowActionButton
            icon={Trash2}
            tooltip={t('actions.delete')}
            ariaLabel="Delete"
            variant="destructive"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteOpen(true);
            }}
          />
        )}
      </div>

      <IncomeFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        income={income}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={accounts}
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
  accounts,
  activeCurrency,
  firstRun,
}: {
  data: IncomeListResponse;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  accounts?: Account[];
  activeCurrency?: string;
  firstRun?: boolean;
}) {
  const fmt = useFormatters();
  const t = useTranslations('income');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, navigate, isPending } =
    useTableSort<IncomeSortField>(ROUTES.income, { resetPage: true });

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
                  <TableCell>{fmt.date(entry.date)}</TableCell>
                  <TableCell className="text-paragraph-sm tabular-nums">
                    {fmt.amount(
                      entry.convertedAmount ?? entry.amount,
                      entry.convertedAmount ? activeCurrency : entry.currency,
                    )}
                  </TableCell>
                  <TableCell>
                    {entry.category ? tCommon(`categories.${entry.category}`) : '—'}
                  </TableCell>
                  <TableCell className="max-w-48 truncate text-muted-foreground">
                    {entry.notes ?? '—'}
                  </TableCell>
                  <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                    <RowActions
                      income={entry}
                      preferredCurrencies={preferredCurrencies}
                      supportedCurrencies={supportedCurrencies}
                      accounts={accounts}
                      onSuccess={() => router.refresh()}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <TablePagination
        page={page}
        totalPages={totalPages}
        totalLabel={t('table.total', { total })}
        onPageChange={handlePageChange}
      />
    </div>
  );
}
