'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, ArchiveRestore, Pencil, RefreshCw, Trash2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { SubscriptionDeleteDialog } from '@/app/(protected)/subscriptions/_components/subscription-delete-dialog';
import { SubscriptionFormDialog } from '@/app/(protected)/subscriptions/_components/subscription-form-dialog';
import {
  archiveSubscription,
  unarchiveSubscription,
} from '@/app/(protected)/subscriptions/subscription-actions';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Subscription, SubscriptionSortField } from '@/lib/api/subscriptions';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

interface SubscriptionsTableProps {
  subscriptions: Subscription[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  activeCurrency?: string;
  firstRun?: boolean;
}

export function SubscriptionsTable({
  subscriptions,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  activeCurrency,
  firstRun,
}: SubscriptionsTableProps) {
  const locale = useLocale();
  const t = useTranslations('subscriptions');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, isPending } = useTableSort<SubscriptionSortField>(
    ROUTES.subscriptions,
  );
  const [editSubscription, setEditSubscription] = useState<Subscription | null>(null);
  const [deleteState, setDeleteState] = useState<Subscription | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);

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
                label={t('table.billingCycle')}
                column="billing_cycle"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.nextBillingDate')}
                column="next_billing_date"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.paymentMethod')}</TableHead>
              <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {subscriptions.length === 0 ? (
              <TableEmptyRow
                colSpan={6}
                firstRun={firstRun}
                icon={RefreshCw}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              subscriptions.map((sub) => {
                const displayAmount = sub.convertedAmount ?? sub.amount;
                return (
                  <TableRow key={sub.id} className={!sub.isActive ? 'opacity-60' : undefined}>
                    <TableCell className="text-paragraph-sm-medium">{sub.name}</TableCell>
                    <TableCell className="text-paragraph-sm tabular-nums">
                      {formatAmount(
                        displayAmount,
                        locale,
                        sub.convertedAmount ? activeCurrency : sub.currency,
                      )}{' '}
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
                          <RowActionButton
                            icon={ArchiveRestore}
                            tooltip={t('actions.unarchive')}
                            ariaLabel="Unarchive"
                            onClick={() => handleUnarchive(sub)}
                            disabled={archivingId === sub.id}
                          />
                          <RowActionButton
                            icon={Trash2}
                            tooltip={t('actions.delete')}
                            ariaLabel="Delete"
                            variant="destructive"
                            onClick={() => setDeleteState(sub)}
                          />
                        </div>
                      ) : (
                        <div className="flex items-center justify-center gap-x-1">
                          <RowActionButton
                            icon={Pencil}
                            tooltip={t('actions.edit')}
                            ariaLabel="Edit"
                            onClick={() => setEditSubscription(sub)}
                          />
                          <RowActionButton
                            icon={Archive}
                            tooltip={t('actions.archive')}
                            ariaLabel="Archive"
                            variant="muted"
                            onClick={() => handleArchive(sub)}
                            disabled={archivingId === sub.id}
                          />
                          <RowActionButton
                            icon={Trash2}
                            tooltip={t('actions.delete')}
                            ariaLabel="Delete"
                            variant="destructive"
                            onClick={() => setDeleteState(sub)}
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

      <SubscriptionFormDialog
        open={!!editSubscription}
        onOpenChange={(open) => {
          if (!open) setEditSubscription(null);
        }}
        subscription={editSubscription ?? undefined}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
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
