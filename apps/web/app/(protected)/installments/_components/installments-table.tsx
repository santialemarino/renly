'use client';

import { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Archive, ArchiveRestore, ListChecks, Pencil, Trash2 } from 'lucide-react';
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
import { InstallmentDeleteDialog } from '@/app/(protected)/installments/_components/installment-delete-dialog';
import { InstallmentFormDialog } from '@/app/(protected)/installments/_components/installment-form-dialog';
import {
  archiveInstallment,
  unarchiveInstallment,
} from '@/app/(protected)/installments/installment-actions';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Installment, InstallmentSortField } from '@/lib/api/installments';
import type { SortOrder } from '@/lib/api/types';
import { INTEREST_EPSILON } from '@/lib/constants/installments';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

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
  const locale = useLocale();
  const t = useTranslations('installments');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [editInstallment, setEditInstallment] = useState<Installment | null>(null);
  const [deleteState, setDeleteState] = useState<Installment | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);

  const sortBy = (searchParams.get('sort_by') as InstallmentSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.installments}?${params.toString()}`));
  }

  function handleSortChange(column: InstallmentSortField) {
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
                      {formatAmount(
                        installmentDisplay,
                        locale,
                        isConverted ? activeCurrency : inst.currency,
                      )}
                      {currencySuffix}
                    </TableCell>
                    <TableCell className="text-paragraph-sm text-muted-foreground tabular-nums">
                      <div>
                        {formatAmount(
                          String(totalToPay),
                          locale,
                          isConverted ? activeCurrency : inst.currency,
                        )}
                        {currencySuffix}
                      </div>
                      {interestAmount !== null && (
                        <div className="text-paragraph-xs">
                          {t('table.interestSubLine', {
                            amount: `${formatAmount(String(interestAmount), locale, isConverted ? activeCurrency : inst.currency)}${currencySuffix}`,
                          })}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-paragraph-sm-medium tabular-nums">
                      {progressLabel}
                    </TableCell>
                    <TableCell>
                      {inst.nextCuotaDate ? formatDateForLocale(inst.nextCuotaDate, locale) : '—'}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {inst.paymentMethod ? t(`paymentMethods.${inst.paymentMethod}`) : '—'}
                    </TableCell>
                    <TableCell className="text-center">
                      {!inst.isActive ? (
                        <div className="flex items-center justify-center gap-x-1">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8"
                                onClick={() => handleUnarchive(inst)}
                                disabled={archivingId === inst.id}
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
                                onClick={() => setDeleteState(inst)}
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
                                onClick={() => setEditInstallment(inst)}
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
                                onClick={() => handleArchive(inst)}
                                disabled={archivingId === inst.id}
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
                                onClick={() => setDeleteState(inst)}
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
