'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, ArchiveRestore, BadgeDollarSign, FileText, Pencil, Trash2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
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
import {
  ExpenseFormDialog,
  type PrefillFromObligation,
} from '@/app/(protected)/_components/expense-form-dialog';
import {
  LinkedPlanAmountMismatchDialog,
  type LinkedPlanMismatch,
} from '@/app/(protected)/_components/linked-plan-amount-mismatch-dialog';
import type { ExpenseFormValues } from '@/app/(protected)/expenses/expenses-form-schema';
import { PaymentObligationDeleteDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-delete-dialog';
import { PaymentObligationFormDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-form-dialog';
import {
  archivePaymentObligation,
  unarchivePaymentObligation,
} from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { PaymentObligation, PaymentObligationSortField } from '@/lib/api/payment-obligations';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

interface PaymentObligationsTableProps {
  obligations: PaymentObligation[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  activeCurrency?: string;
  firstRun?: boolean;
}

export function PaymentObligationsTable({
  obligations,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  activeCurrency,
  firstRun,
}: PaymentObligationsTableProps) {
  const locale = useLocale();
  const t = useTranslations('paymentObligations');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, isPending } =
    useTableSort<PaymentObligationSortField>(ROUTES.paymentObligations);
  const [editObligation, setEditObligation] = useState<PaymentObligation | null>(null);
  const [deleteState, setDeleteState] = useState<PaymentObligation | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);
  const [markPaidPrefill, setMarkPaidPrefill] = useState<PrefillFromObligation | null>(null);
  // Follow-up amount-mismatch prompt after Mark Paid succeeded with a different amount
  // than the obligation's expected one (Phase 3, follow-up Item 6). Now uses the shared
  // LinkedPlanAmountMismatchDialog — the inline dialog was deduplicated.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);

  // Fires after the expense form saves successfully under Mark Paid (Phase 3, follow-up
  // Item 6). The form already computed the amount mismatch; we just stash the plan ref so
  // the shared LinkedPlanAmountMismatchDialog can render the prompt as a sibling of the
  // form dialog (survives the form's close animation).
  function handleLinkedPlanSave(
    savedValues: ExpenseFormValues,
    plan: {
      type: 'obligation' | 'subscription';
      id: number;
      name: string;
      amount: string;
      currency: string;
    },
  ) {
    if (plan.type !== 'obligation') return;
    setMismatch({
      type: plan.type,
      planId: plan.id,
      planName: plan.name,
      enteredAmount: savedValues.amount,
      currentAmount: plan.amount,
      currency: plan.currency,
    });
  }

  // Mark paid opens the expense form pre-filled from the obligation (Phase 3, Step E).
  // The server auto-advances next_due_date on save (or archives one-off obligations).
  // `recurrence` is threaded so the form can surface the "Cycles to pre-pay" input on
  // recurring obligations only (Phase 3, follow-up Item 2).
  function handleMarkPaid(obligation: PaymentObligation) {
    setMarkPaidPrefill({
      amount: obligation.amount,
      currency: obligation.currency,
      category: (obligation.expenseCategory ?? undefined) as PrefillFromObligation['category'],
      paymentMethod: (obligation.paymentMethod ??
        undefined) as PrefillFromObligation['paymentMethod'],
      creditCardId: obligation.creditCardId ?? undefined,
      paymentObligationId: obligation.id,
      recurrence: obligation.recurrence,
    });
  }

  async function handleArchive(obligation: PaymentObligation) {
    setArchivingId(obligation.id);
    try {
      await archivePaymentObligation(obligation.id);
      toast.success(t('actions.archiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.archiveError'));
    } finally {
      setArchivingId(null);
    }
  }

  async function handleUnarchive(obligation: PaymentObligation) {
    setArchivingId(obligation.id);
    try {
      await unarchivePaymentObligation(obligation.id);
      toast.success(t('actions.unarchiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.unarchiveError'));
    } finally {
      setArchivingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead
                label={t('table.name')}
                column="name"
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
                label={t('table.dueDate')}
                column="next_due_date"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.recurrence')}
                column="recurrence"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.category')}</TableHead>
              <TableHead>{t('table.paymentMethod')}</TableHead>
              <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {obligations.length === 0 ? (
              <TableEmptyRow
                colSpan={7}
                firstRun={firstRun}
                icon={FileText}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              obligations.map((o) => {
                const displayAmount = o.convertedAmount ?? o.amount;
                // One-off paid obligations are archived after Mark Paid — surface
                // the payment date as a sub-line so the user can find it later.
                const showPaidOn = !o.isActive && !o.recurrence && o.lastPaymentDate;
                return (
                  <TableRow key={o.id} className={!o.isActive ? 'opacity-60' : undefined}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="text-paragraph-sm-medium">{o.name}</span>
                        {showPaidOn && (
                          <span className="text-paragraph-xs text-muted-foreground">
                            {t('table.paidOn', {
                              date: o.lastPaymentDate
                                ? formatDateForLocale(o.lastPaymentDate, locale)
                                : '',
                            })}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-paragraph-sm tabular-nums">
                      {formatAmount(
                        displayAmount,
                        locale,
                        o.convertedAmount ? activeCurrency : o.currency,
                      )}{' '}
                      {o.convertedAmount ? '' : o.currency}
                    </TableCell>
                    <TableCell>{formatDateForLocale(o.nextDueDate, locale)}</TableCell>
                    <TableCell>
                      {o.recurrence ? t(`recurrences.${o.recurrence}`) : t('recurrences.oneOff')}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{o.category || '—'}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {o.paymentMethod ? t(`paymentMethods.${o.paymentMethod}`) : '—'}
                    </TableCell>
                    <TableCell className="text-center">
                      {!o.isActive ? (
                        <div className="flex items-center justify-center gap-x-1">
                          <RowActionButton
                            icon={ArchiveRestore}
                            tooltip={t('actions.unarchive')}
                            ariaLabel="Unarchive"
                            onClick={() => handleUnarchive(o)}
                            disabled={archivingId === o.id}
                          />
                          <RowActionButton
                            icon={Trash2}
                            tooltip={t('actions.delete')}
                            ariaLabel="Delete"
                            variant="destructive"
                            onClick={() => setDeleteState(o)}
                          />
                        </div>
                      ) : (
                        <div className="flex items-center justify-center gap-x-1">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground hover:text-blue-700"
                                onClick={() => handleMarkPaid(o)}
                                aria-label="Mark paid"
                              >
                                <BadgeDollarSign className="size-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('actions.markPaid')}</TooltipContent>
                          </Tooltip>
                          <RowActionButton
                            icon={Pencil}
                            tooltip={t('actions.edit')}
                            ariaLabel="Edit"
                            onClick={() => setEditObligation(o)}
                          />
                          <RowActionButton
                            icon={Archive}
                            tooltip={t('actions.archive')}
                            ariaLabel="Archive"
                            variant="muted"
                            onClick={() => handleArchive(o)}
                            disabled={archivingId === o.id}
                          />
                          <RowActionButton
                            icon={Trash2}
                            tooltip={t('actions.delete')}
                            ariaLabel="Delete"
                            variant="destructive"
                            onClick={() => setDeleteState(o)}
                          />
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <PaymentObligationFormDialog
        open={!!editObligation}
        onOpenChange={(open) => {
          if (!open) setEditObligation(null);
        }}
        obligation={editObligation ?? undefined}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        onSuccess={() => router.refresh()}
      />

      <PaymentObligationDeleteDialog
        open={!!deleteState}
        onOpenChange={(open) => {
          if (!open) setDeleteState(null);
        }}
        obligation={deleteState}
        onSuccess={() => router.refresh()}
      />

      <ExpenseFormDialog
        open={!!markPaidPrefill}
        onOpenChange={(open) => {
          if (!open) setMarkPaidPrefill(null);
        }}
        prefillFromObligation={markPaidPrefill ?? undefined}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={obligations.filter((o) => o.isActive)}
        onLinkedPlanSave={handleLinkedPlanSave}
        onSuccess={() => {
          setMarkPaidPrefill(null);
          router.refresh();
        }}
      />

      <LinkedPlanAmountMismatchDialog
        mismatch={mismatch}
        onClose={() => setMismatch(null)}
        onConfirmed={() => {
          setMismatch(null);
          router.refresh();
        }}
      />
    </div>
  );
}
