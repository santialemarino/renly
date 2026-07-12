'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Pencil, Receipt, Trash2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import {
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
} from '@repo/ui/components';
import { ExpenseFormDialog } from '@/app/(protected)/_components/expense-form-dialog';
import {
  LinkedPlanAmountMismatchDialog,
  type LinkedPlanMismatch,
} from '@/app/(protected)/_components/linked-plan-amount-mismatch-dialog';
import { ExpenseDeleteDialog } from '@/app/(protected)/expenses/_components/expense-delete-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Expense, ExpenseListResponse, ExpenseSortField } from '@/lib/api/expenses';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { Subscription } from '@/lib/api/subscriptions';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

function RowActions({
  expense,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
  onMismatch,
  onSuccess,
}: {
  expense: Expense;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  onMismatch: (mismatch: LinkedPlanMismatch) => void;
  onSuccess: () => void;
}) {
  const t = useTranslations('expenses');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  return (
    <>
      <div className="flex items-center justify-center gap-x-1">
        <RowActionButton
          icon={Pencil}
          tooltip={t('actions.edit')}
          ariaLabel="Edit"
          onClick={(e) => {
            e.stopPropagation();
            setEditOpen(true);
          }}
        />
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
      </div>

      <ExpenseFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        expense={expense}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={activeObligations}
        activeSubscriptions={activeSubscriptions}
        activeInstallments={activeInstallments}
        onSuccess={onSuccess}
        onLinkedPlanSave={(values, plan) =>
          onMismatch({
            type: plan.type,
            planId: plan.id,
            planName: plan.name,
            enteredAmount: values.amount,
            currentAmount: plan.amount,
            currency: plan.currency,
          })
        }
      />

      <ExpenseDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        expense={expense}
        onSuccess={onSuccess}
      />
    </>
  );
}

export function ExpensesDataTable({
  data,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
  activeCurrency,
  firstRun,
}: {
  data: ExpenseListResponse;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  activeCurrency?: string;
  firstRun?: boolean;
}) {
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, navigate, isPending } =
    useTableSort<ExpenseSortField>(ROUTES.expenses, { resetPage: true });
  // Amount-mismatch follow-up prompt fired from the edit dialog (Phase 3, follow-up
  // Item 6). Lives at the table level rather than per row so the prompt survives the
  // edit dialog's close animation and works the same on any row.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);

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
              <SortableTableHead
                label={t('table.paymentMethod')}
                column="payment_method"
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
                colSpan={6}
                firstRun={firstRun}
                icon={Receipt}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              items.map((expense) => (
                <TableRow key={expense.id}>
                  <TableCell>{formatDateForLocale(expense.date, locale)}</TableCell>
                  <TableCell className="text-paragraph-sm tabular-nums">
                    {formatAmount(
                      expense.convertedAmount ?? expense.amount,
                      locale,
                      expense.convertedAmount ? activeCurrency : expense.currency,
                    )}
                  </TableCell>
                  <TableCell>
                    {expense.category ? tCommon(`categories.${expense.category}`) : '—'}
                  </TableCell>
                  <TableCell>
                    {expense.paymentMethod ? t(`paymentMethods.${expense.paymentMethod}`) : '—'}
                  </TableCell>
                  <TableCell className="max-w-48 truncate text-muted-foreground">
                    {expense.notes ?? '—'}
                  </TableCell>
                  <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                    <RowActions
                      expense={expense}
                      preferredCurrencies={preferredCurrencies}
                      supportedCurrencies={supportedCurrencies}
                      creditCards={creditCards}
                      activeObligations={activeObligations}
                      activeSubscriptions={activeSubscriptions}
                      activeInstallments={activeInstallments}
                      onMismatch={setMismatch}
                      onSuccess={() => router.refresh()}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <LinkedPlanAmountMismatchDialog
        mismatch={mismatch}
        onClose={() => setMismatch(null)}
        onConfirmed={() => {
          setMismatch(null);
          router.refresh();
        }}
      />

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
