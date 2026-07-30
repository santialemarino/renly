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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { AccountReconciliationDeleteDialog } from '@/app/(protected)/accounts/_components/account-reconciliation-delete-dialog';
import { fetchAccountReconciliations } from '@/app/(protected)/accounts/account-actions';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import type { AccountReconciliation } from '@/lib/api/account-reconciliations';
import type { Account } from '@/lib/api/accounts';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';
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
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AccountReconciliation | null>(null);
  // The reloadToken whose data is currently loaded; null until the first fetch.
  const loadedTokenRef = useRef<number | null>(null);

  /*
   * Only the account's most recent reconciliation can be deleted — an older one's adjustment is
   * already inside every later reconciliation's recorded computed_balance, so removing it would
   * skew those (the API enforces this too). The list is ordered newest-first, so the deletable rows
   * are exactly those sharing the newest date.
   */
  const latestDate = reconciliations[0]?.asOfDate;

  const load = useCallback(async () => {
    setLoading(true);
    const start = Date.now();
    try {
      const data = await fetchAccountReconciliations(account.id);
      const elapsed = Date.now() - start;
      if (elapsed < RECONCILIATIONS_DISPLAY_DELAY_MS) {
        await new Promise((r) => setTimeout(r, RECONCILIATIONS_DISPLAY_DELAY_MS - elapsed));
      }
      setReconciliations(data);
    } catch {
      setReconciliations([]);
    } finally {
      setLoading(false);
    }
  }, [account.id]);

  /*
   * Fetch on first expand; re-expand shows cached data instantly. A bumped reloadToken (a
   * reconciliation landed) invalidates the cache, so comparing the loaded token covers both cases
   * without a separate "fetched" flag.
   */
  useEffect(() => {
    if (!expanded || loadedTokenRef.current === reloadToken) return;
    loadedTokenRef.current = reloadToken;
    load();
  }, [expanded, reloadToken, load]);

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
                    <span className="text-paragraph-xs text-muted-foreground">{t('subtitle')}</span>
                  </div>
                  {/* Archived accounts are read-only here, matching their hidden row action. */}
                  {account.isActive && (
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
                                <TableCell className="text-center">
                                  {/*
                                   * Withhold rather than disable: a Radix tooltip never fires on a
                                   * disabled trigger, so notLatestTooltip could never actually explain
                                   * why an older reconciliation can't be deleted. Reconciliation is
                                   * forward-only — delete newest-first.
                                   */}
                                  {isLatest ? (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          variant="ghost"
                                          size="icon"
                                          className="size-7 text-muted-foreground hover:text-destructive"
                                          onClick={() => setDeleteTarget(reconciliation)}
                                          aria-label="Delete reconciliation"
                                        >
                                          <Trash2 className="size-3.5" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent>{t('delete.tooltip')}</TooltipContent>
                                    </Tooltip>
                                  ) : (
                                    <RowLockedIndicator
                                      icon={Lock}
                                      tooltip={t('delete.notLatestTooltip')}
                                      ariaLabel="Only the latest reconciliation can be deleted"
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
