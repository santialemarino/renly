'use client';

import { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Archive,
  ArchiveRestore,
  ArrowDown,
  ArrowUp,
  BadgeDollarSign,
  ChevronsUpDown,
  Pencil,
  Trash2,
} from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import {
  ExpenseFormDialog,
  type PrefillFromObligation,
} from '@/app/(protected)/expenses/_components/expense-form-dialog';
import type { ExpenseFormValues } from '@/app/(protected)/expenses/expenses-form-schema';
import { PaymentObligationDeleteDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-delete-dialog';
import { PaymentObligationFormDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-form-dialog';
import {
  archivePaymentObligation,
  unarchivePaymentObligation,
  updatePaymentObligationAmount,
} from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type {
  PaymentObligation,
  PaymentObligationSortField,
  SortOrder,
} from '@/lib/api/payment-obligations';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: PaymentObligationSortField;
  sortBy: PaymentObligationSortField | null;
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

interface PaymentObligationsTableProps {
  obligations: PaymentObligation[];
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
}

export function PaymentObligationsTable({
  obligations,
  preferredCurrencies,
  creditCards,
}: PaymentObligationsTableProps) {
  const locale = useLocale();
  const t = useTranslations('paymentObligations');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [editObligation, setEditObligation] = useState<PaymentObligation | null>(null);
  const [deleteState, setDeleteState] = useState<PaymentObligation | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);
  const [markPaidPrefill, setMarkPaidPrefill] = useState<PrefillFromObligation | null>(null);
  // Follow-up amount-mismatch prompt after Mark Paid succeeded with a different amount
  // than the obligation's expected one. Survives the form dialog's close.
  const [amountMismatch, setAmountMismatch] = useState<{
    obligationId: number;
    obligationName: string;
    enteredAmount: string;
    currentAmount: string;
    currency: string;
  } | null>(null);
  const [updatingAmount, setUpdatingAmount] = useState(false);

  const sortBy = (searchParams.get('sort_by') as PaymentObligationSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.paymentObligations}?${params.toString()}`));
  }

  function handleSortChange(column: PaymentObligationSortField) {
    if (sortBy === column) {
      if (sortOrder === 'asc') {
        navigate({ sort_by: column, sort_order: 'desc' });
      } else {
        navigate({ sort_by: null, sort_order: null });
      }
    } else {
      navigate({ sort_by: column, sort_order: 'asc' });
    }
  }

  // Tolerance for the amount-mismatch prompt — anything within 0.01 currency unit is
  // treated as equal (avoids prompting on rounding noise from string-to-number conversion).
  const AMOUNT_TOLERANCE = 0.01;

  // Fires after the expense form saves successfully under Mark Paid. Compares the entered
  // amount against the obligation's current expected amount and opens a follow-up prompt
  // when they differ — lets the user update the obligation's "next expected amount" too.
  function handleMarkPaidSave(savedValues: ExpenseFormValues) {
    if (!markPaidPrefill) return;
    const entered = Number(savedValues.amount);
    const current = Number(markPaidPrefill.amount);
    if (
      Number.isFinite(entered) &&
      Number.isFinite(current) &&
      Math.abs(entered - current) > AMOUNT_TOLERANCE
    ) {
      setAmountMismatch({
        obligationId: markPaidPrefill.paymentObligationId,
        obligationName: markPaidPrefill.obligationName,
        enteredAmount: savedValues.amount,
        currentAmount: markPaidPrefill.amount,
        currency: markPaidPrefill.currency,
      });
    }
  }

  async function confirmAmountUpdate() {
    if (!amountMismatch) return;
    setUpdatingAmount(true);
    try {
      await updatePaymentObligationAmount(
        amountMismatch.obligationId,
        amountMismatch.enteredAmount,
      );
      toast.success(t('markPaid.amountUpdateSuccess'));
      setAmountMismatch(null);
      router.refresh();
    } catch {
      toast.error(t('markPaid.amountUpdateError'));
    } finally {
      setUpdatingAmount(false);
    }
  }

  // Mark paid opens the expense form pre-filled from the obligation (Phase 3, Step E).
  // The server auto-advances next_due_date on save (or archives one-off obligations).
  function handleMarkPaid(obligation: PaymentObligation) {
    setMarkPaidPrefill({
      amount: obligation.amount,
      currency: obligation.currency,
      category: (obligation.expenseCategory ?? undefined) as PrefillFromObligation['category'],
      paymentMethod: (obligation.paymentMethod ??
        undefined) as PrefillFromObligation['paymentMethod'],
      creditCardId: obligation.creditCardId ?? undefined,
      paymentObligationId: obligation.id,
      obligationName: obligation.name,
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
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('name')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.name')}
                  <SortIcon column="name" sortBy={sortBy} sortOrder={sortOrder} />
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
                  onClick={() => handleSortChange('next_due_date')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.dueDate')}
                  <SortIcon column="next_due_date" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('recurrence')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.recurrence')}
                  <SortIcon column="recurrence" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>{t('table.category')}</TableHead>
              <TableHead>{t('table.paymentMethod')}</TableHead>
              <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {obligations.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="py-10 rounded-sm text-center text-muted-foreground"
                >
                  {t('table.empty')}
                </TableCell>
              </TableRow>
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
                      {formatAmount(displayAmount, locale)} {o.convertedAmount ? '' : o.currency}
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
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8"
                                onClick={() => handleUnarchive(o)}
                                disabled={archivingId === o.id}
                                aria-label="Unarchive"
                              >
                                <ArchiveRestore className="size-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('actions.unarchive')}</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground hover:text-destructive"
                                onClick={() => setDeleteState(o)}
                                aria-label="Delete"
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('actions.delete')}</TooltipContent>
                          </Tooltip>
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
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8"
                                onClick={() => setEditObligation(o)}
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
                                className="size-8 text-muted-foreground hover:text-foreground"
                                onClick={() => handleArchive(o)}
                                disabled={archivingId === o.id}
                                aria-label="Archive"
                              >
                                <Archive className="size-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('actions.archive')}</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground hover:text-destructive"
                                onClick={() => setDeleteState(o)}
                                aria-label="Delete"
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{t('actions.delete')}</TooltipContent>
                          </Tooltip>
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
        creditCards={creditCards}
        activeObligations={obligations.filter((o) => o.isActive)}
        onMarkPaidSave={handleMarkPaidSave}
        onSuccess={() => {
          setMarkPaidPrefill(null);
          router.refresh();
        }}
      />

      {/* Amount-mismatch follow-up prompt — sibling of the form dialog so it stays
          open after Mark Paid closes. Two paths: update the obligation's amount to
          match the paid one, or keep the existing expected amount. */}
      <Dialog
        open={!!amountMismatch}
        onOpenChange={(open) => {
          if (!open) setAmountMismatch(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('markPaid.amountMismatchTitle')}</DialogTitle>
          </DialogHeader>
          <p className="text-paragraph-sm text-muted-foreground">
            {t('markPaid.amountMismatchDescription', {
              obligationName: amountMismatch?.obligationName ?? '',
              enteredAmount: amountMismatch?.enteredAmount ?? '',
              currentAmount: amountMismatch?.currentAmount ?? '',
              currency: amountMismatch?.currency ?? '',
            })}
          </p>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAmountMismatch(null)}
              disabled={updatingAmount}
            >
              {t('markPaid.amountMismatchDecline')}
            </Button>
            <Button blue onClick={confirmAmountUpdate} disabled={updatingAmount}>
              {updatingAmount
                ? t('markPaid.amountMismatchUpdating')
                : t('markPaid.amountMismatchConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
