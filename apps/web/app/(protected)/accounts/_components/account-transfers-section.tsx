'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, Trash2 } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
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
} from '@repo/ui/components';
import { deleteTransfer, fetchAccountTransfers } from '@/app/(protected)/accounts/account-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { SignedAmountCell } from '@/components/signed-amount-cell';
import { TablePagination } from '@/components/table-pagination';
import type { Account } from '@/lib/api/accounts';
import type { Transfer } from '@/lib/api/transfers';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';
import { API_DEFAULT_PAGE_SIZE } from '@/lib/constants/api-constants';
import { useFormatters } from '@/lib/i18n/formatters';

// Minimum time (ms) from fetch start before showing the result, so an instant resolve doesn't flash.
const TRANSFERS_DISPLAY_DELAY_MS = 500;

interface AccountTransfersSectionProps {
  account: Account;
  expanded: boolean;
  colSpan: number;
  // Bumped by the parent after a transfer lands, so an already-loaded row re-reads its list.
  reloadToken: number;
  onTransfer: () => void;
  onChanged: () => void;
}

export function AccountTransfersSection({
  account,
  expanded,
  colSpan,
  reloadToken,
  onTransfer,
  onChanged,
}: AccountTransfersSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('accounts.transfers');

  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(API_DEFAULT_PAGE_SIZE);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Transfer | null>(null);
  const [deleting, setDeleting] = useState(false);
  // The reloadToken whose data is currently loaded; null until the first fetch.
  const loadedTokenRef = useRef<number | null>(null);
  // The page that token was loaded for, so a page change re-fetches while a re-expand does not.
  const loadedPageRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const start = Date.now();
    try {
      const data = await fetchAccountTransfers(account.id, page);
      const elapsed = Date.now() - start;
      if (elapsed < TRANSFERS_DISPLAY_DELAY_MS) {
        await new Promise((r) => setTimeout(r, TRANSFERS_DISPLAY_DELAY_MS - elapsed));
      }
      setTransfers(data.items);
      setTotal(data.total);
      setPageSize(data.pageSize);
    } catch {
      setTransfers([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [account.id, page]);

  // Fetch on first expand; re-expand shows cached data instantly. A bumped reloadToken invalidates it,
  // and so does a page change — that asks for different rows rather than re-opening the loaded ones.
  useEffect(() => {
    if (!expanded) return;
    if (loadedTokenRef.current === reloadToken && loadedPageRef.current === page) return;
    loadedTokenRef.current = reloadToken;
    loadedPageRef.current = page;
    load();
  }, [expanded, reloadToken, page, load]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const result = await deleteTransfer(deleteTarget.id);
      if (!result.ok) {
        toast.error(result.error || t('delete.error'));
        return;
      }
      toast.success(t('delete.success'));
      setDeleteTarget(null);
      onChanged();
    } catch {
      toast.error(t('delete.error'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <AnimatePresence>
      {expanded && (
        <TableRow>
          <TableCell colSpan={colSpan} className="p-0">
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: ANIMATION_DEFAULT, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <div className="px-8 py-4 bg-muted/30">
                <div className="flex items-start justify-between gap-x-4">
                  <div className="flex flex-col gap-y-0.5">
                    <span className="text-paragraph-sm-medium">{t('title')}</span>
                    <span className="text-paragraph-xs text-muted-foreground">{t('subtitle')}</span>
                  </div>
                  {/* Archived accounts are read-only here, matching their hidden row action. */}
                  {account.isActive && (
                    <Button variant="outline" size="sm" onClick={onTransfer}>
                      {t('transferButton')}
                    </Button>
                  )}
                </div>

                <AnimatePresence mode="wait">
                  {loading ? (
                    <motion.p
                      key="loading"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: ANIMATION_FAST }}
                      className="mt-3 text-paragraph-sm text-muted-foreground"
                    >
                      {t('loading')}
                    </motion.p>
                  ) : transfers.length === 0 ? (
                    <motion.p
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: ANIMATION_FAST }}
                      className="mt-3 text-paragraph-sm text-muted-foreground"
                    >
                      {t('empty')}
                    </motion.p>
                  ) : (
                    <motion.div
                      key="table"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: ANIMATION_FAST }}
                      className="mt-3"
                    >
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{t('table.date')}</TableHead>
                            <TableHead>{t('table.direction')}</TableHead>
                            <TableHead className="text-right">{t('table.amount')}</TableHead>
                            <TableHead>{t('table.notes')}</TableHead>
                            <TableHead className="w-16 text-center">{t('table.actions')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {transfers.map((transfer) => {
                            const outgoing = transfer.fromAccountId === account.id;
                            // The counterpart is whichever leg isn't this account — the row is read
                            // from this account's point of view, so it shows where money went or
                            // came from, not both names.
                            const counterpart = outgoing
                              ? transfer.toAccountName
                              : transfer.fromAccountName;
                            const amount = outgoing ? transfer.fromAmount : transfer.toAmount;
                            const currency = outgoing ? transfer.fromCurrency : transfer.toCurrency;
                            const crossCurrency = transfer.fromCurrency !== transfer.toCurrency;
                            return (
                              <TableRow key={transfer.id}>
                                <TableCell className="text-paragraph-sm-medium">
                                  {fmt.date(transfer.date)}
                                </TableCell>
                                <TableCell>
                                  <span className="flex items-center gap-x-1.5 text-paragraph-sm">
                                    {outgoing ? (
                                      <ArrowUpRight className="size-4 shrink-0 text-muted-foreground" />
                                    ) : (
                                      <ArrowDownLeft className="size-4 shrink-0 text-muted-foreground" />
                                    )}
                                    {outgoing
                                      ? t('table.sentTo', { account: counterpart })
                                      : t('table.receivedFrom', { account: counterpart })}
                                  </span>
                                </TableCell>
                                <TableCell className="text-right">
                                  <SignedAmountCell
                                    amount={amount}
                                    currency={currency}
                                    outgoing={outgoing}
                                    /* Both sides are shown only when they differ — that pair IS the
                                       record of the rate, and one derived number can't read
                                       correctly for both buying and selling. */
                                    subLine={
                                      crossCurrency &&
                                      t('table.crossCurrency', {
                                        from: `${fmt.amount(transfer.fromAmount, transfer.fromCurrency)} ${transfer.fromCurrency}`,
                                        to: `${fmt.amount(transfer.toAmount, transfer.toCurrency)} ${transfer.toCurrency}`,
                                      })
                                    }
                                  />
                                </TableCell>
                                <TableCell className="max-w-48 truncate text-paragraph-sm text-muted-foreground">
                                  {transfer.notes ?? '—'}
                                </TableCell>
                                <TableCell className="text-center">
                                  <RowActionButton
                                    icon={Trash2}
                                    tooltip={t('delete.tooltip')}
                                    variant="destructive"
                                    onClick={() => setDeleteTarget(transfer)}
                                  />
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                      {total > 0 && (
                        <TablePagination
                          page={page}
                          totalPages={Math.max(1, Math.ceil(total / pageSize))}
                          totalLabel={t('table.total', { total })}
                          onPageChange={setPage}
                        />
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </TableCell>
        </TableRow>
      )}

      <ConfirmDialog
        key="transfer-delete"
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        entity={deleteTarget}
        title={t('delete.title')}
        description={(transfer) =>
          t('delete.confirm', {
            amount: `${fmt.amount(transfer.fromAmount, transfer.fromCurrency)} ${transfer.fromCurrency}`,
            from: transfer.fromAccountName,
            to: transfer.toAccountName,
          })
        }
        onConfirm={handleDelete}
        loading={deleting}
        loadingLabel={t('delete.deleting')}
        confirmLabel={t('delete.confirmButton')}
        cancelLabel={t('delete.cancel')}
      />
    </AnimatePresence>
  );
}
