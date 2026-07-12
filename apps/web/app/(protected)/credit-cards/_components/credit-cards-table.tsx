'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Archive,
  ArchiveRestore,
  ChevronRight,
  CreditCard as CreditCardIcon,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
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
import { CreditCardFormDialog } from '@/app/(protected)/_components/credit-card-form-dialog';
import { CreditCardArchiveDialog } from '@/app/(protected)/credit-cards/_components/credit-card-archive-dialog';
import { CreditCardDeleteDialog } from '@/app/(protected)/credit-cards/_components/credit-card-delete-dialog';
import { CreditCardReconciliationsSection } from '@/app/(protected)/credit-cards/_components/credit-card-reconciliations-section';
import { SettlementDeleteDialog } from '@/app/(protected)/credit-cards/_components/settlement-delete-dialog';
import { SettlementFormDialog } from '@/app/(protected)/credit-cards/_components/settlement-form-dialog';
import {
  fetchSettlements,
  unarchiveCreditCard,
  type SettlementResult,
} from '@/app/(protected)/credit-cards/credit-card-actions';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { CreditCard, CreditCardSortField } from '@/lib/api/credit-cards';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

// Minimum time (ms) from fetch start before showing the result.
// Prevents layout flash when the fetch resolves instantly.
const SETTLEMENTS_DISPLAY_DELAY_MS = 500;

