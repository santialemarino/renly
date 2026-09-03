'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { CircleDollarSign, Lock, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { IncomeDeleteDialog } from '@/app/(protected)/income/_components/income-delete-dialog';
import { IncomeFormDialog } from '@/app/(protected)/income/_components/income-form-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { TablePagination } from '@/components/table-pagination';
import { TableSectionRow } from '@/components/table-section-row';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { IncomeEntry, IncomeListResponse, IncomeSortField } from '@/lib/api/income';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { useFormatters } from '@/lib/i18n/formatters';
import { bySectionGroup, sectionedRows } from '@/lib/list-scope';
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
  /*
   * Three independent reasons a row action is withheld, each with its own explanation and its own
   * predicate — kept apart rather than collapsed into one flag, because they diverge. The same three
   * the expenses table gates on, and for the same reasons.
   *
   * A SHARED row is not this user's income entry at all: it is their share of one the group recorded,
   * read in by the list's union. Its `id` belongs to `shared_income`, and ids are unique per TABLE and
   * not across them — so a PUT or DELETE to /income/{id} would land on whatever private entry happens
   * to hold that number.
   *
   * A reconciliation's adjustment is derived, so the API refuses BOTH PUT and DELETE on it (409). A
   * system category is narrower: it means the form cannot round-trip the row, so it withholds Edit
   * while Delete stays legitimate for a row nothing owns.
   */
  const shared = income.scope === 'shared';
  const reconciliationOwned = isReconciliationOwned(income);
  const systemCategory = isSystemIncomeCategory(income.category);
  const canEdit = !shared && !reconciliationOwned && !systemCategory;
  const canDelete = !shared && !reconciliationOwned;
  const lockedReason = shared
    ? ('lockedRow.sharedIncome' as const)
    : reconciliationOwned
      ? ('lockedRow.reconciliationOwned' as const)
      : ('lockedRow.systemCategory' as const);
  const lockedLabel = shared
    ? 'Managed by the group'
    : reconciliationOwned
      ? 'Managed by a reconciliation'
      : 'Category is system-generated';

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
          <RowLockedIndicator icon={Lock} tooltip={tCommon(lockedReason)} ariaLabel={lockedLabel} />
        )}
        {canDelete && (
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
  const t = useTranslations('income');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, navigate, isPending } =
    useTableSort<IncomeSortField>(ROUTES.income, { resetPage: true });

  function handlePageChange(page: number) {
    navigate({ page: page > 1 ? String(page) : null });
  }

  const { items, total, page, pageSize, sections } = data;
  const totalPages = Math.ceil(total / pageSize);
  const rendered = sectionedRows(items, sections, {
    // Keyed on scope AND id, because ids are unique per TABLE and not across them: the union really
    // can put a private entry and a shared one with the same number on one page, which as a bare
    // `id` is a duplicate React key.
    rowKey: (entry) => `${entry.scope}-${entry.id}`,
    scopeKey: (entry) => entry.groupId,
    sectionKey: bySectionGroup,
  });

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
              rendered.map((rendering) =>
                rendering.kind === 'header' ? (
                  <TableSectionRow
                    key={rendering.key}
                    section={rendering.section}
                    colSpan={5}
                    countLabel={t('table.sectionCount', { count: rendering.section.count })}
                  />
                ) : (
                  <IncomeRow
                    key={rendering.key}
                    entry={rendering.row}
                    activeCurrency={activeCurrency}
                    preferredCurrencies={preferredCurrencies}
                    supportedCurrencies={supportedCurrencies}
                    accounts={accounts}
                    onSuccess={() => router.refresh()}
                  />
                ),
              )
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

// One income row. Extracted so the section walk composes rows and headers by mapping one list,
// rather than nesting a conditional around forty lines of markup.
function IncomeRow({
  entry,
  activeCurrency,
  preferredCurrencies,
  supportedCurrencies,
  accounts,
  onSuccess,
}: {
  entry: IncomeEntry;
  activeCurrency?: string;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  accounts?: Account[];
  onSuccess: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('income');
  const tCommon = useTranslations('common');

  return (
    <TableRow>
      <TableCell>{fmt.date(entry.date)}</TableCell>
      <TableCell className="text-paragraph-sm tabular-nums">
        {fmt.amount(
          entry.convertedAmount ?? entry.amount,
          entry.convertedAmount ? activeCurrency : entry.currency,
        )}
        {/*
         * A shared row's amount is the viewer's SHARE of a larger sum, and without saying
         * so it reads exactly like a solo entry of that size.
         *
         * The sub-line restates the share AND the whole in the row's OWN currency, and
         * names it. Both halves are load-bearing: the cell above may have been converted
         * to the display currency, so a bare "of 120 USD" beneath a converted "61,618"
         * puts two figures in two currencies side by side with an arithmetic relation a
         * reader would try to check and could not. Restating the share makes this line a
         * complete, self-consistent fact whatever the cell above happens to be showing.
         */}
        {entry.scope === 'shared' && entry.fullAmount !== null && (
          <span className="flex flex-wrap items-center justify-start gap-x-2 text-paragraph-xs text-muted-foreground">
            {entry.groupName && <Badge variant="outline">{entry.groupName}</Badge>}
            {t('table.shareOf', {
              share: fmt.amount(entry.amount, entry.currency),
              amount: fmt.amount(entry.fullAmount, entry.currency),
              currency: entry.currency,
            })}
          </span>
        )}
      </TableCell>
      <TableCell>{entry.category ? tCommon(`categories.${entry.category}`) : '—'}</TableCell>
      <TableCell className="max-w-48 truncate text-muted-foreground">
        {entry.notes ?? '—'}
      </TableCell>
      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
        <RowActions
          income={entry}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          accounts={accounts}
          onSuccess={onSuccess}
        />
      </TableCell>
    </TableRow>
  );
}
