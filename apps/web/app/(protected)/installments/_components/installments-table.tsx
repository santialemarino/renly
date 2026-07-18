'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, ArchiveRestore, ListChecks, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { InstallmentDeleteDialog } from '@/app/(protected)/installments/_components/installment-delete-dialog';
import { InstallmentFormDialog } from '@/app/(protected)/installments/_components/installment-form-dialog';
import {
  archiveInstallment,
  unarchiveInstallment,
} from '@/app/(protected)/installments/installment-actions';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Installment, InstallmentSortField } from '@/lib/api/installments';
import { INTEREST_EPSILON } from '@/lib/constants/installments';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { useFormatters } from '@/lib/i18n/formatters';

interface InstallmentsTableProps {
  installments: Installment[];
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  activeCurrency?: string;
  firstRun?: boolean;
}

export function InstallmentsTable({
  installments,
  preferredCurrencies,
  creditCards,
  activeCurrency,
  firstRun,
}: InstallmentsTableProps) {
  const t = useTranslations('installments');
  const fmt = useFormatters();
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, isPending } = useTableSort<InstallmentSortField>(
    ROUTES.installments,
  );
  const [editInstallment, setEditInstallment] = useState<Installment | null>(null);
  const [deleteState, setDeleteState] = useState<Installment | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);

  async function handleArchive(inst: Installment) {
    setArchivingId(inst.id);
    try {
      await archiveInstallment(inst.id);
      toast.success(t('actions.archiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.archiveError'));
    } finally {
      setArchivingId(null);
    }
  }

  async function handleUnarchive(inst: Installment) {
    setArchivingId(inst.id);
    try {
      await unarchiveInstallment(inst.id);
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
                label={t('table.installmentAmount')}
                column="installment_amount"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.totalAmount')}
                column="total_amount"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.progress')}
                column="current_installment"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.nextCuotaDate')}
                column="next_cuota_date"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.paymentMethod')}</TableHead>
              <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {installments.length === 0 ? (
              <TableEmptyRow
                colSpan={7}
                firstRun={firstRun}
                icon={ListChecks}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              installments.map((inst) => {
                const installmentDisplay =
                  inst.convertedInstallmentAmount ?? inst.installmentAmount;
                const isConverted = inst.convertedInstallmentAmount !== null;
                const installmentNum = Number(installmentDisplay);
                const totalToPay = Number.isFinite(installmentNum)
                  ? installmentNum * inst.installmentsCount
                  : 0;
                const baseTotalNum = Number(inst.convertedTotalAmount ?? inst.totalAmount);
                const interestAmount =
                  Number.isFinite(baseTotalNum) && totalToPay > baseTotalNum + INTEREST_EPSILON
                    ? totalToPay - baseTotalNum
                    : null;
                const currencySuffix = isConverted ? '' : ` ${inst.currency}`;
                const paid = Math.max(0, inst.currentInstallment - 1);
                const progressLabel = `${paid}/${inst.installmentsCount}`;
                return (
                  <TableRow key={inst.id} className={!inst.isActive ? 'opacity-60' : undefined}>
                    <TableCell className="text-paragraph-sm-medium">{inst.name}</TableCell>
                    <TableCell className="text-paragraph-sm tabular-nums">
                      {fmt.amount(installmentDisplay, isConverted ? activeCurrency : inst.currency)}
                      {currencySuffix}
                    </TableCell>
                    <TableCell className="text-paragraph-sm text-muted-foreground tabular-nums">
                      <div>
                        {fmt.amount(
                          String(totalToPay),
                          isConverted ? activeCurrency : inst.currency,
                        )}
                        {currencySuffix}
                      </div>
                      {interestAmount !== null && (
                        <div className="text-paragraph-xs">
                          {t('table.interestSubLine', {
                            amount: `${fmt.amount(String(interestAmount), isConverted ? activeCurrency : inst.currency)}${currencySuffix}`,
                          })}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-paragraph-sm-medium tabular-nums">
                      {progressLabel}
                    </TableCell>
                    <TableCell>{inst.nextCuotaDate ? fmt.date(inst.nextCuotaDate) : '—'}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {inst.paymentMethod ? t(`paymentMethods.${inst.paymentMethod}`) : '—'}
                    </TableCell>
                    <TableCell className="text-center">
                      {!inst.isActive ? (
                        <div className="flex items-center justify-center gap-x-1">
                          <RowActionButton
                            icon={ArchiveRestore}
                            tooltip={t('actions.unarchive')}
                            ariaLabel="Unarchive"
                            onClick={() => handleUnarchive(inst)}
                            disabled={archivingId === inst.id}
                          />
                          <RowActionButton
                            icon={Trash2}
                            tooltip={t('actions.delete')}
                            ariaLabel="Delete"
                            variant="destructive"
                            onClick={() => setDeleteState(inst)}
                          />
                        </div>
                      ) : (
                        <div className="flex items-center justify-center gap-x-1">
                          <RowActionButton
                            icon={Pencil}
                            tooltip={t('actions.edit')}
                            ariaLabel="Edit"
                            onClick={() => setEditInstallment(inst)}
                          />
                          <RowActionButton
                            icon={Archive}
                            tooltip={t('actions.archive')}
                            ariaLabel="Archive"
                            variant="muted"
                            onClick={() => handleArchive(inst)}
                            disabled={archivingId === inst.id}
                          />
                          <RowActionButton
                            icon={Trash2}
                            tooltip={t('actions.delete')}
                            ariaLabel="Delete"
                            variant="destructive"
                            onClick={() => setDeleteState(inst)}
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

      <InstallmentFormDialog
        open={!!editInstallment}
        onOpenChange={(open) => {
          if (!open) setEditInstallment(null);
        }}
        installment={editInstallment ?? undefined}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        onSuccess={() => router.refresh()}
      />

      <InstallmentDeleteDialog
        open={!!deleteState}
        onOpenChange={(open) => {
          if (!open) setDeleteState(null);
        }}
        installment={deleteState}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
