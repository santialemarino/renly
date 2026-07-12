'use client';

import { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUp, ChevronsUpDown, Pencil, Receipt, Trash2 } from 'lucide-react';
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
import { cn } from '@repo/ui/lib';
import { ExpenseDeleteDialog } from '@/app/(protected)/expenses/_components/expense-delete-dialog';
import { ExpenseFormDialog } from '@/app/(protected)/expenses/_components/expense-form-dialog';
import {
  LinkedPlanAmountMismatchDialog,
  type LinkedPlanMismatch,
} from '@/app/(protected)/expenses/_components/linked-plan-amount-mismatch-dialog';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Expense, ExpenseListResponse, ExpenseSortField, SortOrder } from '@/lib/api/expenses';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { Subscription } from '@/lib/api/subscriptions';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: ExpenseSortField;
  sortBy: ExpenseSortField | null;
  sortOrder: SortOrder;
}) {
  const active = sortBy === column;
  const isAsc = active && sortOrder === 'asc';
  const isDesc = active && sortOrder === 'desc';
  return (
    <span className="grid shrink-0 group-focus-visible/sort:animate-focus-bump">
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  // Amount-mismatch follow-up prompt fired from the edit dialog (Phase 3, follow-up
  // Item 6). Lives at the table level rather than per row so the prompt survives the
  // edit dialog's close animation and works the same on any row.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);

  const sortBy = (searchParams.get('sort_by') as ExpenseSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.expenses}?${params.toString()}`));
  }

  function handleSortChange(column: ExpenseSortField) {
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
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('date')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.date')}
                  <SortIcon column="date" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('amount')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.amount')}
                  <SortIcon column="amount" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('category')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.category')}
                  <SortIcon column="category" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('payment_method')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.paymentMethod')}
                  <SortIcon column="payment_method" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
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
                    {expense.category ? t(`categories.${expense.category}`) : '—'}
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
