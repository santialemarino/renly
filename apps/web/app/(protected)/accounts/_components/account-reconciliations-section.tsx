'use client';

import { useCallback, useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
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
import type { AccountReconciliation } from '@/lib/api/account-reconciliations';
import type { Account } from '@/lib/api/accounts';
import { ANIMATION_FAST } from '@/lib/constants/animations';
import { useFormatters } from '@/lib/i18n/formatters';

interface AccountReconciliationsSectionProps {
  account: Account;
  expanded: boolean;
  // Bumped by the parent after a reconciliation lands, so an already-open row re-reads its list.
  reloadToken: number;
  onReconcile: () => void;
  onChanged: () => void;
}

export function AccountReconciliationsSection({
  account,
  expanded,
  reloadToken,
  onReconcile,
  onChanged,
}: AccountReconciliationsSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('accounts.reconciliations');

  const [reconciliations, setReconciliations] = useState<AccountReconciliation[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AccountReconciliation | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReconciliations(await fetchAccountReconciliations(account.id));
    } catch {
      setReconciliations([]);
    } finally {
      setLoading(false);
    }
  }, [account.id]);

  // Load when the row opens, and again whenever the parent signals a reconciliation landed.
  useEffect(() => {
    if (expanded) load();
  }, [expanded, reloadToken, load]);

  // Which side the adjustment landed on. Positive means the account held more than Renly knew.
  function adjustmentLabel(reconciliation: AccountReconciliation): string {
    const diff = Number(reconciliation.difference);
    if (diff === 0) return t('table.noAdjustment');
    const amount = fmt.amount(String(Math.abs(diff)), account.currency);
    return diff > 0 ? t('table.addedAsIncome', { amount }) : t('table.addedAsExpense', { amount });
  }

  return (
    <>
      <div className="flex flex-col gap-y-3">
        <div className="flex items-start justify-between gap-x-4">
          <div className="flex flex-col gap-y-0.5">
            <span className="text-paragraph-sm-medium">{t('title')}</span>
            <span className="text-paragraph-xs text-muted-foreground">{t('subtitle')}</span>
          </div>
          <Button variant="outline" size="sm" onClick={onReconcile}>
            {t('reconcileButton')}
          </Button>
        </div>

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.p
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: ANIMATION_FAST }}
              className="text-paragraph-sm text-muted-foreground"
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
              className="text-paragraph-sm text-muted-foreground"
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
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('table.date')}</TableHead>
                    <TableHead className="text-right">{t('table.realBalance')}</TableHead>
                    <TableHead className="text-right">{t('table.computedBalance')}</TableHead>
                    <TableHead>{t('table.adjustment')}</TableHead>
                    <TableHead className="w-16 text-center">{t('table.actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reconciliations.map((reconciliation) => (
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
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

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
    </>
  );
}
