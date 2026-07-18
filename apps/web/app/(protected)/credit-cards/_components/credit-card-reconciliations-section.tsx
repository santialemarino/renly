'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Info, Trash2 } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import {
  Badge,
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
import { ReconciliationDeleteDialog } from '@/app/(protected)/credit-cards/_components/reconciliation-delete-dialog';
import { ReconciliationFormDialog } from '@/app/(protected)/credit-cards/_components/reconciliation-form-dialog';
import { fetchStatements } from '@/app/(protected)/credit-cards/credit-card-actions';
import type { CardReconciliation, StatementPeriod } from '@/lib/api/card-reconciliations';
import { ANIMATION_FAST } from '@/lib/constants/animations';
import { useFormatters } from '@/lib/i18n/formatters';
import { getLocaleTag } from '@/lib/i18n/locales';

interface CreditCardReconciliationsSectionProps {
  cardId: number;
  bucketCurrencies: string[];
  expanded: boolean;
}

export function CreditCardReconciliationsSection({
  cardId,
  bucketCurrencies,
  expanded,
}: CreditCardReconciliationsSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('creditCards.reconciliations');
  const router = useRouter();

  // Per-bucket statement list, keyed by currency. Each list is loaded the first
  // time its bucket is rendered (i.e. when the row is expanded).
  const [statementsByCurrency, setStatementsByCurrency] = useState<
    Record<string, StatementPeriod[]>
  >({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [fetched, setFetched] = useState(false);
  const [activeStatement, setActiveStatement] = useState<StatementPeriod | null>(null);
  const [deleteRec, setDeleteRec] = useState<CardReconciliation | null>(null);

  const loadAll = useCallback(async () => {
    const next: Record<string, StatementPeriod[]> = {};
    const loadingFlags: Record<string, boolean> = {};
    bucketCurrencies.forEach((c) => {
      loadingFlags[c] = true;
    });
    setLoading(loadingFlags);

    await Promise.all(
      bucketCurrencies.map(async (currency) => {
        try {
          next[currency] = await fetchStatements(cardId, currency);
        } catch {
          next[currency] = [];
        }
      }),
    );

    setStatementsByCurrency(next);
    setLoading({});
  }, [cardId, bucketCurrencies]);

  useEffect(() => {
    if (expanded && !fetched) {
      setFetched(true);
      loadAll();
    }
  }, [expanded, fetched, loadAll]);

  function statusFor(statement: StatementPeriod): 'reconciled' | 'stale' | 'not_reconciled' {
    if (!statement.reconciliation) return 'not_reconciled';
    return statement.reconciliation.isStale ? 'stale' : 'reconciled';
  }

  function formatPeriodLabel(start: string, end: string): string {
    // YYYY-MM-DD -> Locale-aware short label using period_end as the anchor.
    // Anchor at local midnight so negative-UTC-offset users don't read the
    // previous month for an end-of-month period (matches `formatMonth` +
    // `formatDateForLocale`).
    const endDate = new Date(end + 'T00:00:00');
    return endDate.toLocaleDateString(getLocaleTag(fmt.locale), {
      month: 'short',
      year: 'numeric',
    });
  }

  function lastReconciledLabel(list: StatementPeriod[]): string {
    const latestReconciled = list.find((s) => s.reconciliation && !s.reconciliation.isStale);
    if (!latestReconciled) return t('notYetReconciled');
    return t('lastReconciled', {
      period: formatPeriodLabel(latestReconciled.periodStart, latestReconciled.periodEnd),
    });
  }

  return (
    <>
      <div className="flex flex-col gap-y-4">
        <div className="flex flex-col gap-y-0.5">
          <span className="text-paragraph-sm-medium">{t('title')}</span>
          <span className="text-paragraph-xs text-muted-foreground">{t('subtitle')}</span>
        </div>

        {bucketCurrencies.map((currency, index) => {
          const list = statementsByCurrency[currency] ?? [];
          const isLoading = loading[currency];
          // Multi-bucket cards get a thin divider + extra top padding between buckets so the
          // boundary is visible without an explicit Separator component.
          const dividerClass = index > 0 ? 'pt-4 border-t border-border' : '';

          return (
            <div key={currency} className={`flex flex-col gap-y-2 ${dividerClass}`}>
              <div className="flex items-center justify-between">
                <span className="text-paragraph-xs-medium">{t('bucketLabel', { currency })}</span>
                <span className="text-paragraph-xs text-muted-foreground">
                  {isLoading ? t('loading') : lastReconciledLabel(list)}
                </span>
              </div>

              <AnimatePresence mode="wait">
                {isLoading ? (
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
                ) : list.length === 0 ? (
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
                          <TableHead>{t('table.period')}</TableHead>
                          <TableHead>{t('table.periodRange')}</TableHead>
                          <TableHead>
                            <span className="inline-flex items-center gap-x-1">
                              {t('table.computedBalance')}
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Info className="size-3 text-muted-foreground cursor-help" />
                                </TooltipTrigger>
                                <TooltipContent className="max-w-xs">
                                  {t('table.computedBalanceTooltip')}
                                </TooltipContent>
                              </Tooltip>
                            </span>
                          </TableHead>
                          <TableHead>{t('table.status')}</TableHead>
                          <TableHead className="w-24 text-center">{t('table.actions')}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {list.map((statement) => {
                          const status = statusFor(statement);
                          return (
                            <TableRow key={`${statement.periodStart}-${statement.periodEnd}`}>
                              <TableCell className="text-paragraph-sm-medium">
                                {formatPeriodLabel(statement.periodStart, statement.periodEnd)}
                              </TableCell>
                              <TableCell className="text-paragraph-xs text-muted-foreground">
                                {fmt.date(statement.periodStart)} → {fmt.date(statement.periodEnd)}
                              </TableCell>
                              <TableCell className="text-paragraph-sm tabular-nums">
                                {fmt.amount(statement.computedBalance, statement.currency)}{' '}
                                <span className="text-paragraph-xs text-muted-foreground">
                                  {statement.currency}
                                </span>
                              </TableCell>
                              <TableCell>
                                {status === 'reconciled' && (
                                  <Badge className="bg-green-100 text-green-700 hover:bg-green-100">
                                    {t('statusReconciled')}
                                  </Badge>
                                )}
                                {status === 'stale' && (
                                  <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100">
                                    {t('statusStale')}
                                  </Badge>
                                )}
                                {status === 'not_reconciled' && (
                                  <Badge className="bg-muted text-muted-foreground hover:bg-muted">
                                    {t('statusNotReconciled')}
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className="text-center">
                                <div className="flex items-center justify-center gap-x-1">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setActiveStatement(statement)}
                                  >
                                    {statement.reconciliation
                                      ? t('viewReconciliation')
                                      : t('reconcileButton')}
                                  </Button>
                                  {statement.reconciliation && (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          variant="ghost"
                                          size="icon"
                                          className="size-7 text-muted-foreground hover:text-destructive"
                                          onClick={() => setDeleteRec(statement.reconciliation)}
                                          aria-label="Delete reconciliation"
                                        >
                                          <Trash2 className="size-3.5" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent>{t('delete.tooltip')}</TooltipContent>
                                    </Tooltip>
                                  )}
                                </div>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      <ReconciliationFormDialog
        open={!!activeStatement}
        onOpenChange={(open) => {
          if (!open) setActiveStatement(null);
        }}
        cardId={cardId}
        statement={activeStatement}
        onSuccess={() => {
          loadAll();
          router.refresh();
        }}
      />

      <ReconciliationDeleteDialog
        open={!!deleteRec}
        onOpenChange={(open) => {
          if (!open) setDeleteRec(null);
        }}
        cardId={cardId}
        reconciliation={deleteRec}
        onSuccess={() => {
          loadAll();
          router.refresh();
        }}
      />
    </>
  );
}
