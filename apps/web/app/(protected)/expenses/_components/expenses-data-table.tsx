'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Lock, Pencil, Receipt, Trash2 } from 'lucide-react';
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
import { ExpenseFormDialog } from '@/app/(protected)/_components/expense-form-dialog';
import {
  LinkedPlanAmountMismatchDialog,
  type LinkedPlanMismatch,
} from '@/app/(protected)/_components/linked-plan-amount-mismatch-dialog';
import { ExpenseDeleteDialog } from '@/app/(protected)/expenses/_components/expense-delete-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { TablePagination } from '@/components/table-pagination';
import { TableSectionRow } from '@/components/table-section-row';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Expense, ExpenseListResponse, ExpenseSortField } from '@/lib/api/expenses';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { Subscription } from '@/lib/api/subscriptions';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { useFormatters } from '@/lib/i18n/formatters';
import { bySectionGroup, sectionedRows } from '@/lib/list-scope';
import { isReconciliationOwned } from '@/lib/reconciliation';
import { isSystemExpenseCategory } from '@/lib/utils/categories';

function RowActions({
  expense,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  accounts,
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
  accounts?: Account[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  onMismatch: (mismatch: LinkedPlanMismatch) => void;
  onSuccess: () => void;
}) {
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  /*
   * Three independent reasons a row action is withheld, each with its own explanation and its own
   * predicate — kept apart rather than collapsed into one flag, because they diverge.
   *
   * A SHARED row is not this user's expense at all: it is their share of one the group recorded, read
   * in by the list's union. Its `id` belongs to `shared_expenses`, and ids are unique per TABLE and
   * not across them — so a PUT or DELETE to /expenses/{id} would land on whatever private expense
   * happens to hold that number. Measured on real data: a shared expense with id 2 sat beside a
   * private one with id 2, so Delete on the shared row would have removed an unrelated expense.
   *
   * A reconciliation's adjustment is derived, so the API refuses BOTH PUT and DELETE on it (409) —
   * offering either would only dead-end or orphan. A system category is narrower: it means the form
   * cannot round-trip the row (no matching combobox option, and the schema's z.enum rejects the stored
   * value), so it withholds Edit while Delete stays legitimate for a row nothing owns — a restored
   * adjustment, whose reconciliation links restore nulls while its category survives. Either way the
   * row explains itself: an action that silently vanishes is the thing this gate exists to avoid.
   */
  const shared = expense.scope === 'shared';
  const reconciliationOwned = isReconciliationOwned(expense);
  const systemCategory = isSystemExpenseCategory(expense.category);
  const canEdit = !shared && !reconciliationOwned && !systemCategory;
  const canDelete = !shared && !reconciliationOwned;
  const lockedReason = shared
    ? ('lockedRow.sharedExpense' as const)
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

      <ExpenseFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        expense={expense}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        accounts={accounts}
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
  accounts,
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
  accounts?: Account[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  activeCurrency?: string;
  firstRun?: boolean;
}) {
  const t = useTranslations('expenses');
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

  const { items, total, page, pageSize, sections } = data;
  const totalPages = Math.ceil(total / pageSize);
  const rendered = sectionedRows(items, sections, {
    // Keyed on scope AND id, because ids are unique per TABLE and not across them: the union really
    // can put a private expense and a shared one with the same number on one page, which as a bare
    // `id` is a duplicate React key.
    rowKey: (expense) => `${expense.scope}-${expense.id}`,
    scopeKey: (expense) => expense.groupId,
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
              rendered.map((entry) =>
                entry.kind === 'header' ? (
                  <TableSectionRow
                    key={entry.key}
                    section={entry.section}
                    colSpan={6}
                    countLabel={t('table.sectionCount', { count: entry.section.count })}
                  />
                ) : (
                  <ExpenseRow
                    key={entry.key}
                    expense={entry.row}
                    activeCurrency={activeCurrency}
                    preferredCurrencies={preferredCurrencies}
                    supportedCurrencies={supportedCurrencies}
                    creditCards={creditCards}
                    accounts={accounts}
                    activeObligations={activeObligations}
                    activeSubscriptions={activeSubscriptions}
                    activeInstallments={activeInstallments}
                    onMismatch={setMismatch}
                    onSuccess={() => router.refresh()}
                  />
                ),
              )
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

      <TablePagination
        page={page}
        totalPages={totalPages}
        totalLabel={t('table.total', { total })}
        onPageChange={handlePageChange}
      />
    </div>
  );
}

// One expense row. Extracted so the section walk composes rows and headers by mapping one list,
// rather than nesting a conditional around fifty lines of markup.
function ExpenseRow({
  expense,
  activeCurrency,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  accounts,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
  onMismatch,
  onSuccess,
}: {
  expense: Expense;
  activeCurrency?: string;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  accounts?: Account[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  onMismatch: (mismatch: LinkedPlanMismatch) => void;
  onSuccess: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  return (
    <TableRow>
      <TableCell>{fmt.date(expense.date)}</TableCell>
      <TableCell className="text-paragraph-sm tabular-nums">
        {fmt.amount(
          expense.convertedAmount ?? expense.amount,
          expense.convertedAmount ? activeCurrency : expense.currency,
        )}
        {/*
         * A shared row's amount is the viewer's SHARE of a larger bill, and without
         * saying so it reads exactly like a solo expense of that size.
         *
         * The sub-line restates the share AND the whole in the row's OWN currency, and
         * names it. Both halves are load-bearing: the cell above may have been converted
         * to the display currency, so a bare "of 120 USD" beneath a converted "61,618"
         * puts two figures in two currencies side by side with an arithmetic relation a
         * reader would try to check and could not. Restating the share makes this line a
         * complete, self-consistent fact whatever the cell above happens to be showing.
         */}
        {expense.scope === 'shared' && expense.fullAmount !== null && (
          <span className="flex flex-wrap items-center justify-start gap-x-2 text-paragraph-xs text-muted-foreground">
            {expense.groupName && <Badge variant="outline">{expense.groupName}</Badge>}
            {t('table.shareOf', {
              share: fmt.amount(expense.amount, expense.currency),
              amount: fmt.amount(expense.fullAmount, expense.currency),
              currency: expense.currency,
            })}
          </span>
        )}
      </TableCell>
      <TableCell>{expense.category ? tCommon(`categories.${expense.category}`) : '—'}</TableCell>
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
          accounts={accounts}
          activeObligations={activeObligations}
          activeSubscriptions={activeSubscriptions}
          activeInstallments={activeInstallments}
          onMismatch={onMismatch}
          onSuccess={onSuccess}
        />
      </TableCell>
    </TableRow>
  );
}
