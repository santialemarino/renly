'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Lock, Trash2 } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { AccountReconciliationDeleteDialog } from '@/app/(protected)/accounts/_components/account-reconciliation-delete-dialog';
import { fetchAccountReconciliations } from '@/app/(protected)/accounts/account-actions';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { TablePagination } from '@/components/table-pagination';
import type { AccountReconciliation } from '@/lib/api/account-reconciliations';
import type { Account } from '@/lib/api/accounts';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';
import { API_DEFAULT_PAGE_SIZE } from '@/lib/constants/api-constants';
import { useFormatters } from '@/lib/i18n/formatters';

// Minimum time (ms) from fetch start before showing the result.
// Prevents layout flash when the fetch resolves instantly.
const RECONCILIATIONS_DISPLAY_DELAY_MS = 500;

interface AccountReconciliationsSectionProps {
  account: Account;
  expanded: boolean;
  colSpan: number;
  // Bumped by the parent after a reconciliation lands, so an already-loaded row re-reads its list.
  reloadToken: number;
  onReconcile: () => void;
  onChanged: () => void;
}

export function AccountReconciliationsSection({
  account,
  expanded,
  colSpan,
  reloadToken,
  onReconcile,
  onChanged,
}: AccountReconciliationsSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('accounts.reconciliations');

  const [reconciliations, setReconciliations] = useState<AccountReconciliation[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(API_DEFAULT_PAGE_SIZE);
  const [latestDate, setLatestDate] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AccountReconciliation | null>(null);
  // The reloadToken whose data is currently loaded; null until the first fetch.
  const loadedTokenRef = useRef<number | null>(null);
  // The page that token was loaded for, so a page change re-fetches while a re-expand does not.
  const loadedPageRef = useRef<number | null>(null);

  /*
   * Only the account's most recent reconciliation can be deleted — an older one's adjustment is
   * already inside every later reconciliation's recorded computed_balance, so removing it would skew
   * those (the API enforces this too). The deletable rows are exactly those sharing the newest date.
   *
   * That date comes from the RESPONSE rather than from `reconciliations[0]`, and since SEC-11 it has
   * to: this list is one page now, so the first row of page 2 is the newest row ON THAT PAGE and not
   * the account's — the UI would offer a delete the API then refuses with 409.
   */

  /*
   * A shared account's history gains a WHO column and a subtitle that says the difference divides.
   * Both are withheld on a private account rather than rendered blank: its history has exactly one
   * possible author, so a column naming them on every row is noise, and the API sends no name for it.
   */
  const isShared = account.scope === 'shared';

  const load = useCallback(async () => {
    setLoading(true);
    const start = Date.now();
    try {
      const data = await fetchAccountReconciliations(account.id, page);
      const elapsed = Date.now() - start;
      if (elapsed < RECONCILIATIONS_DISPLAY_DELAY_MS) {
        await new Promise((r) => setTimeout(r, RECONCILIATIONS_DISPLAY_DELAY_MS - elapsed));
      }
      setReconciliations(data.items);
      setTotal(data.total);
      setPageSize(data.pageSize);
      setLatestDate(data.latestAsOfDate);
    } catch {
      setReconciliations([]);
      setTotal(0);
      setLatestDate(null);
    } finally {
      setLoading(false);
    }
  }, [account.id, page]);

  /*
   * Fetch on first expand; re-expand shows cached data instantly. A bumped reloadToken (a
   * reconciliation landed) invalidates the cache, so comparing the loaded token covers both cases
   * without a separate "fetched" flag.
   */
  useEffect(() => {
    if (!expanded) return;
    // The token guard caches across a re-expand; the page is not part of it, because changing page is
    // a request for different rows rather than a re-open of the ones already loaded.
    if (loadedTokenRef.current === reloadToken && loadedPageRef.current === page) return;
    loadedTokenRef.current = reloadToken;
    loadedPageRef.current = page;
    load();
  }, [expanded, reloadToken, page, load]);

  // Which side the adjustment landed on. Positive means the account held more than Renly knew.
  function adjustmentLabel(reconciliation: AccountReconciliation): string {
    const diff = Number(reconciliation.difference);
    if (diff === 0) return t('table.noAdjustment');
    const amount = fmt.amount(String(Math.abs(diff)), account.currency);
    return diff > 0 ? t('table.addedAsIncome', { amount }) : t('table.addedAsExpense', { amount });
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
                    <span className="text-paragraph-xs text-muted-foreground">
                      {isShared ? t('sharedSubtitle') : t('subtitle')}
                    </span>
                  </div>
                  {/* The same two conditions the row's own action carries — see accounts-table. */}
                  {account.canReconcile && account.isActive && (
                    <Button variant="outline" size="sm" onClick={onReconcile}>
                      {t('reconcileButton')}
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
                  ) : reconciliations.length === 0 ? (
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
                            <TableHead className="text-right">{t('table.realBalance')}</TableHead>
                            <TableHead className="text-right">
                              {t('table.computedBalance')}
                            </TableHead>
                            <TableHead>{t('table.adjustment')}</TableHead>
                            {isShared && <TableHead>{t('table.reconciledBy')}</TableHead>}
                            <TableHead className="w-16 text-center">{t('table.actions')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {reconciliations.map((reconciliation) => {
                            const isLatest = reconciliation.asOfDate === latestDate;
                            return (
                              <TableRow key={reconciliation.id}>
                                <TableCell className="text-paragraph-sm-medium">
                                  {fmt.date(reconciliation.asOfDate)}
                                </TableCell>
                                <TableCell className="text-right text-paragraph-sm tabular-nums">
                                  {fmt.amount(reconciliation.statementBalance, account.currency)}
                                </TableCell>
                                <TableCell className="text-right text-paragraph-sm tabular-nums text-muted-foreground">
                                  {fmt.amount(reconciliation.computedBalance, account.currency)}
                                </TableCell>
                                <TableCell className="text-paragraph-xs text-muted-foreground">
                                  {adjustmentLabel(reconciliation)}
                                </TableCell>
                                {isShared && (
                                  <TableCell className="text-paragraph-xs text-muted-foreground">
                                    {/* Null once that seat has no account left, exactly as the group's
                                        activity trail leaves an actor unnamed for the same reason. */}
                                    {reconciliation.reconciledBy ?? t('table.reconciledByUnknown')}
                                  </TableCell>
                                )}
                                <TableCell className="text-center">
                                  {/*
                                   * Withhold rather than disable: a Radix tooltip never fires on a
                                   * disabled trigger, so notLatestTooltip could never actually explain
                                   * why an older reconciliation can't be deleted. Reconciliation is
                                   * forward-only — delete newest-first.
                                   */}
                                  {isLatest ? (
                                    <RowActionButton
                                      icon={Trash2}
                                      tooltip={t('delete.tooltip')}
                                      variant="destructive"
                                      className="size-7"
                                      iconClassName="size-3.5"
                                      testId="reconciliation-delete"
                                      onClick={() => setDeleteTarget(reconciliation)}
                                    />
                                  ) : (
                                    <RowLockedIndicator
                                      icon={Lock}
                                      tooltip={t('delete.notLatestTooltip')}
                                      label={t('delete.notLatestLabel')}
                                      className="size-7"
                                      iconClassName="size-3.5"
                                    />
                                  )}
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

                <AccountReconciliationDeleteDialog
                  open={!!deleteTarget}
                  onOpenChange={(open) => {
                    if (!open) setDeleteTarget(null);
                  }}
                  accountId={account.id}
                  reconciliation={deleteTarget}
                  onSuccess={() => {
                    load();
                    onChanged();
                  }}
                />
              </div>
            </motion.div>
          </TableCell>
        </TableRow>
      )}
    </AnimatePresence>
  );
}
