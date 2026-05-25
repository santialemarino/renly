'use client';

import { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Archive,
  ArchiveRestore,
  ArrowDown,
  ArrowUp,
  ChevronsUpDown,
  Pencil,
  Trash2,
} from 'lucide-react';
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
import { cn } from '@repo/ui/lib';
import { SubscriptionDeleteDialog } from '@/app/(protected)/subscriptions/_components/subscription-delete-dialog';
import { SubscriptionFormDialog } from '@/app/(protected)/subscriptions/_components/subscription-form-dialog';
import {
  archiveSubscription,
  unarchiveSubscription,
} from '@/app/(protected)/subscriptions/subscription-actions';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { SortOrder, Subscription, SubscriptionSortField } from '@/lib/api/subscriptions';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: SubscriptionSortField;
  sortBy: SubscriptionSortField | null;
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

interface SubscriptionsTableProps {
  subscriptions: Subscription[];
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
}

export function SubscriptionsTable({
  subscriptions,
  preferredCurrencies,
  creditCards,
}: SubscriptionsTableProps) {
  const locale = useLocale();
  const t = useTranslations('subscriptions');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [editSubscription, setEditSubscription] = useState<Subscription | null>(null);
  const [deleteState, setDeleteState] = useState<Subscription | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);

  const sortBy = (searchParams.get('sort_by') as SubscriptionSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.subscriptions}?${params.toString()}`));
  }

  function handleSortChange(column: SubscriptionSortField) {
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

  async function handleArchive(sub: Subscription) {
    setArchivingId(sub.id);
    try {
      await archiveSubscription(sub.id);
      toast.success(t('actions.archiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.archiveError'));
    } finally {
      setArchivingId(null);
    }
  }

  async function handleUnarchive(sub: Subscription) {
    setArchivingId(sub.id);
    try {
      await unarchiveSubscription(sub.id);
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
                  onClick={() => handleSortChange('billing_cycle')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.billingCycle')}
                  <SortIcon column="billing_cycle" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('next_billing_date')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.nextBillingDate')}
                  <SortIcon column="next_billing_date" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>{t('table.paymentMethod')}</TableHead>
              <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {subscriptions.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="py-10 rounded-sm text-center text-muted-foreground"
                >
                  {t('table.empty')}
                </TableCell>
              </TableRow>
            ) : (
              subscriptions.map((sub) => {
                const displayAmount = sub.convertedAmount ?? sub.amount;
                return (
                  <TableRow key={sub.id} className={!sub.isActive ? 'opacity-60' : undefined}>
                    <TableCell className="text-paragraph-sm-medium">{sub.name}</TableCell>
                    <TableCell className="text-paragraph-sm tabular-nums">
                      {formatAmount(displayAmount, locale)}{' '}
                      {sub.convertedAmount ? '' : sub.currency}
                    </TableCell>
                    <TableCell>{t(`billingCycles.${sub.billingCycle}`)}</TableCell>
                    <TableCell>{formatDateForLocale(sub.nextBillingDate, locale)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {sub.paymentMethod ? t(`paymentMethods.${sub.paymentMethod}`) : '—'}
                    </TableCell>
                    <TableCell className="text-center">
                      {!sub.isActive ? (
                        <div className="flex items-center justify-center gap-x-1">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8"
                                onClick={() => handleUnarchive(sub)}
                                disabled={archivingId === sub.id}
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
                                onClick={() => setDeleteState(sub)}
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
                                className="size-8"
                                onClick={() => setEditSubscription(sub)}
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
                                onClick={() => handleArchive(sub)}
                                disabled={archivingId === sub.id}
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
                                onClick={() => setDeleteState(sub)}
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

      <SubscriptionFormDialog
        open={!!editSubscription}
        onOpenChange={(open) => {
          if (!open) setEditSubscription(null);
        }}
        subscription={editSubscription ?? undefined}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        onSuccess={() => router.refresh()}
      />

      <SubscriptionDeleteDialog
        open={!!deleteState}
        onOpenChange={(open) => {
          if (!open) setDeleteState(null);
        }}
        subscription={deleteState}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