function SettlementsSection({
  cardId,
  bucketCurrencies,
  expanded,
}: {
  cardId: number;
  bucketCurrencies: string[];
  expanded: boolean;
}) {
  const locale = useLocale();
  const t = useTranslations('creditCards');
  const router = useRouter();
  const [settlements, setSettlements] = useState<SettlementResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteSettlementState, setDeleteSettlementState] = useState<SettlementResult | null>(null);

  const loadSettlements = useCallback(async () => {
    setLoading(true);
    const start = Date.now();
    try {
      const data = await fetchSettlements(cardId);
      const elapsed = Date.now() - start;
      if (elapsed < SETTLEMENTS_DISPLAY_DELAY_MS) {
        await new Promise((r) => setTimeout(r, SETTLEMENTS_DISPLAY_DELAY_MS - elapsed));
      }
      setSettlements(data);
    } catch {
      setSettlements([]);
    } finally {
      setLoading(false);
    }
  }, [cardId]);

  // Fetch on first expand. Re-expand shows cached data instantly.
  const [fetched, setFetched] = useState(false);
  useEffect(() => {
    if (expanded && !fetched) {
      setFetched(true);
      loadSettlements();
    }
  }, [expanded, fetched, loadSettlements]);

  return (
    <AnimatePresence>
      {expanded && (
        <TableRow>
          <TableCell colSpan={7} className="p-0">
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <div className="px-8 py-4 bg-muted/30">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-paragraph-sm-medium">{t('settlements.title')}</span>
                  <Button variant="outline" size="sm" onClick={() => setAddOpen(true)}>
                    <Plus className="size-3.5" />
                    {t('settlements.add')}
                  </Button>
                </div>

                <AnimatePresence mode="wait">
                  {loading ? (
                    <motion.p
                      key="loading"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="text-paragraph-sm text-muted-foreground"
                    >
                      {t('settlements.loading')}
                    </motion.p>
                  ) : settlements.length === 0 ? (
                    <motion.p
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="text-paragraph-sm text-muted-foreground"
                    >
                      {t('settlements.empty')}
                    </motion.p>
                  ) : (
                    <motion.div
                      key="table"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                    >
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{t('settlements.table.date')}</TableHead>
                            <TableHead>{t('settlements.table.amount')}</TableHead>
                            <TableHead>{t('settlements.table.currency')}</TableHead>
                            <TableHead>{t('settlements.table.notes')}</TableHead>
                            <TableHead className="w-12 text-center">{t('table.actions')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {settlements.map((s) => (
                            <TableRow key={s.id}>
                              <TableCell>{formatDateForLocale(s.date, locale)}</TableCell>
                              <TableCell className="text-paragraph-sm tabular-nums">
                                {formatAmount(s.amount, locale, s.currency)}
                              </TableCell>
                              <TableCell>{s.currency}</TableCell>
                              <TableCell className="max-w-48 truncate text-muted-foreground">
                                {s.notes ?? '—'}
                              </TableCell>
                              <TableCell>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-7 text-muted-foreground hover:text-destructive"
                                      onClick={() => setDeleteSettlementState(s)}
                                      aria-label="Delete settlement"
                                    >
                                      <Trash2 className="size-3.5" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>{t('settlements.deleteTooltip')}</TooltipContent>
                                </Tooltip>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </motion.div>
                  )}
                </AnimatePresence>

                <SettlementFormDialog
                  open={addOpen}
                  onOpenChange={setAddOpen}
                  cardId={cardId}
                  bucketCurrencies={bucketCurrencies}
                  onSuccess={() => {
                    loadSettlements();
                    router.refresh();
                  }}
                />

                <SettlementDeleteDialog
                  open={!!deleteSettlementState}
                  onOpenChange={(open) => {
                    if (!open) setDeleteSettlementState(null);
                  }}
                  cardId={cardId}
                  settlement={deleteSettlementState}
                  onSuccess={() => {
                    loadSettlements();
                    router.refresh();
                  }}
                />

                <div className="mt-6 pt-6 border-t border-border">
                  <CreditCardReconciliationsSection
                    cardId={cardId}
                    bucketCurrencies={bucketCurrencies}
                    expanded={expanded}
                  />
                </div>
              </div>
            </motion.div>
          </TableCell>
        </TableRow>
      )}
    </AnimatePresence>
  );
}

export function CreditCardsTable({
  cards,
  preferredCurrencies,
  firstRun,
}: {
  cards: CreditCard[];
  preferredCurrencies?: string[];
  firstRun?: boolean;
}) {
  const locale = useLocale();
  const t = useTranslations('creditCards');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, isPending } = useTableSort<CreditCardSortField>(
    ROUTES.creditCards,
  );
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editCard, setEditCard] = useState<CreditCard | null>(null);
  const [archiveCard, setArchiveCard] = useState<CreditCard | null>(null);
  const [deleteCardState, setDeleteCardState] = useState<CreditCard | null>(null);
  const [unarchiving, setUnarchiving] = useState<number | null>(null);

  async function handleUnarchive(card: CreditCard) {
    setUnarchiving(card.id);
    try {
      await unarchiveCreditCard(card.id);
      toast.success(t('actions.unarchiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.unarchiveError'));
    } finally {
      setUnarchiving(null);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-6" />
              <SortableTableHead
                label={t('table.name')}
                column="name"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.closingDay')}
                column="closing_day"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.dueDay')}
                column="due_day"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.currency')}
                column="currency"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.balance')}</TableHead>
              <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cards.length === 0 ? (
              <TableEmptyRow
                colSpan={7}
                firstRun={firstRun}
                icon={CreditCardIcon}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              cards.map((card) => {
                const isExpanded = expandedId === card.id;
                return (
                  <Fragment key={card.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : card.id)}
                    >
                      <TableCell>
                        <ChevronRight
                          className={cn(
                            'size-4 transition-transform duration-200',
                            isExpanded && 'rotate-90',
                          )}
                        />
                      </TableCell>
                      <TableCell className="text-paragraph-sm-medium">{card.name}</TableCell>
                      <TableCell>{card.closingDay}</TableCell>
                      <TableCell>{card.dueDay}</TableCell>
                      <TableCell>{card.currency}</TableCell>
                      <TableCell className="text-paragraph-sm tabular-nums">
                        <div className="flex flex-col gap-y-0.5">
                          {card.balances.map((bucket) => (
                            <span key={bucket.currency} className="flex items-baseline gap-x-1.5">
                              <span>{formatAmount(bucket.balance, locale, bucket.currency)}</span>
                              <span className="text-paragraph-xs text-muted-foreground">
                                {bucket.currency}
                              </span>
                            </span>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                        {!card.isActive ? (
                          <div className="flex items-center justify-center">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-8"
                                  onClick={() => handleUnarchive(card)}
                                  disabled={unarchiving === card.id}
                                  aria-label="Unarchive"
                                >
                                  <ArchiveRestore className="size-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>{t('actions.unarchive')}</TooltipContent>
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
                                  onClick={() => setEditCard(card)}
                                  aria-label="Edit"
                                >
                                  <Pencil className="size-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>{t('actions.edit')}</TooltipContent>
                            </Tooltip>
                            {card.hasExpenses ? (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8 text-muted-foreground hover:text-foreground"
                                    onClick={() => setArchiveCard(card)}
                                    aria-label="Archive"
                                  >
                                    <Archive className="size-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t('actions.archive')}</TooltipContent>
                              </Tooltip>
                            ) : (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8 text-muted-foreground hover:text-destructive"
                                    onClick={() => setDeleteCardState(card)}
                                    aria-label="Delete"
                                  >
                                    <Trash2 className="size-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t('actions.delete')}</TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                    <SettlementsSection
                      key={`settlements-${card.id}`}
                      cardId={card.id}
                      bucketCurrencies={card.balances.map((b) => b.currency)}
                      expanded={isExpanded}
                    />
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <CreditCardFormDialog
        open={!!editCard}
        onOpenChange={(open) => {
          if (!open) setEditCard(null);
        }}
        card={editCard ?? undefined}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />

      <CreditCardArchiveDialog
        open={!!archiveCard}
        onOpenChange={(open) => {
          if (!open) setArchiveCard(null);
        }}
        card={archiveCard}
        onSuccess={() => router.refresh()}
      />

      <CreditCardDeleteDialog
        open={!!deleteCardState}
        onOpenChange={(open) => {
          if (!open) setDeleteCardState(null);
        }}
        card={deleteCardState}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
