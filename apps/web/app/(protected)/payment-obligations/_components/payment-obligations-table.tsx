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
import { useTranslations } from 'next-intl';
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
import { cn } from '@repo/ui/lib';
import {
  ExpenseFormDialog,
  type PrefillFromObligation,
} from '@/app/(protected)/expenses/_components/expense-form-dialog';
import { PaymentObligationDeleteDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-delete-dialog';
import { PaymentObligationFormDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-form-dialog';
import {
  archivePaymentObligation,
  unarchivePaymentObligation,
} from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type {
  PaymentObligation,
  PaymentObligationSortField,
  SortOrder,
} from '@/lib/api/payment-obligations';
import { formatAmount } from '@/lib/utils/currency';

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
  const t = useTranslations('paymentObligations');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [editObligation, setEditObligation] = useState<PaymentObligation | null>(null);
  const [deleteState, setDeleteState] = useState<PaymentObligation | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);
  const [markPaidPrefill, setMarkPaidPrefill] = useState<PrefillFromObligation | null>(null);

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
                            {t('table.paidOn', { date: o.lastPaymentDate ?? '' })}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-paragraph-sm tabular-nums">
                      {formatAmount(displayAmount)} {o.convertedAmount ? '' : o.currency}
                    </TableCell>
                    <TableCell>{o.nextDueDate}</TableCell>
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
        onSuccess={() => {
          setMarkPaidPrefill(null);
          router.refresh();
        }}
      />
    </div>
  );
}
